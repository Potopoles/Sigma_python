#!/usr/bin/env python
#-*- coding: utf-8 -*-
"""
###############################################################################
Author:             Christoph Heim
Date created:       20190601
Last modified:      20190701
License:            MIT

Time step in surface scheme.
Prognose change in soil temperature SOILTEMP
Tendencies are only implemented for 1 soil layer (nz_soil = 1)
###############################################################################
"""
import math
from numba import cuda, njit, prange
from namelist import i_radiation, i_surface_fluxes, i_surface_SOILTEMP_tendency
from io_read_namelist import wp, wp_str, wp_int, gpu_enable
from io_constants import con_cp, con_Lh
from srfc_namelist import (max_moisture_soil, desert_moisture_thresh,
                            land_evap_resist)
from main_grid import nx,ny,nz,nzs,nb
if gpu_enable:
    from misc_gpu_functions import cuda_kernel_decorator
from misc_meteo_utilities import calc_specific_humidity_py 
###############################################################################


###############################################################################
### DEVICE UNSPECIFIC PYTHON FUNCTIONS
###############################################################################
def tendency_SOILTEMP_py(LWFLXNET_srfc, SWFLXNET_srfc,
                        SSHFLX, SLHFLX,
                        SOILCP, SOILRHO, SOILDEPTH):

    dSOILTEMPdt = wp(0.)

    if i_radiation:
        dSOILTEMPdt += ( (LWFLXNET_srfc + SWFLXNET_srfc) /
                         (SOILCP * SOILRHO * SOILDEPTH) )

    if i_surface_fluxes: 
        dSOILTEMPdt -= ( (SSHFLX + SLHFLX) /
                         (SOILCP * SOILRHO * SOILDEPTH) )

    return(dSOILTEMPdt)


def timestep_SOILTEMP_py(SOILTEMP, dSOILTEMPdt, dt):
    return(SOILTEMP + dt * dSOILTEMPdt)

def calc_albedo_py(OCEANMASK, SOILTEMP, SOILMOIST):
    # ocean
    if OCEANMASK:
        SURFALBEDSW = wp(0.05)
        SURFALBEDLW = wp(0.00)
        # sea ice
        if SOILTEMP <= wp(273.15):
            SURFALBEDSW = wp(0.5)
    # land
    else:
        SURFALBEDLW = wp(0.0)
        # desert
        if SOILMOIST < desert_moisture_thresh:
            SURFALBEDSW = wp(0.3)
        else:
            # snow / glacier
            if SOILTEMP <= wp(273.15):
                SURFALBEDSW = wp(0.6)
            # normal land surface
            else:
                SURFALBEDSW = wp(0.2)
    return(SURFALBEDSW, SURFALBEDLW)


def calc_srfc_fluxes_py(SOILTEMP, SOILMOIST,
                        TAIR_nz, QV_nz, WIND_nz, RHO_nz,
                        PSURF, COLP, WINDX_nz, WINDY_nz,
                        DRAGCM, DRAGCH, A, dt):
    # surface momentum flux in x direction pointing towards atmosphere
    SMOMXFLX = - DRAGCM * WIND_nz * WINDX_nz * COLP * A

    # surface momentum flux in y direction pointing towards atmosphere
    SMOMYFLX = - DRAGCM * WIND_nz * WINDY_nz * COLP * A

    # surface sensible heat flux pointing towards atmosphere
    # (w'theta')*rho*con_cp [W m-2]
    SSHFLX = - DRAGCH * WIND_nz * ( TAIR_nz - SOILTEMP ) * RHO_nz * con_cp

    # for QV of soil assume 60% of saturation specific humidity for SOILTEMP
    QV_soil = calc_specific_humidity(SOILTEMP, wp(60.), PSURF)
    # surface latent heat flux pointing towards atmosphere
    # (w'qv')*rho*con_Lh [W m-2]
    SLHFLX = - DRAGCH * WIND_nz * ( QV_nz - QV_soil ) * RHO_nz * con_Lh
    # over land apply resistance to evaporation
    if not math.isnan(SOILMOIST):
        SLHFLX *= land_evap_resist
    # only allow for positive latent heat flux (towards atmosphere)
    SLHFLX = max(wp(0.), SLHFLX)
    # reduce latent heat flux if no soil moisture is available over land
    if not math.isnan(SOILMOIST):
        if dt * SLHFLX / con_Lh > SOILMOIST:
            SLHFLX = SOILMOIST * con_Lh / dt

    return(SMOMXFLX, SMOMYFLX, SSHFLX, SLHFLX)


def run_full_timestep_py(SOILTEMP, SOILMOIST, LWFLXNET_srfc, SWFLXNET_srfc,
                         SOILCP, SOILRHO, SOILDEPTH, OCEANMASK,
                         TAIR_nz, QV_nz, WIND_nz, RHO_nz, PSURF,
                         COLP, WINDX_nz, WINDY_nz,
                         RAIN,
                         DRAGCM, DRAGCH, A, dt):

    # comute surface fluxes
    if i_surface_fluxes:
        SMOMXFLX, SMOMYFLX, SSHFLX, SLHFLX = calc_srfc_fluxes(
                                          SOILTEMP, SOILMOIST,
                                          TAIR_nz, QV_nz,
                                          WIND_nz, RHO_nz, PSURF,
                                          COLP, WINDX_nz, WINDY_nz,
                                          DRAGCM, DRAGCH, A, dt)
    else:
        SMOMXFLX    = wp(0.)
        SMOMYFLX    = wp(0.)
        SSHFLX      = wp(0.)
        SLHFLX      = wp(0.)

    # soil temperature change
    if i_surface_SOILTEMP_tendency:
        dSOILTEMPdt     = tendency_SOILTEMP(LWFLXNET_srfc, SWFLXNET_srfc,
                                            SSHFLX, SLHFLX,
                                            SOILCP, SOILRHO, SOILDEPTH)
    else:
        dSOILTEMPdt = wp(0.)
    SOILTEMP        = timestep_SOILTEMP(SOILTEMP, dSOILTEMPdt, dt)

    # update surface albedo
    SURFALBEDSW, SURFALBEDLW = calc_albedo(OCEANMASK, SOILTEMP, SOILMOIST)

    # soil moisture change
    SOILMOIST -= dt * SLHFLX / con_Lh
    if SOILMOIST > max_moisture_soil:
        SOILMOIST = max_moisture_soil
    SOILMOIST += RAIN
    
    return(SOILTEMP, SOILMOIST, SURFALBEDSW, SURFALBEDLW,
           SMOMXFLX, SMOMYFLX, SSHFLX, SLHFLX)





#@jit([wp_old+'[:,:  ], '+wp_old+'[:,:  ], '+wp_old+'[:,:  ], '+wp_old+'[:,:,:]  '], target='gpu')
#def calc_evaporation_capacity_gpu(SOILEVAPITY, SOILMOIST, OCEANMASK, SOILTEMP):
#    i, j = cuda.grid(2)
#    # calc evaporation capacity
#    if OCEANMASK[i,j] == 0:
#        SOILEVAPITY[i,j] = min(max(0., SOILMOIST[i,j] / evapity_thresh), 1.)



###############################################################################
### SPECIALIZE FOR GPU
###############################################################################
if gpu_enable:
    tendency_SOILTEMP = njit(tendency_SOILTEMP_py, device=True, inline=True)
    timestep_SOILTEMP = njit(timestep_SOILTEMP_py, device=True, inline=True)
    calc_albedo       = njit(calc_albedo_py, device=True, inline=True)
    calc_specific_humidity = njit(calc_specific_humidity_py,
                                device=True, inline=True)
    calc_srfc_fluxes  = njit(calc_srfc_fluxes_py, device=True, inline=True)
    run_full_timestep = njit(run_full_timestep_py, device=True, inline=True)

def launch_cuda_kernel(SOILTEMP, SOILMOIST, LWFLXNET, SWFLXNET, SOILCP,
                       SOILRHO, SOILDEPTH, OCEANMASK,
                       SURFALBEDSW, SURFALBEDLW,
                       TAIR, QV, WIND, RHO, PSURF, COLP,
                       SMOMXFLX, SMOMYFLX, SSHFLX, SLHFLX,
                       WINDX, WINDY, RAIN, DRAGCM, DRAGCH, A, dt):

    i, j = cuda.grid(2)
    if i < nx+2*nb and j < ny+2*nb:
        ( SOILTEMP[i,j,0], SOILMOIST[i,j,0],
          SURFALBEDSW[i,j,0], SURFALBEDLW[i,j,0],
          SMOMXFLX[i,j,0], SMOMYFLX   [i,j,0], SSHFLX     [i,j,0],
          SLHFLX  [i,j,0] ) = run_full_timestep(
                        SOILTEMP[i,j,0],        SOILMOIST[i,j,0],
                        LWFLXNET[i,j,nzs-1],    SWFLXNET[i,j,nzs-1],
                        SOILCP[i,j,0],          SOILRHO[i,j,0],
                        SOILDEPTH[i,j,0],       OCEANMASK[i,j,0],
                        TAIR[i,j,nz-1],         QV[i,j,nz-1],
                        WIND[i,j,nz-1],         RHO[i,j,nz-1],
                        PSURF[i,j,0],           COLP[i,j,0   ],
                        WINDX[i,j,nz-1],        WINDY[i,j,nz-1],
                        RAIN[i,j,0],
                        DRAGCM,                 DRAGCH,
                        A[i,j,0   ],            dt)


if gpu_enable:
    advance_timestep_srfc_gpu = cuda.jit(cuda_kernel_decorator(
                    launch_cuda_kernel,
                    non_3D={'dt':wp_str,'OCEANMASK':'int32[:,:,:]',
                            'DRAGCM':wp_str, 'DRAGCH':wp_str}))(
                    launch_cuda_kernel)


###############################################################################
### SPECIALIZE FOR CPU
###############################################################################
tendency_SOILTEMP = njit(tendency_SOILTEMP_py)
timestep_SOILTEMP = njit(timestep_SOILTEMP_py)
calc_albedo       = njit(calc_albedo_py)
calc_specific_humidity = njit(calc_specific_humidity_py)
calc_srfc_fluxes  = njit(calc_srfc_fluxes_py)
run_full_timestep = njit(run_full_timestep_py)


def launch_numba_cpu(SOILTEMP, SOILMOIST, LWFLXNET, SWFLXNET, SOILCP,
                       SOILRHO, SOILDEPTH, OCEANMASK,
                       SURFALBEDSW, SURFALBEDLW,
                       TAIR, QV, WIND, RHO, PSURF, COLP,
                       SMOMXFLX, SMOMYFLX, SSHFLX, SLHFLX,
                       WINDX, WINDY, RAIN, DRAGCM, DRAGCH, A, dt):

    for i in prange(0,nx+2*nb):
        for j in range(0,ny+2*nb):
            ( SOILTEMP[i,j,0], SOILMOIST[i,j,0],
              SURFALBEDSW[i,j,0], SURFALBEDLW[i,j,0],
              SMOMXFLX[i,j,0], SMOMYFLX[i,j,0], SSHFLX[i,j,0],
              SLHFLX[i,j,0] ) = run_full_timestep(
                        SOILTEMP[i,j,0],        SOILMOIST[i,j,0],
                        LWFLXNET[i,j,nzs-1],    SWFLXNET[i,j,nzs-1],
                        SOILCP[i,j,0],          SOILRHO[i,j,0],
                        SOILDEPTH[i,j,0],       OCEANMASK[i,j,0],
                        TAIR[i,j,nz-1],         QV[i,j,nz-1],
                        WIND[i,j,nz-1],         RHO[i,j,nz-1],
                        PSURF[i,j,0],           COLP[i,j,0   ],
                        WINDX[i,j,nz-1],        WINDY[i,j,nz-1],
                        RAIN[i,j,0],
                        DRAGCM,                 DRAGCH,     
                        A[i,j,0   ],            dt)


advance_timestep_srfc_cpu = njit(parallel=True)(launch_numba_cpu) 
