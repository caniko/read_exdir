import quantities as pq
import numpy as np
import pathlib

import spikeextractors as se
import neo

import exdir.plugins.quantities
import exdir

from .auxiliary import read_epoch


def get_network_events(data_path, session_id=None):
    f = exdir.File(str(data_path), 'r', plugins=[exdir.plugins.quantities])
    if session_id == None:
        content = tuple(f['acquisition'])
        if len(content) > 1:
            print('There are multiple sessions: %s\nSession %d will be used' % (content, content[0]))
        session = f['acquisition'][content[0]]
    elif isinstance(int, session_id):
        session = f['acquisition'][str(session_id)]
    elif isinstance(str, session_id):
        session = f['acquisition'][session_id]
    else:
        msg = 'session_id has to be string or integer'
        raise ValueError(msg)

    event_dir = data_path / session / 'experiment1' / 'recording1' / 'events/Network_Events-120.0' / 'TEXT_group_1'
    return (
        np.load(event_dir / 'text.npy').astype(str),
        np.load(event_dir / 'timestamp.npy').astype(int),
        np.load(event_dir / 'metadata.npy').astype(int)
    )


def load_lfp(data_path):
    f = exdir.File(str(data_path), 'r', plugins=[exdir.plugins.quantities])

    t_stop = f.attrs['session_duration']
    _lfp = f['processing']['electrophysiology']['channel_group_0']['LFP']
    keys = list(_lfp.keys())
    electrode_value = [_lfp[key]['data'].value.flatten() for key in keys]
    electrode_idx = [_lfp[key].attrs['electrode_idx'] for key in keys]
    sampling_rate = _lfp[keys[0]].attrs['sample_rate']
    units = _lfp[keys[0]]['data'].attrs['unit']
    LFP = np.r_[[_lfp[key]['data'].value.flatten() for key in keys]].T
    #LFP = (LFP.T - np.median(np.array(LFP), axis=-1)).T #CMR reference
    #LFP = (LFP.T - LFP[:, 0]).T # use topmost channel as reference
    LFP = LFP[:, np.argsort(electrode_idx)]

    LFP = neo.AnalogSignal(LFP,
                           units=units, t_stop=t_stop, sampling_rate=sampling_rate)
    LFP = LFP.rescale('mV')
    return LFP


def load_epochs(data_path):
    f = exdir.File(str(data_path), 'r', plugins=[exdir.plugins.quantities])
    epochs_group = f['epochs']
    epochs = []
    for group in epochs_group.values():
        if 'timestamps' in group.keys():
            epo = read_epoch(f, group.name)
            epochs.append(epo)
        else:
            for g in group.values():
                if 'timestamps' in g.keys():
                    epo = read_epoch(f, g.name)
                    epochs.append(epo)
    # io = neo.ExdirIO(str(data_path), plugins=[exdir.plugins.quantities, exdir.plugins.git_lfs])
    # blk = io.read_block()
    # seg = blk.segments[0]
    # epochs = seg.epochs
    return epochs


def load_spiketrains(data_path, channel_group=None, load_waveforms=False, sample_rate=None,
                    remove_group=None, t_start=0 * pq.s):
   '''

   Parameters
   ----------
   data_path
   channel_group
   load_waveforms
   remove_label

   Returns
   -------

   '''
   if sample_rate is None:
       sample_rate = 30000 * pq.Hz
   sorting = se.ExdirSortingExtractor(data_path, sample_rate=sample_rate.magnitude,
                                      channel_group=channel_group, load_waveforms=load_waveforms)
   sptr = []
   # build neo pbjects
   for u in sorting.get_unit_ids():
       times = sorting.get_unit_spike_train(u) / sample_rate
       t_stop = np.max(times)
       if load_waveforms and 'waveforms' in sorting.get_unit_spike_feature_names(u):
           wf = sorting.get_unit_spike_features(u, 'waveforms')
       else:
           wf = None
       times = times - t_start
       times = times[np.where(times > 0)]
       if wf is not None:
           wf = wf[np.where(times > 0)]
       st = neo.SpikeTrain(times=times, t_stop=t_stop, waveforms=wf)
       for p in sorting.get_unit_property_names(u):
           st.annotations.update({p: sorting.get_unit_property(u, p)})
       sptr.append(st)

   sptr_rm = []
   if remove_group is not None:
       for st in sptr:
           if st.annotations['cluster_group'] != remove_group:
               sptr_rm.append(st)
   else:
       sptr_rm = sptr

   return sptr_rm
