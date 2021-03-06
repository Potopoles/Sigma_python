#!/usr/bin/env python
#-*- coding: utf-8 -*-
"""
###############################################################################
Author:             Christoph Heim
Date created:       20190526
Last modified:      20190608
License:            MIT

Computation column pressure (COLP) tendency and vertical wind (WWIND),
as well as time step forward for COLP (COLP_OLD to COLP_NEW).
Doing the time step already here is necessary because COLP_NEW is needed
for forward integration in UVFLX and POTT.
Computations aaccording to:
Jacobson 2005
Fundamentals of Atmospheric Modeling, Second Edition
Chapter 7.4, page 208ff

HISTORY
- 20190531: CH: First implementation.
- 20190608: CH: Removed vertical reduction restriction of nz = 2**x
###############################################################################
"""
import numpy as np
from numba import cuda, njit, prange, vectorize

from namelist import (i_COLP_main_switch)
from io_read_namelist import (wp_str, wp, wp_numba, wp_int, gpu_enable)
from main_grid import (nx,nxs,ny,nys,nz,nzs,nb,
                  shared_nz)
from dyn_functions import euler_forward_py
if gpu_enable:
    from misc_gpu_functions import cuda_kernel_decorator
###############################################################################


###############################################################################
### DEVICE UNSPECIFIC PYTHON FUNCTIONS
###############################################################################
def calc_UFLX_py(UWIND, COLP, COLP_im1, dyis):
    return( (COLP_im1 + COLP)/wp(2.) * UWIND * dyis )

def calc_VFLX_py(VWIND, COLP, COLP_jm1, dxjs):
    return( (COLP_jm1 + COLP)/wp(2.) * VWIND * dxjs )

def calc_FLXDIV_py(UFLX, UFLX_ip1, VFLX, VFLX_jp1, dsigma, A):
    return( ( + UFLX_ip1 - UFLX + VFLX_jp1 - VFLX ) * dsigma / A )


###############################################################################
### SPECIALIZE FOR GPU
###############################################################################
calc_UFLX       = njit(calc_UFLX_py, device=True, inline=True)
calc_VFLX       = njit(calc_VFLX_py, device=True, inline=True)
calc_FLXDIV     = njit(calc_FLXDIV_py, device=True, inline=True)
euler_forward   = njit(euler_forward_py, device=True, inline=True)


def launch_cuda_main_kernel(UFLX, VFLX, FLXDIV,
                    UWIND, VWIND, WWIND,
                    COLP, dCOLPdt, COLP_NEW, COLP_OLD,
                    dyis, dxjs, dsigma, sigma_vb, A, dt):

    i, j, k = cuda.grid(3)

    if i >= nb and i < nx+nb and j >= nb and j < ny+nb:
        # MOMENTUM FLUXES
        #######################################################################
        UFLX_i = calc_UFLX(
            UWIND       [i  ,j  ,k  ],
            COLP        [i  ,j  ,0  ], COLP        [i-1,j  ,0  ],
            dyis        [i  ,j  ,0  ])
        UFLX_ip1 = calc_UFLX(
            UWIND       [i+1,j  ,k  ],
            COLP        [i+1,j  ,0  ], COLP        [i  ,j  ,0  ],
            dyis        [i+1,j  ,0  ])

        VFLX_j = calc_VFLX(
            VWIND       [i  ,j  ,k  ],
            COLP        [i  ,j  ,0  ], COLP        [i  ,j-1,0  ],
            dxjs        [i  ,j  ,0  ])
        VFLX_jp1 = calc_VFLX(
            VWIND       [i  ,j+1,k  ],
            COLP        [i  ,j+1,0  ], COLP        [i  ,j  ,0  ],
            dxjs        [i  ,j+1,0  ])

        UFLX[i  ,j  ,k] = UFLX_i
        VFLX[i  ,j  ,k] = VFLX_j

        # MOMENTUM FLUX DIVERGENCE
        #######################################################################
        FLXDIV[i  ,j  ,k] = calc_FLXDIV(
            UFLX_i           , UFLX_ip1    ,
            VFLX_j           , VFLX_jp1    ,
            dsigma[0  ,0  ,k], A[i  ,j  ,0])

        # COLUMN PRESSURE TENDENCY
        #######################################################################
        if i_COLP_main_switch:
            cuda.syncthreads()
            tz = cuda.threadIdx.z

            vert_sum = cuda.shared.array(shape=shared_nz, dtype=wp_numba)
            vert_sum[tz] = FLXDIV[i,j,k]
            cuda.syncthreads()

            ## sum-reduce vert_sum vertically
            ## (slighly faster method but restrict nz to 2**x)
            #t = shared_nz // 2
            #while t > 0:
            #    if tz < t:
            #        vert_sum[tz] = vert_sum[tz] + vert_sum[tz+t]
            #    t //= 2
            #    cuda.syncthreads()
            #if tz == 0:
            #    dCOLPdt[i,j,0] = - vert_sum[0]

            # sum-reduce vert_sum vertically
            # (slower method but nz can be chosen flexibly)
            kt = 0
            while kt < nz:
                if kt == k-1:
                    vert_sum[k] = vert_sum[k] + vert_sum[k-1]
                kt = kt + 1
                if kt == nz-1:
                    dCOLPdt[i,j,0] = - vert_sum[kt]
                cuda.syncthreads()

        else:
            dCOLPdt[i,j,0] = wp(0.)

        ## PRESSURE TIME STEP
        ########################################################################
        cuda.syncthreads()
        COLP_NEW[i,j,0] = euler_forward(COLP_OLD[i,j,0], dCOLPdt[i,j,0], dt)

        ## VERTICAL WIND
        ########################################################################
        cuda.syncthreads()
        vert_sum[k] = FLXDIV[i,j,k]
        # cumulative-sum-reduce vert_sum vertically
        kt = 0
        while kt < nzs-1:
            if kt == k-1:
                vert_sum[k] = vert_sum[k] + vert_sum[k-1]
                fluxdivsum = vert_sum[kt]
            kt = kt + 1
            cuda.syncthreads()

        WWIND[i,j,k] = ( - fluxdivsum / COLP_NEW[i,j,0] 
                         - sigma_vb[0,0,k] * dCOLPdt[i,j,0] / COLP_NEW[i,j,0] )
        cuda.syncthreads()


if gpu_enable:
    continuity_gpu = cuda.jit(cuda_kernel_decorator(launch_cuda_main_kernel,
                    non_3D={'dt':wp_str}))(launch_cuda_main_kernel)



###############################################################################
### SPECIALIZE FOR CPU
###############################################################################
calc_UFLX       = njit(calc_UFLX_py)
calc_VFLX       = njit(calc_VFLX_py)
calc_FLXDIV     = njit(calc_FLXDIV_py)
euler_forward   = vectorize()(euler_forward_py)


def launch_numba_cpu(UFLX, VFLX, FLXDIV,
                    UWIND, VWIND, WWIND,
                    COLP, dCOLPdt, COLP_NEW, COLP_OLD,
                    dyis, dxjs, dsigma, sigma_vb, A, dt):


    for i in prange(nb,nx+nb):
        for j in range(nb,ny+nb):
            for k in range(wp_int(0),nz):
                # MOMENTUM FLUXES
                ###############################################################
                UFLX_i = calc_UFLX(
                    UWIND       [i  ,j  ,k  ],
                    COLP        [i  ,j  ,0  ], COLP        [i-1,j  ,0  ],
                    dyis        [i  ,j  ,0  ])
                UFLX_ip1 = calc_UFLX(
                    UWIND       [i+1,j  ,k  ],
                    COLP        [i+1,j  ,0  ], COLP        [i  ,j  ,0  ],
                    dyis        [i+1,j  ,0  ])

                VFLX_j = calc_VFLX(
                    VWIND       [i  ,j  ,k  ],
                    COLP        [i  ,j  ,0  ], COLP        [i  ,j-1,0  ],
                    dxjs        [i  ,j  ,0  ])
                VFLX_jp1 = calc_VFLX(
                    VWIND       [i  ,j+1,k  ],
                    COLP        [i  ,j+1,0  ], COLP        [i  ,j  ,0  ],
                    dxjs        [i  ,j+1,0  ])

                UFLX[i  ,j  ,k] = UFLX_i
                VFLX[i  ,j  ,k] = VFLX_j

                ## MOMENTUM FLUX DIVERGENCE
                ###############################################################
                FLXDIV[i  ,j  ,k] = calc_FLXDIV(
                    UFLX_i           , UFLX_ip1    ,
                    VFLX_j           , VFLX_jp1    ,
                    dsigma[0  ,0  ,k], A[i  ,j  ,0])

    ## COLUMN PRESSURE TENDENCY
    ############################################################################
    if i_COLP_main_switch:
        dCOLPdt[:,:,0] = - FLXDIV.sum(axis=2)
    else:
        dCOLPdt[:,:,0] = wp(0.)

    ### PRESSURE TIME STEP
    ############################################################################
    COLP_NEW[:,:,0] = COLP_OLD[:,:,0] + dt * dCOLPdt[:,:,0]

    ### VERTICAL WIND
    ############################################################################
    for i in prange(nb,nx+nb):
        for j in range(nb,ny+nb):
            flxdivsum = FLXDIV[i,j,0]
            for k in prange(1,nz):
                WWIND[i,j,k] = ( - flxdivsum / COLP_NEW[i,j,0] - sigma_vb[0,0,k]
                                 * dCOLPdt[i,j,0] / COLP_NEW[i,j,0] )
                flxdivsum += FLXDIV[i,j,k]



continuity_cpu = njit(parallel=True)(launch_numba_cpu)
