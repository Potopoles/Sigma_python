#!/usr/bin/env python
#-*- coding: utf-8 -*-
"""
###############################################################################
Author:             Christoph Heim
Date created:       20190630
Last modified:      20190701
License:            MIT

Computations for microphysics scheme.
###############################################################################
"""
from numba import cuda, njit, prange
from io_read_namelist import (i_POTT_microphys, i_moist_microphys)
from io_read_namelist import wp, wp_str, wp_int, wp_bool, gpu_enable
from io_constants import con_cp, con_Lh
from main_grid import nx,ny,nz,nzs,nb
if gpu_enable:
    from misc_gpu_functions import cuda_kernel_decorator
from misc_meteo_utilities import calc_specific_humidity_py 
###############################################################################


###############################################################################
### DEVICE UNSPECIFIC PYTHON FUNCTIONS
###############################################################################
# kinetics of conversion from qv to qc
qv_to_qc_rate = wp(1E-3) # [s-1]
# min qc above which rain is created initially
qc_qr_conv_thresh = wp(2E-3) # [kg kg-1]
# min qc above which rain in raining cloud is created
qr_qr_conv_thresh = wp(2E-4) # [kg kg-1]
# kinetics of conversion from qc to qr
qc_to_qr_rate = wp(1E-3) # [s-1]

def run_all_py(QV, QC, QR, POTT, TAIR, PAIR, RHO,
                RAIN, RAINRATE, ACCRAIN, dt, k, nz, reset_accum):
    
    # latent heat release
    LH_release = wp(0.)
    if k == 0:
        RAIN = wp(0.)

    # CONVERSION BETWEEN QV AND QC
    QV_sat = calc_specific_humidity(TAIR, wp(80.), PAIR)
    # amount of QV causing supersaturation
    QV_excess = QV - QV_sat

    # in case of condensation
    if QV_excess > wp(0.):
        Q_cond = QV_excess
    # in case of evaporation
    elif QV_excess < wp(0.):
        Q_cond = - min(abs(QV_excess), QC)

    kinetic_factor = min( qv_to_qc_rate * dt, wp(1.) )
    Q_cond = Q_cond * kinetic_factor

    if i_moist_microphys:
        QV -= Q_cond
        QC += Q_cond
    LH_release += Q_cond * RHO * con_Lh

    # CONVERSION OF QC TO QR
    if i_moist_microphys:
        if QR > qr_qr_conv_thresh or QC > qc_qr_conv_thresh:
            kinetic_factor = min( qc_to_qr_rate * dt, wp(1.) )
            QR = QC * kinetic_factor
        else:
            QR = wp(0.)
    
        QC -= QR
        RAIN += QR * RHO

        if k == nz-1:
            if reset_accum:
                RAINRATE = wp(0.)
            RAINRATE += RAIN
            ACCRAIN += RAIN
        

    # CHANGE OF TEMPERATURE
    if i_POTT_microphys:
        POTT += LH_release / con_cp
        dPOTTdt_MIC = LH_release / con_cp / dt * wp(3600)
    else:
        dPOTTdt_MIC = wp(0.)

    return(QV, QC, QR, POTT, dPOTTdt_MIC, RAIN, RAINRATE, ACCRAIN)



###############################################################################
### SPECIALIZE FOR GPU
###############################################################################
if gpu_enable:
    calc_specific_humidity = njit(calc_specific_humidity_py,
                                    device=True, inline=True)
    run_all = njit(run_all_py, device=True, inline=True)

def launch_cuda_kernel(QV, QC, QR, POTT, TAIR, PAIR, RHO,
                    dPOTTdt_MIC, RAIN, RAINRATE, ACCRAIN, dt, reset_accum):

    i, j, k = cuda.grid(3)
    if i < nx+2*nb and j < ny+2*nb and k < nz:
        kiter = 0

        while kiter < nz:
            if kiter == k:
                ( QV[i,j,k], QC[i,j,k], QR[i,j,k],
                  POTT[i,j,k], dPOTTdt_MIC[i,j,k],
                  RAIN[i,j,0], RAINRATE[i,j,0], ACCRAIN[i,j,0] ) = run_all(
                        QV          [i,j,k],    QC          [i,j,k],
                        QR          [i,j,k],
                        POTT        [i,j,k],    TAIR        [i,j,k],
                        PAIR        [i,j,k],    RHO         [i,j,k],
                        RAIN        [i,j,0],    RAINRATE    [i,j,0],
                        ACCRAIN     [i,j,0],
                        dt, k, nz, reset_accum)
            kiter += 1
            cuda.syncthreads()


if gpu_enable:
    compute_microphysics_gpu = cuda.jit(cuda_kernel_decorator(
                    launch_cuda_kernel,
                    non_3D={'dt':wp_str, 'k':wp_int,
                            'nz':wp_int,'reset_accum':wp_bool}))(
                    launch_cuda_kernel)


###############################################################################
### SPECIALIZE FOR CPU
###############################################################################
#tendency_SOILTEMP = njit(tendency_SOILTEMP_py)
#timestep_SOILTEMP = njit(timestep_SOILTEMP_py)
#calc_albedo       = njit(calc_albedo_py)
#calc_specific_humidity = njit(calc_specific_humidity_py)
#calc_srfc_fluxes  = njit(calc_srfc_fluxes_py)
#run_full_timestep = njit(run_full_timestep_py)
#
#
#def launch_numba_cpu(SOILTEMP, LWFLXNET, SWFLXNET, SOILCP,
#                       SOILRHO, SOILDEPTH, OCEANMASK,
#                       SURFALBEDSW, SURFALBEDLW,
#                       TAIR, QV, WIND, RHO, PSURF, COLP,
#                       SMOMXFLX, SMOMYFLX, SSHFLX, SLHFLX,
#                       WINDX, WINDY, DRAGCM, DRAGCH, A, dt):
#
#    for i in prange(0,nx+2*nb):
#        for j in range(0,ny+2*nb):
#            ( SOILTEMP[i,j,0], SURFALBEDSW[i,j,0], SURFALBEDLW[i,j,0],
#              SMOMXFLX[i,j,0], SMOMYFLX[i,j,0], SSHFLX[i,j,0],
#              SLHFLX[i,j,0] ) = run_full_timestep(
#                        SOILTEMP[i,j,0],
#                        LWFLXNET[i,j,nzs-1],    SWFLXNET[i,j,nzs-1],
#                        SOILCP[i,j,0],          SOILRHO[i,j,0],
#                        SOILDEPTH[i,j,0],       OCEANMASK[i,j,0],
#                        TAIR[i,j,nz-1],         QV[i,j,nz-1],
#                        WIND[i,j,nz-1],         RHO[i,j,nz-1],
#                        PSURF[i,j,0],           COLP[i,j,0   ],
#                        WINDX[i,j,nz-1],        WINDY[i,j,nz-1],
#                        DRAGCM,                 DRAGCH,     
#                        A[i,j,0   ],            dt)
#
#
#advance_timestep_srfc_cpu = njit(parallel=True)(launch_numba_cpu) 
