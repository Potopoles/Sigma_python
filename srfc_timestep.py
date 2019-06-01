#!/usr/bin/env python
#-*- coding: utf-8 -*-
"""
###############################################################################
Author:             Christoph Heim
Date created:       20190601
Last modified:      20190601
License:            MIT

Time step in surface scheme.
Prognose change in soil temperature SOILTEMP
Tendencies are only implemented for 1 soil layer (nz_soil = 1)
###############################################################################
"""
from numba import cuda, njit, prange
#import numpy as np
#from namelist import i_radiation, i_microphysics
from io_read_namelist import wp, wp_str
from main_grid import nx,ny
from misc_gpu_functions import cuda_kernel_decorator
###############################################################################


###############################################################################
### DEVICE UNSPECIFIC PYTHON FUNCTIONS
###############################################################################
def tendency_SOILTEMP_py():

    dSOILTEMPdt = wp(0.)

    #if i_radiation:
    #    dSOILTEMPdt += (LWFLXNET[i,j,nzs-1] + SWFLXNET[i,j,nzs-1])/ \
    #                    (SOILCP[i,j] * SOILRHO[i,j] * SOILDEPTH[i,j])

    #if i_microphysics > 0:
    #    dSOILTEMPdt = dSOILTEMPdt - ( MIC.surf_evap_flx * MIC.lh_cond_water ) / \
    #                                (CF.SOILCP * CF.SOILRHO * CF.SOILDEPTH)
    dSOILTEMPdt = wp(0.0001)
    return(dSOILTEMPdt)


def timestep_SOILTEMP_py(SOILTEMP, dSOILTEMPdt, dt):
    return(SOILTEMP + dt * dSOILTEMPdt)

def run_full_timestep_py(SOILTEMP, dt):
    dSOILTEMPdt     = tendency_SOILTEMP()
    SOILTEMP        = timestep_SOILTEMP(SOILTEMP, dSOILTEMPdt, dt)
    return(SOILTEMP)



#@jit([wp_old+'[:,:  ], '+wp_old+'[:,:  ], '+wp_old+'[:,:  ], '+wp_old+'[:,:,:]  '], target='gpu')
#def calc_albedo_gpu(SURFALBEDSW, SURFALBEDLW, OCEANMASK, SOILTEMP):
#
#    i, j = cuda.grid(2)
#
#    # ocean
#    if OCEANMASK[i,j] == 1:
#        SURFALBEDSW[i,j] = 0.05
#        #SURFALBEDLW[i,j] = 0.05
#        SURFALBEDLW[i,j] = 0.00
#    # land
#    else:
#        SURFALBEDSW[i,j] = 0.2
#        #SURFALBEDLW[i,j] = 0.2
#        SURFALBEDLW[i,j] = 0.0
#
#    # ice (land and sea)
#    if SOILTEMP[i,j,0] <= 273.15:
#        SURFALBEDSW[i,j] = 0.5
#        #SURFALBEDLW[i,j] = 0.3
#        SURFALBEDLW[i,j] = 0.0
#
#    cuda.syncthreads()
#
#
#@jit([wp_old+'[:,:  ], '+wp_old+'[:,:  ], '+wp_old+'[:,:  ], '+wp_old+'[:,:,:]  '], target='gpu')
#def calc_evaporation_capacity_gpu(SOILEVAPITY, SOILMOIST, OCEANMASK, SOILTEMP):
#    i, j = cuda.grid(2)
#    # calc evaporation capacity
#    if OCEANMASK[i,j] == 0:
#        SOILEVAPITY[i,j] = min(max(0., SOILMOIST[i,j] / evapity_thresh), 1.)



###############################################################################
### SPECIALIZE FOR GPU
###############################################################################
tendency_SOILTEMP = njit(tendency_SOILTEMP_py, device=True, inline=True)
timestep_SOILTEMP = njit(timestep_SOILTEMP_py, device=True, inline=True)
run_full_timestep = njit(run_full_timestep_py, device=True, inline=True)
def launch_cuda_kernel(SOILTEMP, dt):

    i, j = cuda.grid(2)
    if i < nx and j < ny:
        SOILTEMP[i,j,0] = run_full_timestep(SOILTEMP[i,j,0], dt) 

advance_timestep_srfc_gpu = cuda.jit(cuda_kernel_decorator(launch_cuda_kernel,
                            non_3D={'dt':wp_str}))(launch_cuda_kernel)




###############################################################################
### SPECIALIZE FOR CPU
###############################################################################
tendency_SOILTEMP = njit(tendency_SOILTEMP_py)
timestep_SOILTEMP = njit(timestep_SOILTEMP_py)
run_full_timestep = njit(run_full_timestep_py)
def launch_numba_cpu(SOILTEMP, dt):

    for i in prange(nx):
        for j in range(ny):
            SOILTEMP[i,j,0] = run_full_timestep(SOILTEMP[i,j,0], dt) 

advance_timestep_srfc_cpu = njit(parallel=True)(launch_numba_cpu) 
