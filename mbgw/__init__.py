"""
Must have the following in current working directory:
- CSE_Asia_and_Americas...hdf5 (pr-incidence trace)
- pr-falciparum (age-pr relationship trace)
- age-dist-falciparum (age distribution trace)
"""

disttol = 5./6378.
ttol = 1./12

import tables as tb
import numpy as np
from st_cov_fun import *
from generic_mbg import FieldStepper, invlogit, histogram_reduce
from pymc import thread_partition_array
from pymc.gp import GPEvaluationGibbs
import pymc as pm
import mbgw
import os
root = os.path.split(mbgw.__file__)[0]
pm.gp.cov_funs.cov_utils.mod_search_path.append(root)

def check_data(input):
    pass
    
nugget_labels = {'sp_sub': 'V'}
obs_labels = {'sp_sub': 'eps_p_f'}

# Extra stuff for predictive ops.
n_facs = 1000

non_cov_columns = {'lo_age': 'int', 'up_age': 'int', 'pos': 'float', 'neg': 'float'}

# Postprocessing stuff for mapping

def pr(sp_sub):
    pr = sp_sub.copy('F')
    return invlogit(pr)

map_postproc = [pr]
bins = np.array([0,.2])

def binfn(arr, bins=bins):
    out = np.digitize(arr, bins)
    return out

bin_reduce = histogram_reduce(bins,binfn)

def bin_finalize(products, n, bins=bins, bin_reduce=bin_reduce):
    out = {}
    for i in xrange(len(bins)-1):
        out['p-class-%i-%i'%(bins[i]*100,bins[i+1]*100)] = products[bin_reduce][:,i+1].astype('float')/n
    out['most-likely-class'] = np.argmax(products[bin_reduce], axis=1)
    out['p-most-likely-class'] = np.max(products[bin_reduce], axis=1).astype('float') / n
    return out
        
extra_reduce_fns = [bin_reduce]    
extra_finalize = bin_finalize

metadata_keys = ['ti','fi','ui','with_stukel','chunk','disttol','ttol']

# Postprocessing stuff for validation

def pr(data):
    obs = data.pos
    n = data.pos + data.neg
    def f(sp_sub, two_ten_facs=two_ten_factors):
        return pm.flib.invlogit(sp_sub)*two_ten_facs[np.random.randint(len(two_ten_facs))]
    return obs, n, f

validate_postproc=[pr]

def survey_likelihood(x, survey_plan, data, i):
    data_ = np.ones_like(x)*data[i]
    return pm.binomial_like(data_, survey_plan.n[i], pm.invlogit(x))

# Postprocessing stuff for survey evaluation

def simdata_postproc(sp_sub, survey_plan):
    p = pm.invlogit(sp_sub)
    n = survey_plan.n
    return pm.rbinomial(n, p)

# Initialize step methods
#def mcmc_init(M):
#    M.use_step_method(GPEvaluationGibbs, M.sp_sub, M.V, M.eps_p_f_list, ti=M.ti)

# Initialize step methods
def mcmc_init(M):
    M.use_step_method(GPEvaluationGibbs, M.sp_sub, M.V, M.eps_p_f, ti=M.ti)
    def isscalar(s):
        return (s.dtype != np.dtype('object')) and (np.alen(s.value)==1) and (s not in M.eps_p_f_list)
    scalar_stochastics = filter(isscalar, M.stochastics)
    
    # The following two lines choose the 'AdaptiveMetropolis' step method (jumping strategy) for 
    # the scalar variables: nugget, scale, partial sill etc. It tries to update all of the variables
    # jointly, so each iteration takes much less time. 
    #
    # Comment them to accept the default, which is one-at-a-time Metropolis. This jumping strategy is
    # much slower, and known to be worse in many cases; but has been performing reliably for small
    # datasets.
    # 
    # The two parameters here, 'delay' and 'interval', control how the step method attempts to adapt its
    # jumping strategy. It waits for 'delay' iterations of one-at-a-time updates before it even tries to
    # start adapting. Subsequently, it tries to adapt every 'interval' iterations.
    # 
    # If any of the variables appear to not have reached their dense support before 'delay' iterations
    # have elapsed, 'delay' must be increased. However, it's good to have 'delay' be as small as possible
    # subject to that constraint.
    #
    # 'Interval' is the last parameter to fiddle; its effects can be hard to understand.
    M.use_step_method(pm.gp.GPParentAdaptiveMetropolis, scalar_stochastics, delay=10000, interval=5000)
    #
    # The following line sets the size of jumps before the first adaptation. If the chain is 'flatlining'
    # before 'delay' iterations have elapsed, it should be decreased. However, it should be as large as
    # possible while still allowing many jumps to be accepted.
    #
    M.step_method_dict[M.log_amp][0].proposal_sd *= 1    
    

from model import *
