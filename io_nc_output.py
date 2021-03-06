#!/usr/bin/env python
#-*- coding: utf-8 -*-
"""
###############################################################################
Author:             Christoph Heim
Date created:       20181001
Last modified:      20190701
License:            MIT

Write fields to nc file.
###############################################################################
"""
import numpy as np
from netCDF4 import Dataset
from pathlib import Path

from namelist import (output_path, output_fields,
                     i_radiation, i_microphysics, i_surface_scheme)
from io_read_namelist import pair_top
from main_grid import nx,nxs,ny,nys,nz,nzs,nb
from io_functions import NC_output_diagnostics
###############################################################################


def output_to_NC(GR, F):

    print('###########################################')
    print('###########################################')
    print('WRITE FIELDS '+str(GR.nc_output_count).zfill(4))
    print('###########################################')
    print('###########################################')

    # PREPARATIONS
    ###########################################################################
    VORT, WWIND_ms, WVP, CWP = NC_output_diagnostics(GR, 
                        **F.get(F.field_groups[F.NC_OUT_DIAG_FIELDS]))

    # CREATE AND OPEN FILE
    ###########################################################################
    Path(output_path).mkdir(exist_ok=True)
    filename = output_path+'/out'+str(GR.nc_output_count).zfill(4)+'.nc'
    ncf = Dataset(filename, 'w', format='NETCDF4')
    ncf.close()
    ncf = Dataset(filename, 'a', format='NETCDF4')

    # DIMENSIONS
    ###########################################################################
    time_dim = ncf.createDimension('time', None)
    #bnds_dim = ncf.createDimension('bnds', 1)
    lon_dim = ncf.createDimension('lon', GR.nx)
    lons_dim = ncf.createDimension('lons', GR.nxs)
    lat_dim = ncf.createDimension('lat', GR.ny)
    lats_dim = ncf.createDimension('lats', GR.nys)
    level_dim = ncf.createDimension('level', GR.nz)
    levels_dim = ncf.createDimension('levels', GR.nzs)

    # DIMENSION VARIABLES
    ###########################################################################
    dtime = ncf.createVariable('time', 'f8', ('time',) )
    #bnds = ncf.createVariable('bnds', 'f8', ('bnds',) )
    lon = ncf.createVariable('lon', 'f4', ('lon',) )
    lons = ncf.createVariable('lons', 'f4', ('lons',) )
    lat = ncf.createVariable('lat', 'f4', ('lat',) )
    lats = ncf.createVariable('lats', 'f4', ('lats',) )
    level = ncf.createVariable('level', 'f4', ('level',) )
    levels = ncf.createVariable('levels', 'f4', ('levels',) )

    dtime[:] = GR.sim_time_sec/3600/24
    #bnds[:] = [0]
    lon[:] = GR.lon_rad[GR.ii,GR.nb+1,0]
    lons[:] = GR.lon_is_rad[GR.iis,GR.nb+1,0]
    lat[:] = GR.lat_rad[GR.nb+1,GR.jj,0]
    lats[:] = GR.lat_js_rad[GR.nb+1,GR.jjs,0]
    level[:] = GR.level
    levels[:] = GR.levels

    ###########################################################################
    # DIRECT FIELDS
    ###########################################################################

    field_names = ['UWIND', 'VWIND', 'WIND', 'POTT', 'TAIR',
                   'PHI', 'PAIR', 'RHO', 'COLP', 'QV', 'QC', 'QR', 'dQVdt',
                   'dQVdt_TURB', 'dUFLXdt_TURB', 'dVFLXdt_TURB',
                   'dPOTTdt_TURB', 'KMOM', 'KHEAT',
                   'SMOMXFLX', 'SMOMYFLX', 'SSHFLX', 'SLHFLX', 'SOILMOIST',
                   'KMOM_dUWINDdz', 'KMOM_dVWINDdz', 'dPOTTdt_MIC',
                   'RAINRATE', 'ACCRAIN', 'RAIN']
    for field_name in field_names:
        if output_fields[field_name]:
            no_border = False
            dimx, dimy, dimz = F.host[field_name].shape
            if (dimx == nx  + 2*nb) or (dimx == nx):
                lon_str = 'lon'
                if dimx == nx: no_border = True
            elif (dimx == nxs + 2*nb) or (dimx == nxs):
                lon_str = 'lons'
            if (dimy == ny  + 2*nb) or (dimy == ny):
                lat_str = 'lat'
            elif (dimy == nys + 2*nb) or (dimy == nys):
                lat_str = 'lats'
            if dimz == nz:
                level_str = 'level'
            elif dimz == nzs:
                level_str = 'levels'
            elif dimz == 1:
                level_str = None

            if level_str is not None:
                dimensions = ('time', level_str, lat_str, lon_str,)
            else:
                dimensions = ('time', lat_str, lon_str,)
            
            #print(field_name)
            #print(dimensions)

            i = np.arange(nb,dimx-1) 
            j = np.arange(nb,dimy-1) 
            ii,jj = np.ix_(i, j)

            VAR_out = ncf.createVariable(field_name, 'f4', dimensions )
            if no_border:
                VAR_out[-1,::] = F.host[field_name][:,:,:].T
            else:
                VAR_out[-1,::] = F.host[field_name][ii,jj,:].T

    ###########################################################################
    # PREPROCESSED FIELDS
    ###########################################################################

    if output_fields['PSURF']:
        PSURF_out = ncf.createVariable('PSURF', 'f4', ('time', 'lat', 'lon',) )
        PSURF_out[-1,:,:] = F.host['COLP'][GR.ii,GR.jj,:].T + pair_top

    if output_fields['WWIND']:
        WWIND_out = ncf.createVariable('WWIND', 'f4',
                                    ('time', 'levels', 'lat', 'lon',) )
        for ks in range(0,GR.nzs):
            WWIND_out[-1,ks,:,:] = (
                    F.host['WWIND'][GR.ii,GR.jj,ks] *
                    F.host['COLP' ][GR.ii,GR.jj,0 ] ).T
        #WWIND_out[-1,ks,:,:] = WWIND_ms[:,:,ks][GR.iijj].T

    if output_fields['VORT']:
        VORT_out = ncf.createVariable('VORT', 'f4',
                                    ('time', 'level', 'lat', 'lon',) )
        VORT_out[-1,:,:,:] = VORT[:,:,:][GR.ii,GR.jj].T


    if output_fields['WVP']:
        WVP_out = ncf.createVariable('WVP', 'f4', ('time', 'lat', 'lon',) )
        WVP_out[-1,:,:] = WVP.T

    if output_fields['CWP']:
        CWP_out = ncf.createVariable('CWP', 'f4', ('time', 'lat', 'lon',) )
        CWP_out[-1,:,:] = CWP.T


    ###########################################################################
    # PROFILES OF CERTAIN FIELDS
    ###########################################################################

    if output_fields['UWIND'] > 1:
        UWINDprof_out = ncf.createVariable('UWINDprof', 'f4',
                                            ('time', 'level', 'lat',) )
    if output_fields['VWIND'] > 1:
        VWINDprof_out = ncf.createVariable('VWINDprof', 'f4',
                                            ('time', 'level', 'lats',) )
    if output_fields['WWIND'] > 1:
        WWINDprof_out = ncf.createVariable('WWINDprof', 'f4',
                                            ('time', 'levels', 'lat',) )
    if output_fields['VORT'] > 1:
        VORTprof_out = ncf.createVariable('VORTprof', 'f4',
                                            ('time', 'level', 'lat',) )
    if output_fields['POTT'] > 1:
        POTTprof_out = ncf.createVariable('POTTprof', 'f4',
                                            ('time', 'level', 'lat',) )
    if output_fields['TAIR'] > 1:
        TAIRprof_out = ncf.createVariable('TAIRprof', 'f4',
                                            ('time', 'level', 'lat',) )
    if output_fields['QV'] > 1:
        QVprof_out = ncf.createVariable('QVprof', 'f4',
                                            ('time', 'level', 'lat',) )
    if output_fields['QC'] > 1:
        QCprof_out = ncf.createVariable('QCprof', 'f4',
                                            ('time', 'level', 'lat',) )
    for k in range(0,GR.nz):
        if output_fields['UWIND'] > 1:
            UWINDprof_out[-1,GR.nz-k-1,:] = np.mean(
                        F.host['UWIND'][GR.iis,GR.jj,k],axis=0)
        if output_fields['VWIND'] > 1:
            VWINDprof_out[-1,GR.nz-k-1,:] = np.mean(
                        F.host['VWIND'][GR.ii,GR.jjs,k],axis=0)
        if output_fields['VORT'] > 1:
            VORTprof_out[-1,GR.nz-k-1,:] = np.mean(
                        VORT[GR.ii,GR.jj,k],axis=0)
        if output_fields['POTT'] > 1:
            POTTprof_out[-1,GR.nz-k-1,:] = np.mean(
                        F.host['POTT'][GR.ii,GR.jj,k],axis=0)
        if output_fields['TAIR'] > 1:
            TAIRprof_out[-1,GR.nz-k-1,:] = np.mean(
                        F.host['TAIR'][GR.ii,GR.jj,k],axis=0)
        if output_fields['QV'] > 1:
            QVprof_out[-1,GR.nz-k-1,:] = np.mean(
                        F.host['QV'][GR.ii,GR.jj,k],axis=0)
        if output_fields['QC'] > 1:
            QCprof_out[-1,GR.nz-k-1,:] = np.mean(
                        F.host['QC'][GR.ii,GR.jj,k],axis=0)
    for k in range(0,GR.nzs):
        if output_fields['WWIND'] > 1:
            WWINDprof_out[-1,GR.nzs-k-1,:] = np.mean(
                        F.host['WWIND'][GR.ii,GR.jj,k],axis=0)







    # RADIATION VARIABLES
    if i_radiation:
        SWDIFFLXDO_out =ncf.createVariable('SWDIFFLXDO', 'f4', ('time', 'levels', 'lat', 'lon',) )
        SWDIRFLXDO_out =ncf.createVariable('SWDIRFLXDO', 'f4', ('time', 'levels', 'lat', 'lon',) )
        SWFLXUP_out = ncf.createVariable('SWFLXUP', 'f4', ('time', 'levels', 'lat', 'lon',) )
        SWFLXDO_out = ncf.createVariable('SWFLXDO', 'f4', ('time', 'levels', 'lat', 'lon',) )
        SWFLXNET_out = ncf.createVariable('SWFLXNET', 'f4', ('time', 'levels', 'lat', 'lon',) )
        LWFLXUP_out = ncf.createVariable('LWFLXUP', 'f4', ('time', 'levels', 'lat', 'lon',) )
        LWFLXDO_out = ncf.createVariable('LWFLXDO', 'f4', ('time', 'levels', 'lat', 'lon',) )
        LWFLXNET_out = ncf.createVariable('LWFLXNET', 'f4', ('time', 'levels', 'lat', 'lon',) )
        dPOTTdt_RAD_out=ncf.createVariable('dPOTTdt_RAD', 'f4', ('time', 'level', 'lat', 'lon',) )
        #SWFLXDIV_out = ncf.createVariable('SWFLXDIV', 'f4', ('time', 'level', 'lat', 'lon',) )
        #LWFLXDIV_out = ncf.createVariable('LWFLXDIV', 'f4', ('time', 'level', 'lat', 'lon',) )

    # SURF VARIABLES
    if i_surface_scheme:

        # create variables
        SURFTEMP_out = ncf.createVariable('SURFTEMP', 'f4', ('time', 'lat', 'lon',) )

        # fill in values
        if output_fields['SURFTEMP']:
            SURFTEMP_out[-1,:,:] = F.host['SOILTEMP'][GR.ii,GR.jj,0].T

        #if i_microphysics:
        #    SOILMOIST_out[-1,:,:] = SURF.MOIST.T
        #    RAINRATE_out[-1,:,:] = SURF.RAINRATE.T*3600 # mm/h
        #    ACCRAIN_out[-1,:,:] = SURF.ACCRAIN.T # mm
        #    SOILEVAPITY_out[-1,:,:] = SURF.SOILEVAPITY.T
        #if i_microphysics:
        #    SOILMOIST_out = ncf.createVariable('SOILMOIST', 'f4', ('time', 'lat', 'lon',) )
        #    RAINRATE_out = ncf.createVariable('RAINRATE', 'f4', ('time', 'lat', 'lon',) )
        #    ACCRAIN_out = ncf.createVariable('ACCRAIN', 'f4', ('time', 'lat', 'lon',) )
        #    SOILEVAPITY_out = ncf.createVariable('SOILEVAPITY', 'f4', ('time', 'lat', 'lon',) )
        if output_fields['SURFALBEDSW']:
            SURFALBEDSW_out = ncf.createVariable('SURFALBEDSW', 'f4',
                                                ('time', 'lat', 'lon',) )
            SURFALBEDSW_out[0,:,:] = F.host['SURFALBEDSW'][GR.ii,GR.jj,0].T
        if output_fields['SURFALBEDLW']:
            SURFALBEDLW_out = ncf.createVariable('SURFALBEDLW', 'f4',
                                                ('time', 'lat', 'lon',) )
            SURFALBEDLW_out[0,:,:] = F.host['SURFALBEDLW'][GR.ii,GR.jj,0].T


    ## MICROPHYSICS VARIABLES
    #if i_microphysics:
    #    dQVdt_MIC_out  = ncf.createVariable('dQVdt_MIC', 'f4',
    #                                        ('time', 'level', 'lat', 'lon',) )
    #    dQCdt_MIC_out  = ncf.createVariable('dQCdt_MIC', 'f4',
    #                                        ('time', 'level', 'lat', 'lon',) )
    #    dPOTTdt_MIC_out=ncf.createVariable('dPOTTdt_MIC', 'f4',
    #                                        ('time', 'level', 'lat', 'lon',) )



    ###########################################################################
    ###########################################################################

    for k in range(0,GR.nz):

        # RADIATION VARIABLES
        if i_radiation > 0:
            dPOTTdt_RAD_out[-1,k,:,:] = F.host['dPOTTdt_RAD'][
                                            GR.ii,GR.jj,k].T * 3600
            #SWFLXDIV_out[-1,k,:,:] = F.host['SWFLXDIV'][GR.ii,GR.jj,k].T 
            #LWFLXDIV_out[-1,k,:,:] = F.host['LWFLXDIV'][GR.ii,GR.jj,k].T 

        ## MICROPHYSICS VARIABLES
        #if i_microphysics:
        #    RH_out[-1,k,:,:] = MIC.RH[:,:,k].T
        #    dQVdt_MIC_out[-1,k,:,:] = F.dQVdt_MIC[GR.ii,GR.jj,k].T * 3600
        #    dQCdt_MIC_out[-1,k,:,:] = F.dQCdt_MIC[GR.ii,GR.jj,k].T * 3600
        #    dPOTTdt_MIC_out[-1,k,:,:] = F.dPOTTdt_MIC[GR.ii,GR.jj,k].T * 3600



    for ks in range(0,GR.nzs):


        # RADIATION VARIABLES
        if i_radiation > 0:
            SWDIFFLXDO_out[-1,ks,:,:] = F.host['SWDIFFLXDO'][GR.ii,GR.jj,ks].T
            SWDIRFLXDO_out[-1,ks,:,:] = F.host['SWDIRFLXDO'][GR.ii,GR.jj,ks].T
            SWFLXUP_out[-1,ks,:,:] = F.host['SWFLXUP'][GR.ii,GR.jj,ks].T
            SWFLXDO_out[-1,ks,:,:] = F.host['SWFLXDO'][GR.ii,GR.jj,ks].T
            SWFLXNET_out[-1,ks,:,:] = F.host['SWFLXNET'][GR.ii,GR.jj,ks].T
            LWFLXUP_out[-1,ks,:,:] = F.host['LWFLXUP'][GR.ii,GR.jj,ks].T
            LWFLXDO_out[-1,ks,:,:] = F.host['LWFLXDO'][GR.ii,GR.jj,ks].T
            LWFLXNET_out[-1,ks,:,:] = F.host['LWFLXNET'][GR.ii,GR.jj,ks].T


    ncf.close()




def constant_fields_to_NC(GR, F):

    print('###########################################')
    print('###########################################')
    print('write constant fields')
    print('###########################################')
    print('###########################################')

    Path(output_path).mkdir(exist_ok=True)
    filename = output_path+'/constants.nc'

    ncf = Dataset(filename, 'w', format='NETCDF4')
    ncf.close()

    ncf = Dataset(filename, 'a', format='NETCDF4')

    # DIMENSIONS
    lon_dim = ncf.createDimension('lon', GR.nx)
    lons_dim = ncf.createDimension('lons', GR.nxs)
    lat_dim = ncf.createDimension('lat', GR.ny)
    lats_dim = ncf.createDimension('lats', GR.nys)
    level_dim = ncf.createDimension('level', GR.nz)
    levels_dim = ncf.createDimension('levels', GR.nzs)

    # DIMENSION VARIABLES
    lon = ncf.createVariable('lon', 'f4', ('lon',) )
    lons = ncf.createVariable('lons', 'f4', ('lons',) )
    lat = ncf.createVariable('lat', 'f4', ('lat',) )
    lats = ncf.createVariable('lats', 'f4', ('lats',) )
    level = ncf.createVariable('level', 'f4', ('level',) )
    levels = ncf.createVariable('levels', 'f4', ('levels',) )

    lon[:] = GR.lon_rad[GR.ii,GR.nb+1,0]
    lons[:] = GR.lon_is_rad[GR.iis,GR.nb+1,0]
    lat[:] = GR.lat_rad[GR.nb+1,GR.jj,0]
    lats[:] = GR.lat_js_rad[GR.nb+1,GR.jjs,0]
    level[:] = GR.level
    levels[:] = GR.levels


    # VARIABLES
    HSURF_out = ncf.createVariable('HSURF', 'f4', ('lat', 'lon',) )
    HSURF_out[:,:] = F.host['HSURF'][GR.ii,GR.jj,0].T

    # SURF VARIABLES
    if i_surface_scheme:
        OCEANMASK_out = ncf.createVariable('OCEANMASK', 'f4', ('lat', 'lon',) )
        OCEANMASK_out[:,:] = F.host['OCEANMASK'][GR.ii,GR.jj,0].T

    # RADIATION VARIABLES
    ncf.close()


