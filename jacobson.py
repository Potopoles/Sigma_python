import copy
import numpy as np
import time
from continuity import colp_tendency_jacobson, vertical_wind_jacobson
from wind import wind_tendency_jacobson
#from wind import wind_tendency_jacobson_par
from wind_cython import wind_tendency_jacobson_par
from temperature import temperature_tendency_jacobson
from geopotential import diag_geopotential_jacobson
from boundaries import exchange_BC
from moisture import water_vapor_tendency, cloud_water_tendency
from namelist import pTop, njobs
from constants import con_Rd

# parallel
import multiprocessing as mp

def tendencies_jacobson(GR, subgrids,\
                    COLP, POTT, POTTVB, HSURF,
                    UWIND, VWIND, WWIND,
                    UFLX, VFLX, PHI, PVTF, PVTFVB,
                    RAD, MIC, TURB):

    # PROGNOSE COLP
    dCOLPdt, UFLX, VFLX, FLXDIV = colp_tendency_jacobson(GR, COLP, UWIND,\
                                                        VWIND, UFLX, VFLX)
    COLP_NEW = copy.deepcopy(COLP)
    COLP_NEW[GR.iijj] = COLP[GR.iijj] + GR.dt*dCOLPdt
    COLP_NEW = exchange_BC(GR, COLP_NEW)

    # DIAGNOSE WWIND
    WWIND = vertical_wind_jacobson(GR, COLP_NEW, dCOLPdt, FLXDIV, WWIND)

    # PROGNOSE WIND
    t_start = time.time()
    #for q in range(0,5):
    dUFLXdt, dVFLXdt = wind_tendency_jacobson(GR, UWIND, VWIND, WWIND, UFLX, VFLX, 
                                                    COLP, COLP_NEW, HSURF, PHI, POTT,
                                                    PVTF, PVTFVB)

    t_end = time.time()
    print(t_end - t_start)
    #print(dUFLXdt)
    import pickle
    out = {}
    out['dUFLXdt'] = dUFLXdt
    out['dVFLXdt'] = dVFLXdt
    with open('testarray.pkl', 'wb') as f:
        pickle.dump(out, f)
    #print(dUFLXdt)
    quit()

        #dUFLXdt, dVFLXdt = wind_tendency_jacobson_par(GR, UWIND, VWIND, WWIND, UFLX, VFLX, 
        #                                                COLP, COLP_NEW, HSURF, PHI, POTT,
        #                                                PVTF, PVTFVB)


        #output = mp.Queue()
        #processes = []
        #for job_ind in range(0,njobs):

        #    SGR = subgrids[job_ind]
        #    processes.append(
        #        mp.Process(\
        #            target=wind_tendency_jacobson_par,
        #            args = (job_ind, output, subgrids[job_ind],
        #                    UWIND[SGR.map_iisjj], VWIND[SGR.map_iijjs],
        #                    WWIND[SGR.map_iijj], 
        #                    UFLX[SGR.map_iisjj], VFLX[SGR.map_iijjs],
        #                    COLP[SGR.map_iijj], COLP_NEW[SGR.map_iijj],
        #                    HSURF[SGR.map_iijj], PHI[SGR.map_iijj],
        #                    POTT[SGR.map_iijj], PVTF[SGR.map_iijj],
        #                    PVTFVB[SGR.map_iijj])))
        #for proc in processes:
        #    proc.start()
        #results = [output.get() for p in processes]
        #results.sort()
        #dUFLXdt = np.zeros( (GR.nxs, GR.ny, GR.nz) )
        #dVFLXdt = np.zeros( (GR.nx, GR.nys, GR.nz) )
        #for job_ind in range(0,njobs):
        #    SGR = subgrids[job_ind]
        #    res = results[job_ind][1]

        #    dUFLXdt[SGR.mapin_iisjj] = results[job_ind][1]['dUFLXdt']
        #    dVFLXdt[SGR.mapin_iijjs] = results[job_ind][1]['dVFLXdt']

        #for proc in processes:
        #    proc.join()

    t_end = time.time()
    GR.wind_comp_time += t_end - t_start
    #print(t_end - t_start)
    #quit()

    # PROGNOSE POTT
    dPOTTdt = temperature_tendency_jacobson(GR, POTT, POTTVB, COLP, COLP_NEW,\
                                            UFLX, VFLX, WWIND, RAD, MIC)

    # MOIST VARIABLES
    dQVdt = water_vapor_tendency(GR, MIC.QV, COLP, COLP_NEW, UFLX, VFLX, WWIND, MIC, TURB)
    dQCdt = cloud_water_tendency(GR, MIC.QC, COLP, COLP_NEW, UFLX, VFLX, WWIND, MIC)

    return(dCOLPdt, dUFLXdt, dVFLXdt, dPOTTdt, WWIND, dQVdt, dQCdt)


def proceed_timestep_jacobson(GR, UWIND, VWIND,
                    COLP, POTT, QV, QC,
                    dCOLPdt, dUFLXdt, dVFLXdt, dPOTTdt, dQVdt, dQCdt):

    # TIME STEPPING
    COLP_OLD = copy.deepcopy(COLP)
    COLPA_is_OLD, COLPA_js_OLD = interp_COLPA(GR, COLP_OLD)

    COLP[GR.iijj] = COLP[GR.iijj] + GR.dt*dCOLPdt
    COLP = exchange_BC(GR, COLP)
    COLPA_is_NEW, COLPA_js_NEW = interp_COLPA(GR, COLP)

    for k in range(0,GR.nz):
        UWIND[:,:,k][GR.iisjj] = UWIND[:,:,k][GR.iisjj] * COLPA_is_OLD/COLPA_is_NEW \
                            + GR.dt*dUFLXdt[:,:,k]/COLPA_is_NEW
        VWIND[:,:,k][GR.iijjs] = VWIND[:,:,k][GR.iijjs] * COLPA_js_OLD/COLPA_js_NEW \
                            + GR.dt*dVFLXdt[:,:,k]/COLPA_js_NEW
        #VWIND[:,:,k][GR.ii,GR.nb] = 0
        #VWIND[:,:,k][GR.ii,-1-GR.nb] = 0
        POTT[:,:,k][GR.iijj] = POTT[:,:,k][GR.iijj] * COLP_OLD[GR.iijj]/COLP[GR.iijj] \
                            + GR.dt*dPOTTdt[:,:,k]/COLP[GR.iijj]
        QV[:,:,k][GR.iijj] = QV[:,:,k][GR.iijj] * COLP_OLD[GR.iijj]/COLP[GR.iijj] \
                            + GR.dt*dQVdt[:,:,k]/COLP[GR.iijj]
        QC[:,:,k][GR.iijj] = QC[:,:,k][GR.iijj] * COLP_OLD[GR.iijj]/COLP[GR.iijj] \
                            + GR.dt*dQCdt[:,:,k]/COLP[GR.iijj]
    UWIND = exchange_BC(GR, UWIND)
    VWIND = exchange_BC(GR, VWIND)
    POTT = exchange_BC(GR, POTT)
    QV[QV < 0] = 0
    QV = exchange_BC(GR, QV)
    QC[QC < 0] = 0
    QC = exchange_BC(GR, QC)

    return(UWIND, VWIND, COLP, POTT, QV, QC)


def diagnose_fields_jacobson(GR, PHI, PHIVB, COLP, POTT, HSURF, PVTF, PVTVB, POTTVB, TURB):

    t_start = time.time()

    PHI, PHIVB, PVTF, PVTFVB = diag_geopotential_jacobson(GR, PHI, PHIVB, HSURF, 
                                                POTT, COLP, PVTF, PVTVB)

    for ks in range(1,GR.nzs-1):
        POTTVB[:,:,ks][GR.iijj] =   ( \
                    +   (PVTFVB[:,:,ks][GR.iijj] - PVTF[:,:,ks-1][GR.iijj]) * \
                        POTT[:,:,ks-1][GR.iijj]
                    +   (PVTF[:,:,ks][GR.iijj] - PVTFVB[:,:,ks][GR.iijj]) * \
                        POTT[:,:,ks][GR.iijj]
                                    ) / (PVTF[:,:,ks][GR.iijj] - PVTF[:,:,ks-1][GR.iijj])

    # extrapolate model bottom and model top POTTVB
    POTTVB[:,:,0][GR.iijj] = POTT[:,:,0][GR.iijj] - \
            ( POTTVB[:,:,1][GR.iijj] - POTT[:,:,0][GR.iijj] )
    POTTVB[:,:,-1][GR.iijj] = POTT[:,:,-1][GR.iijj] - \
            ( POTTVB[:,:,-2][GR.iijj] - POTT[:,:,-1][GR.iijj] )

    TURB.diag_rho(GR, COLP, POTT, PVTF, POTTVB, PVTFVB)
    TURB.diag_dz(GR, PHI, PHIVB)

    t_end = time.time()
    GR.diag_comp_time += t_end - t_start

    return(PHI, PHIVB, PVTF, PVTFVB, POTTVB, TURB)




def interp_COLPA(GR, COLP):

    COLPA_is = 1/8*(    COLP[GR.iisjj_im1_jp1] * GR.A[GR.iisjj_im1_jp1] + \
                        COLP[GR.iisjj_jp1    ] * GR.A[GR.iisjj_jp1    ] + \
                    2 * COLP[GR.iisjj_im1    ] * GR.A[GR.iisjj_im1    ] + \
                    2 * COLP[GR.iisjj        ] * GR.A[GR.iisjj        ] + \
                        COLP[GR.iisjj_im1_jm1] * GR.A[GR.iisjj_im1_jm1] + \
                        COLP[GR.iisjj_jm1    ] * GR.A[GR.iisjj_jm1    ]   )

    # ATTEMPT TO INTERPOLATE ONLY WITH TWO NEIGHBORING POINTS
    #COLPA_is[:, 0] = 1/2*( COLP[GR.iis-1,GR.jj[ 0]] * GR.A[GR.iis-1,GR.jj[ 0]] + \
    #                       COLP[GR.iis  ,GR.jj[ 0]] * GR.A[GR.iis  ,GR.jj[ 0]]   )
    #COLPA_is[:,-1] = 1/2*( COLP[GR.iis-1,GR.jj[-1]] * GR.A[GR.iis-1,GR.jj[-1]] + \
    #                       COLP[GR.iis  ,GR.jj[-1]] * GR.A[GR.iis  ,GR.jj[-1]]   )

    # ATTEMPT TO SET BOUNDARY AREA TO ZERO (see grid)
    # consequently change 1/8 to 1/6
    #COLPA_is[:, 0] = COLPA_is[:, 0]*4/3
    #COLPA_is[:, -1] = COLPA_is[:, -1]*4/3

    # ATTEMPT TO INTERPOLATE ONLY WITH TWO NEIGHBORING POINTS (JACOBSON)
    COLPA_is[:,-1] = 1/4*(    COLP[GR.iis-1,GR.jj[-1]] * GR.A[GR.iis-1,GR.jj[-1]] + \
                              COLP[GR.iis  ,GR.jj[-1]] * GR.A[GR.iis  ,GR.jj[-1]] + \
                              COLP[GR.iis-1,GR.jj[-2]] * GR.A[GR.iis-1,GR.jj[-2]] + \
                              COLP[GR.iis  ,GR.jj[-2]] * GR.A[GR.iis  ,GR.jj[-2]]   )

    COLPA_is[:, 0] = 1/4*(    COLP[GR.iis-1,GR.jj[0]] * GR.A[GR.iis-1,GR.jj[0]] + \
                              COLP[GR.iis  ,GR.jj[0]] * GR.A[GR.iis  ,GR.jj[0]] + \
                              COLP[GR.iis-1,GR.jj[1]] * GR.A[GR.iis-1,GR.jj[1]] + \
                              COLP[GR.iis  ,GR.jj[1]] * GR.A[GR.iis  ,GR.jj[1]]   )




    COLPA_js = 1/8*(    COLP[GR.iijjs_ip1_jm1] * GR.A[GR.iijjs_ip1_jm1] + \
                        COLP[GR.iijjs_ip1    ] * GR.A[GR.iijjs_ip1    ] + \
                    2 * COLP[GR.iijjs_jm1    ] * GR.A[GR.iijjs_jm1    ] + \
                    2 * COLP[GR.iijjs        ] * GR.A[GR.iijjs        ] + \
                        COLP[GR.iijjs_im1_jm1] * GR.A[GR.iijjs_im1_jm1] + \
                        COLP[GR.iijjs_im1    ] * GR.A[GR.iijjs_im1    ]   )


    return(COLPA_is, COLPA_js)




