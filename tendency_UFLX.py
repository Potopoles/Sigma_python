#!/usr/bin/env python
#-*- coding: utf-8 -*-
"""
File name:          tendency_UFLX.py  
Author:             Christoph Heim (CH)
Date created:       20190510
Last modified:      20190511
License:            MIT

Computation of horizontal momentum flux in longitude
(UFLX) tendency (dUFLXdt) according to:
Jacobson 2005
Fundamentals of Atmospheric Modeling, Second Edition
Chapter 7.4, page 214ff
"""
import time
import numpy as np
import cupy as cp
from numba import cuda, njit, prange, vectorize

from namelist import (UVFLX_dif_coef,
                    i_UVFLX_main_switch,
                    i_UVFLX_hor_adv, i_UVFLX_vert_adv,
                    i_UVFLX_coriolis,
                    i_UVFLX_num_dif, i_UVFLX_pre_grad)
from org_namelist import (wp, wp_int, wp_old)
from grid import nx,nxs,ny,nys,nz,nzs,nb
from GPU import cuda_kernel_decorator

from tendency_functions import (num_dif_py, pre_grad_py)
####################################################################


####################################################################
### DEVICE UNSPECIFIC PYTHON FUNCTIONS
####################################################################
def add_up_tendencies_py(
            UFLX, UFLX_im1, UFLX_ip1, UFLX_jm1, UFLX_jp1,
            PHI, PHI_im1, COLP, COLP_im1,
            POTT, POTT_im1,
            PVTF, PVTF_im1,
            PVTFVB, PVTFVB_im1, 
            PVTFVB_im1_kp1, PVTFVB_kp1,
            dsigma, sigma_vb, sigma_vb_kp1,
            dyis):

    dUFLXdt = wp(0.)

    if i_UVFLX_main_switch:
        # HORIZONTAL ADVECTION
        if i_UVFLX_hor_adv:
            pass
            #dPOTTdt = dPOTTdt + hor_adv(
            #    POTT,
            #    POTT_im1, POTT_ip1,
            #    POTT_jm1, POTT_jp1,
            #    UFLX, UFLX_ip1,
            #    VFLX, VFLX_jp1,
            #    A)
        # VERTICAL ADVECTION
        if i_UVFLX_vert_adv:
            pass
            #dPOTTdt = dPOTTdt + vert_adv(
            #    POTTVB, POTTVB_kp1,
            #    WWIND, WWIND_kp1,
            #    COLP_NEW, dsigma, k)
        # CORIOLIS AND SPHERICAL GRID CONVERSION
        if i_UVFLX_coriolis:
            pass
        # PRESSURE GRADIENT
        if i_UVFLX_pre_grad:
            dUFLXdt = dUFLXdt + pre_grad(
                PHI, PHI_im1, COLP, COLP_im1,
                POTT, POTT_im1,
                PVTF, PVTF_im1,
                PVTFVB, PVTFVB_im1,
                PVTFVB_im1_kp1, PVTFVB_kp1,
                dsigma, sigma_vb, sigma_vb_kp1,
                dyis)
        # NUMERICAL HORIZONTAL DIFUSION
        if i_UVFLX_num_dif and (UVFLX_dif_coef > wp(0.)):
            dUFLXdt = dUFLXdt + num_dif(
                UFLX, UFLX_im1, UFLX_ip1,
                UFLX_jm1, UFLX_jp1,
                UVFLX_dif_coef)

    return(dUFLXdt)






####################################################################
### SPECIALIZE FOR GPU
####################################################################
num_dif = njit(num_dif_py, device=True, inline=True)
pre_grad = njit(pre_grad_py, device=True, inline=True)
add_up_tendencies = njit(add_up_tendencies_py, device=True, inline=True)

def launch_cuda_kernel(dUFLXdt, UFLX, PHI, COLP, POTT,
                        PVTF, PVTFVB, dsigma, sigma_vb, dyis):

    i, j, k = cuda.grid(3)
    if i >= nb and i < nx+nb and j >= nb and j < ny+nb:
        dUFLXdt[i  ,j  ,k] = \
            add_up_tendencies(UFLX[i  ,j  ,k],
            UFLX    [i-1,j  ,k  ], UFLX    [i+1,j  ,k  ],
            UFLX    [i  ,j-1,k  ], UFLX    [i  ,j+1,k  ],
            PHI     [i  ,j  ,k  ], PHI     [i-1,j  ,k  ],
            COLP    [i  ,j  ,0  ], COLP    [i-1,j  ,0  ],
            POTT    [i  ,j  ,k  ], POTT    [i-1,j  ,k  ],
            PVTF    [i  ,j  ,k  ], PVTF    [i-1,j  ,k  ],
            PVTFVB  [i  ,j  ,k  ], PVTFVB  [i-1,j  ,k  ],
            PVTFVB  [i-1,j  ,k+1], PVTFVB  [i  ,j  ,k+1],
            dsigma  [0  ,0  ,k  ], sigma_vb[0  ,0  ,k  ],
            sigma_vb[0  ,0  ,k+1], dyis    [i  ,j  ,k  ])

UFLX_tendency_gpu = cuda.jit(cuda_kernel_decorator(launch_cuda_kernel))\
                            (launch_cuda_kernel)



####################################################################
### SPECIALIZE FOR CPU
####################################################################
num_dif = njit(num_dif_py)
pre_grad = njit(pre_grad_py)
add_up_tendencies = njit(add_up_tendencies_py)

def launch_numba_cpu(dUFLXdt, UFLX):

    for i in prange(nb,nxs+nb):
        for j in range(nb,ny+nb):
            for k in range(wp_int(0),nz):

                dUFLXdt[i  ,j  ,k] = \
                    add_up_tendencies(UFLX[i  ,j  ,k],
                    UFLX[i-1,j  ,k], UFLX[i+1,j  ,k],
                    UFLX[i  ,j-1,k], UFLX[i  ,j+1,k])


UFLX_tendency_cpu = njit(parallel=True)(launch_numba_cpu)





