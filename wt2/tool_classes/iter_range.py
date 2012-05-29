from __future__ import print_function, division; __metaclass__ = type
from wt2.tool_classes.core import WEMDTool


import logging

log = logging.getLogger(__name__)

import numpy
import wemd

class IterRangeSelection(WEMDTool):
    '''Select and record limits on iterations used in analysis and/or reporting.
    This class provides both the user-facing command-line options and parsing, and
    the application-side API for recording limits in HDF5.
    
    HDF5 datasets calculated based on a restricted set of iterations should be tagged
    with the following attributes:
    
        ``first_iter``
            The first iteration included in the calculation.
            
        ``last_iter``
            One past the last iteration included in the calculation.
            
        ``iter_step``
            Blocking or sampling period for iterations included in the calculation.
    '''
    
    def __init__(self):
        super(IterRangeSelection,self).__init__()
        
        # First iteration on which to perform analysis/reporting
        self.iter_start = None
        
        # One past the last iteration on which to perform analysis/reporting
        self.iter_stop = None
        
        # Step 
        self.iter_step = 1
        
        self.include_args.update({'iter_start': True,
                                  'iter_stop':  True,
                                  'iter_step':  False})

    def add_args(self, parser):
        group = parser.add_argument_group('iteration range')

        if self.include_args['iter_start']:
            group.add_argument('--first-iter', dest='first_iter', type=int, metavar='N_ITER', default=1,
                               help='''Begin analysis at iteration N_ITER (default: %(default)d).''')
        if self.include_args['iter_stop']:
            group.add_argument('--last-iter', dest='last_iter', type=int, metavar='N_ITER',
                               help='''Conclude analysis with N_ITER, inclusive (default: last completed iteration).''')
        if self.include_args['iter_step']:            
            group.add_argument('--step-iter', dest='step_iter', type=int, metavar='STEP',
                               help='''Analyze/report in blocks of STEP iterations.''')

    
    def process_args(self, args):
        if self.include_args['iter_start']:
            self.first_iter = args.first_iter or 1
        if self.include_args['iter_stop'] and args.iter_stop:
            self.last_iter = args.last_iter+1
        if self.include_args['iter_step']:
            self.iter_step = args.iter_step or 1
                    
            
    def check_iter_range(self, data_manager = None):
        data_manager = data_manager or wemd.rc.get_data_manager()
        dm_current_iteration = data_manager.current_iteration
        
        self.iter_start = int(max(self.iter_start, 1))
        if self.iter_stop is None or self.iter_stop >= dm_current_iteration:
            self.last_iter = dm_current_iteration
            
        if self.iter_start == self.iter_stop:
            raise ValueError('first and last iterations are the same')
        wemd.rc.pstatus('Processing iterations from {self.iter_start:d} to {self.iter_stop:d}, inclusive (step size {self.iter_step:d})'.format(self=self))
        
    def iter_block_iter(self):
        '''Return an iterable of (block_start,block_end) over the blocks of iterations
        selected by --first-iter/--last-iter/--step-iter.'''
                            
        for blkfirst in xrange(self.iter_start, self.iter_stop, self.iter_step):
            yield(blkfirst, min(self.iter_stop, blkfirst+self.iter_step))
             
        
    def n_iter_blocks(self):
        '''Return the number of blocks of iterations (as returned by ``iter_block_iter``)
        selected by --first-iter/--last-iter/--step-iter.'''
        npoints = self.iter_stop - self.iter_start
        if npoints % self.iter_step == 0:
            return npoints // self.iter_step
        else:
            return npoints // self.iter_step + 1
            
    def record_data_iter_range(self, h5object, iter_start = None, iter_stop = None):
        '''Store attributes ``iter_start`` and ``iter_stop`` on the given HDF5 object (group/dataset)'''
        iter_start = self.iter_start if iter_start is None else iter_start
        iter_stop  = self.iter_stop if iter_stop is None else iter_stop
        h5object.attrs['iter_start'] = iter_start
        h5object.attrs['iter_stop'] = iter_stop
        
    def record_data_iter_step(self, h5object, iter_step = None):
        '''Store attribute ``iter_step`` on the given HDF5 object (group/dataset).'''
        iter_step = self.iter_setp if iter_step is None else iter_step
        h5object.attrs['iter_step'] = iter_step
        
    def check_data_iter_range_least(self, h5object, iter_start = None, iter_stop = None):
        '''Check that the given HDF5 object contains (as denoted by its ``iter_start``/``iter_stop`` attributes)
        data at least for the iteration range specified.'''
        iter_start = self.iter_start if iter_start is None else iter_start
        iter_stop  = self.iter_stop if iter_stop is None else iter_stop
        
        obj_first_iter = h5object.attrs.get('iter_start')
        obj_last_iter  = h5object.attrs.get('iter_stop')
        
        return (obj_first_iter <= iter_start and obj_last_iter >= iter_stop)
        
    def check_data_iter_range_equal(self, h5object, iter_start = None, iter_stop = None):
        '''Check that the given HDF5 object contains (as denoted by its ``iter_start``/``iter_stop`` attributes)
        data exactly for the iteration range specified.'''

        iter_start = self.iter_start if iter_start is None else iter_start
        iter_stop  = self.iter_stop if iter_stop is None else iter_stop
        
        obj_first_iter = h5object.attrs.get('iter_start')
        obj_last_iter  = h5object.attrs.get('iter_stop')
        
        return (obj_first_iter == iter_start and obj_last_iter == iter_stop)
    
    def check_data_iter_step_conformant(self, h5object, iter_step = None):
        '''Check that the given HDF5 object contains per-iteration data at an iteration stride suitable for extracting data
        with the given stride (in other words, the given ``iter_step`` is a multiple of the stride with 
        which data was recorded).'''
        
        iter_step = iter_step or self.iter_step
        obj_iter_step = h5object.attrs.get('iter_step')
        return (obj_iter_step % iter_step == 0)
    
    def check_data_iter_step_equal(self, h5object, iter_step = None):
        '''Check that the given HDF5 object contains per-iteration data at an iteration stride the same as
        that specified.'''
        iter_step = iter_step or self.iter_step
        obj_iter_step = h5object.attrs.get('iter_step')
        return (obj_iter_step == iter_step)
        
    def slice_per_iter_data(self, dataset, iter_start = None, iter_stop = None, iter_step = None, axis=0):
        '''Return the subset of the given dataset corresponding to the given iteration range and stride. Unless
        otherwise specified, the first dimension of the dataset is the one sliced.'''
        
        iter_start = self.iter_start if iter_start is None else iter_start
        iter_stop  = self.iter_stop if iter_stop is None else iter_stop
        iter_step = self.iter_step if iter_step is None else iter_step
         
        ds_iter_start = dataset.attrs['iter_start']
        ds_iter_stop  = dataset.attrs['iter_stop']
        ds_iter_step  = dataset.attrs.get('iter_step', 1)
        
        if iter_start < ds_iter_start or iter_stop > ds_iter_stop or ds_iter_step % iter_step > 0:
            raise IndexError(('Cannot slice requested iterations [{:d},{:d}) (stride={:d}) from dataset {!r}'
                              +'with range [{:d},{:d}) (stride={:d}).'.format(iter_start,iter_stop,iter_step,
                                                                              ds_iter_start,ds_iter_stop,ds_iter_step)))
        
        dimslices = []
        for idim in xrange(len(dataset.shape)):
            if idim == axis:
                dimslices.append(slice(iter_start - ds_iter_start, iter_stop - ds_iter_stop + iter_step, iter_step))
            else:
                dimslices.append(slice(None,None,None))
        
        dimslices = tuple(dimslices)
        log.debug('slicing {!r} with {!r}'.format(dataset, dimslices))
        data = dataset[dimslices]
        log.debug('resulting data is of shape {!r}'.format(data.shape))
        return data        
        
    
    def iter_range(self, iter_start = None, iter_stop = None, iter_step = None):
        '''Return a sequence for the given iteration numbers and stride, filling 
        in missing values from those stored on ``self``.'''
        iter_start = self.iter_start if iter_start is None else iter_start
        iter_stop  = self.iter_stop if iter_stop is None else iter_stop
        iter_step = self.iter_step if iter_step is None else iter_step
        return numpy.arange(iter_start, iter_stop, iter_step)
        
        
        