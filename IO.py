import numpy as np
import time
from netCDF4 import Dataset
from scipy.interpolate import interp2d
from boundaries import exchange_BC_rigid_y, exchange_BC_periodic_x
import pickle
import os
from namelist import pTop, n_topo_smooth, tau_topo_smooth, \
                    output_path
from geopotential import diag_pvt_factor
from constants import con_kappa
from functions import IO_diagnostics
from scipy import interpolate


def output_to_NC(GR, outCounter, COLP, PAIR, PHI, UWIND, VWIND, WIND, WWIND,
                HSURF, POTT, TAIR, RHO, PVTF, PVTFVB, RAD, SOIL):

    t_start = time.time()

    print('###########################################')
    print('###########################################')
    print('write fields')
    print('###########################################')
    print('###########################################')

    VORT, PAIR, TAIR, WWIND_ms = IO_diagnostics(GR, UWIND, 
                        VWIND, WWIND, POTT, COLP, PVTF, PVTFVB,
                        PHI)

    filename = output_path+'/out'+str(outCounter).zfill(4)+'.nc'

    ncf = Dataset(filename, 'w', format='NETCDF4')
    ncf.close()

    ncf = Dataset(filename, 'a', format='NETCDF4')

    # DIMENSIONS
    time_dim = ncf.createDimension('time', None)
    #bnds_dim = ncf.createDimension('bnds', 2)
    bnds_dim = ncf.createDimension('bnds', 1)
    lon_dim = ncf.createDimension('lon', GR.nx)
    lons_dim = ncf.createDimension('lons', GR.nxs)
    lat_dim = ncf.createDimension('lat', GR.ny)
    lats_dim = ncf.createDimension('lats', GR.nys)
    level_dim = ncf.createDimension('level', GR.nz)
    levels_dim = ncf.createDimension('levels', GR.nzs)

    # DIMENSION VARIABLES
    dtime = ncf.createVariable('time', 'f8', ('time',) )
    bnds = ncf.createVariable('bnds', 'f8', ('bnds',) )
    lon = ncf.createVariable('lon', 'f4', ('lon',) )
    lons = ncf.createVariable('lons', 'f4', ('lons',) )
    lat = ncf.createVariable('lat', 'f4', ('lat',) )
    lats = ncf.createVariable('lats', 'f4', ('lats',) )
    level = ncf.createVariable('level', 'f4', ('level',) )
    levels = ncf.createVariable('levels', 'f4', ('levels',) )

    dtime[:] = GR.sim_time_sec/3600/24
    #bnds[:] = [0,1]
    bnds[:] = [0]
    lon[:] = GR.lon_rad[GR.ii,GR.nb+1]
    lons[:] = GR.lonis_rad[GR.iis,GR.nb+1]
    lat[:] = GR.lat_rad[GR.nb+1,GR.jj]
    lats[:] = GR.latjs_rad[GR.nb+1,GR.jjs]
    level[:] = GR.level
    levels[:] = GR.levels

    # VARIABLES
    HSURF_out = ncf.createVariable('HSURF', 'f4', ('bnds', 'lat', 'lon',) )
    PSURF_out = ncf.createVariable('PSURF', 'f4', ('time', 'lat', 'lon',) )
    PAIR_out = ncf.createVariable('PAIR', 'f4', ('time', 'level', 'lat', 'lon',) )
    PHI_out = ncf.createVariable('PHI', 'f4', ('time', 'level', 'lat', 'lon',) )
    UWIND_out = ncf.createVariable('UWIND', 'f4', ('time', 'level', 'lat', 'lons',) )
    VWIND_out = ncf.createVariable('VWIND', 'f4', ('time', 'level', 'lats', 'lon',) )
    WIND_out = ncf.createVariable('WIND', 'f4', ('time', 'level', 'lat', 'lon',) )
    VORT_out = ncf.createVariable('VORT', 'f4', ('time', 'level', 'lat', 'lon',) )
    WWIND_out = ncf.createVariable('WWIND', 'f4', ('time', 'levels', 'lat', 'lon',) )
    POTT_out = ncf.createVariable('POTT', 'f4', ('time', 'level', 'lat', 'lon',) )
    POTTprof_out = ncf.createVariable('POTTprof', 'f4', ('time', 'level', 'lat',) )
    TAIR_out = ncf.createVariable('TAIR', 'f4', ('time', 'level', 'lat', 'lon',) )
    RHO_out = ncf.createVariable('RHO', 'f4', ('time', 'level', 'lat', 'lon',) )

    # RADIATION VARIABLES
    SWINTOA_out = ncf.createVariable('SWINTOA', 'f4', ('time', 'lat', 'lon',) )
    LWOUTOA_out = ncf.createVariable('LWOUTOA', 'f4', ('time', 'lat', 'lon',) )

    # SOIL VARIABLES
    TSURF_out = ncf.createVariable('TSURF', 'f4', ('time', 'lat', 'lon',) )

    HSURF_out[0,:,:] = HSURF[GR.iijj].T
    PSURF_out[-1,:,:] = COLP[GR.iijj].T + pTop
    TSURF_out[-1,:,:] = SOIL.TSOIL[:,:,0].T
    for k in range(0,GR.nz):
        PAIR_out[-1,k,:,:] = PAIR[:,:,k][GR.iijj].T
        PHI_out[-1,k,:,:] = PHI[:,:,k][GR.iijj].T
        UWIND_out[-1,k,:,:] = UWIND[:,:,k][GR.iisjj].T
        VWIND_out[-1,k,:,:] = VWIND[:,:,k][GR.iijjs].T
        WIND_out[-1,k,:,:] = WIND[:,:,k][GR.iijj].T
        VORT_out[-1,k,:,:] = VORT[:,:,k][GR.iijj].T
        POTT_out[-1,k,:,:] = POTT[:,:,k][GR.iijj].T
        POTTprof_out[-1,GR.nz-k-1,:] = np.mean(POTT[:,:,k][GR.iijj],axis=0)
        TAIR_out[-1,k,:,:] = TAIR[:,:,k][GR.iijj].T
        RHO_out[-1,k,:,:] = RHO[:,:,k][GR.iijj].T

        SWINTOA_out[-1,:,:] = RAD.SWINTOA.T
        LWOUTOA_out[-1,:,:] = -RAD.LWFLXNET[:,:,0].T

    for ks in range(0,GR.nzs):
        #WWIND_out[-1,ks,:,:] = WWIND[:,:,ks][GR.iijj].T*COLP[GR.iijj].T
        WWIND_out[-1,ks,:,:] = WWIND_ms[:,:,ks][GR.iijj].T
    #mean_wind_out[-1,:] = mean_wind

    ncf.close()


    t_end = time.time()
    GR.IO_comp_time += t_end - t_start


def load_profile(GR, COLP, HSURF, PSURF, PVTF, PVTFVB, POTT, TAIR):
    filename = 'verticalProfileTable.dat'
    profile = np.loadtxt(filename)
    #print(profile)
    zsurf_test = np.mean(HSURF[GR.iijj])
    top_ind = np.argwhere(profile[:,2] >= pTop).squeeze()[-1]
    ztop_test = profile[top_ind,0] + (profile[top_ind,2] - pTop)/ \
                            (profile[top_ind,4]*profile[top_ind,1])


    ks = np.arange(0,GR.nzs)
    z_vb_test = np.zeros(GR.nzs)
    p_vb_test = np.zeros(GR.nzs)
    rho_vb_test = np.zeros(GR.nzs)
    g_vb_test = np.zeros(GR.nzs)

    z_vb_test[0] = ztop_test
    z_vb_test[ks] = zsurf_test + (ztop_test - zsurf_test)*(1 - ks/GR.nz)

    rho_vb_test = np.interp(z_vb_test, profile[:,0], profile[:,4]) 
    g_vb_test = np.interp(z_vb_test, profile[:,0], profile[:,1]) 
    p_vb_test[0] = pTop
    ks = 1
    for ks in range(1,GR.nzs):
        p_vb_test[ks] = p_vb_test[ks-1] + \
                        rho_vb_test[ks]*g_vb_test[ks] * \
                        (z_vb_test[ks-1] - z_vb_test[ks])
    
    GR.sigma_vb = (p_vb_test - pTop)/(p_vb_test[-1] - pTop)
    GR.dsigma = np.diff(GR.sigma_vb)

    for i in GR.ii:
        for j in GR.jj:
            PSURF[i,j] = np.interp(HSURF[i,j], profile[:,0], profile[:,2])

    COLP[GR.iijj] = PSURF[GR.iijj] - pTop
    PVTF, PVTFVB = diag_pvt_factor(GR, COLP, PVTF, PVTFVB)

    PAIR =  np.full( (GR.nx +2*GR.nb, GR.ny +2*GR.nb, GR.nz ), np.nan)
    for k in range(0,GR.nz):
        PAIR[:,:,k][GR.iijj] = 100000*np.power(PVTF[:,:,k][GR.iijj], 1/con_kappa)

    interp = interpolate.interp1d(profile[:,2], profile[:,3])
    for i in GR.ii:
        for j in GR.jj:
            TAIR[i,j,:] = interp(PAIR[i,j,:])

    for k in range(0,GR.nz):
        POTT[:,:,k][GR.iijj] = TAIR[:,:,k][GR.iijj] * \
                np.power(100000/PAIR[:,:,k][GR.iijj], con_kappa)

    return(GR, COLP, PSURF, POTT, TAIR)


def write_restart(GR, COLP, PAIR, PHI, PHIVB, UWIND, VWIND, WIND, WWIND,\
                        UFLX, VFLX, UFLXMP, VFLXMP, \
                        HSURF, POTT, TAIR, RHO,\
                        POTTVB, PVTF, PVTFVB):
    filename = '../restart/'+str(GR.dlat_deg).zfill(2)+'.pkl'
    out = {}
    out['GR'] = GR
    out['COLP'] = COLP
    out['PAIR'] = PAIR
    out['PHI'] = PHI
    out['PHIVB'] = PHIVB
    out['UWIND'] = UWIND
    out['VWIND'] = VWIND
    out['WIND'] = WIND
    out['WWIND'] = WWIND
    out['UFLX'] = UFLX
    out['VFLX'] = VFLX
    out['UFLXMP'] = UFLXMP
    out['VFLXMP'] = VFLXMP
    out['HSURF'] = HSURF
    out['POTT'] = POTT
    out['TAIR'] = TAIR
    out['RHO'] = RHO
    out['POTTVB'] = POTTVB
    out['PVTF'] = PVTF
    out['PVTFVB'] = PVTFVB
    with open(filename, 'wb') as f:
        pickle.dump(out, f)

def load_restart_grid(dlat_deg):
    filename = '../restart/'+str(dlat_deg).zfill(2)+'.pkl'
    if os.path.exists(filename):
        with open(filename, 'rb') as f:
            inp = pickle.load(f)
    else:
        raise ValueError('Restart File does not exist.')
    GR = inp['GR']
    return(GR)

def load_restart_fields(GR):
    filename = '../restart/'+str(GR.dlat_deg).zfill(2)+'.pkl'
    if os.path.exists(filename):
        with open(filename, 'rb') as f:
            inp = pickle.load(f)
    COLP = inp['COLP']
    PAIR = inp['PAIR']
    PHI = inp['PHI']
    PHIVB = inp['PHIVB']
    UWIND = inp['UWIND']
    VWIND = inp['VWIND']
    WIND = inp['WIND']
    WWIND = inp['WWIND']
    UFLX = inp['UFLX']
    VFLX = inp['VFLX']
    UFLXMP = inp['UFLXMP']
    VFLXMP = inp['VFLXMP']
    HSURF = inp['HSURF']
    POTT = inp['POTT']
    TAIR = inp['TAIR']
    RHO = inp['RHO']
    POTTVB = inp['POTTVB']
    PVTF = inp['PVTF']
    PVTFVB = inp['PVTFVB']
    return(COLP, PAIR, PHI, PHIVB, UWIND, VWIND, WIND, WWIND, \
                UFLX, VFLX, UFLXMP, VFLXMP, \
                HSURF, POTT, TAIR, RHO, \
                POTTVB, PVTF, PVTFVB)



def load_topo(GR):
    HSURF = np.full( (GR.nx+2*GR.nb,GR.ny+2*GR.nb), np.nan)
    filename = '../elevation/elev.1-deg.nc'
    ncf = Dataset(filename, 'r', format='NETCDF4')
    lon_inp = ncf['lon'][:]
    lat_inp = ncf['lat'][:]
    hsurf_inp = ncf['data'][0,:,:]
    interp = interp2d(lon_inp, lat_inp, hsurf_inp)
    HSURF[GR.iijj] = interp(GR.lon_deg[GR.ii,GR.nb+1], GR.lat_deg[GR.nb+1,GR.jj]).T
    HSURF[HSURF < 0] = 0
    HSURF = exchange_BC_periodic_x(GR, HSURF)
    HSURF = exchange_BC_rigid_y(GR, HSURF)

    for i in range(0,n_topo_smooth):
        HSURF[GR.iijj] = HSURF[GR.iijj] + tau_topo_smooth*\
                                            (HSURF[GR.iijj_im1] + HSURF[GR.iijj_ip1] + \
                                            HSURF[GR.iijj_jm1] + HSURF[GR.iijj_jp1] - \
                                            4*HSURF[GR.iijj]) 
        HSURF = exchange_BC_periodic_x(GR, HSURF)
        HSURF = exchange_BC_rigid_y(GR, HSURF)

    return(HSURF)


