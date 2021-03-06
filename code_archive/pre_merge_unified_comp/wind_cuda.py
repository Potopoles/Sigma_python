import time
import numpy as np
from boundaries_cuda import exchange_BC_gpu
from constants import con_cp, con_rE, con_Rd
from namelist import (UVFLX_dif_coef,
                    i_UVFLX_main_switch,
                    i_UVFLX_hor_adv, i_UVFLX_vert_adv,
                    i_UVFLX_coriolis,
                    i_UVFLX_num_dif, i_UVFLX_pre_grad)
from org_namelist import wp_old
from numba import cuda, jit
from math import cos, sin


def wind_tendency_jacobson_gpu(GR, UWIND, VWIND, WWIND, UFLX, dUFLXdt, VFLX, dVFLXdt,
                                BFLX, CFLX, DFLX, EFLX, RFLX, QFLX, SFLX, TFLX, 
                                WWIND_UWIND, WWIND_VWIND,
                                COLP, COLP_NEW, PHI, POTT, PVTF, PVTFVB):

    stream = GR.stream

    set_to[GR.griddim_is, GR.blockdim, stream](dUFLXdt, 0.)
    stream.synchronize()
    set_to[GR.griddim_js, GR.blockdim, stream](dVFLXdt, 0.)
    stream.synchronize()

    if i_UVFLX_main_switch:

        #######################################################################
        #######################################################################
        #######################################################################
        #######################################################################

        # HORIZONTAL ADVECTION
        if i_UVFLX_hor_adv:
            # CALCULATE MOMENTUM FLUXES
            calc_fluxes_ij[GR.griddim, GR.blockdim, stream] \
                            (BFLX, RFLX, UFLX, VFLX)
            stream.synchronize()
            BFLX = exchange_BC_gpu(BFLX, GR.zonal, GR.merid, GR.griddim,
                                    GR.blockdim, stream)
            RFLX = exchange_BC_gpu(RFLX, GR.zonal, GR.merid, GR.griddim,
                                    GR.blockdim, stream)

            calc_fluxes_isj[GR.griddim_is, GR.blockdim, stream] \
                            (SFLX, TFLX, UFLX, VFLX)
            stream.synchronize()
            SFLX = exchange_BC_gpu(SFLX, GR.zonal, GR.merids, GR.griddim_is,
                                    GR.blockdim, stream, stagx=True)
            TFLX = exchange_BC_gpu(TFLX, GR.zonal, GR.merids, GR.griddim_is,
                                    GR.blockdim, stream, stagx=True)

            calc_fluxes_ijs[GR.griddim_js, GR.blockdim, stream] \
                            (DFLX, EFLX, UFLX, VFLX)
            stream.synchronize()
            DFLX = exchange_BC_gpu(DFLX, GR.zonals, GR.merid, GR.griddim_js,
                                    GR.blockdim, stream, stagy=True)
            EFLX = exchange_BC_gpu(EFLX, GR.zonals, GR.merid, GR.griddim_js,
                                    GR.blockdim, stream, stagy=True)

            calc_fluxes_isjs[GR.griddim_is_js, GR.blockdim, stream] \
                            (CFLX, QFLX, UFLX, VFLX)
            stream.synchronize()
            CFLX = exchange_BC_gpu(CFLX, GR.zonals, GR.merids, GR.griddim_is_js,
                                    GR.blockdim, stream, stagx=True, stagy=True)
            QFLX = exchange_BC_gpu(QFLX, GR.zonals, GR.merids, GR.griddim_is_js,
                                    GR.blockdim, stream, stagx=True, stagy=True)

        # VERTICAL ADVECTION
        if i_UVFLX_vert_adv:
            calc_WWIND_VWIND[GR.griddim_js_ks, GR.blockdim_ks, stream] \
                                (WWIND_VWIND, VWIND, COLP_NEW, WWIND, GR.Ad, 
                                GR.dsigmad)
            stream.synchronize()
            calc_WWIND_UWIND[GR.griddim_is_ks, GR.blockdim_ks, stream] \
                                (WWIND_UWIND, UWIND, COLP_NEW, WWIND, GR.Ad, 
                                GR.dsigmad)
            #stream.synchronize()
            #print(np.asarray(WWIND_UWIND))
            #quit()

        #######################################################################
        #######################################################################
        #######################################################################
        #######################################################################

        run_UWIND[GR.griddim_is, GR.blockdim, stream] \
                        (dUFLXdt, UWIND, VWIND, COLP,
                        UFLX, BFLX, CFLX, DFLX, EFLX,
                        PHI, POTT, PVTF, PVTFVB, WWIND_UWIND,
                        GR.corf_isd, GR.lat_is_radd, GR.dlon_rad,
                        GR.dsigmad, GR.sigma_vbd, GR.dy)
        stream.synchronize()

        run_VWIND[GR.griddim_js, GR.blockdim, stream] \
                        (dVFLXdt, UWIND, VWIND, COLP,
                        VFLX, RFLX, QFLX, SFLX, TFLX,
                        PHI, POTT, PVTF, PVTFVB, WWIND_VWIND,
                        GR.corfd, GR.lat_radd, GR.dlon_rad,
                        GR.dsigmad, GR.sigma_vbd, GR.dxjsd)
        stream.synchronize()

        #######################################################################
        #######################################################################
        #######################################################################
        #######################################################################

    return(dUFLXdt, dVFLXdt)


@jit([wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:  ], '+ \
      wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+ \
      wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+ \
      wp_old+'[:,:  ], '+wp_old+'[:,:  ], '+wp_old+', '+ \
      wp_old+'[:    ], '+wp_old+'[:    ], '+wp_old], target='gpu')
def run_UWIND(dUFLXdt, UWIND, VWIND, COLP,
                UFLX, BFLX, CFLX, DFLX, EFLX,
                PHI, POTT, PVTF, PVTFVB, WWIND_UWIND,
                corf_is, latis_rad, dlon_rad,
                dsigma, sigma_vb, dy):
    nx = dUFLXdt.shape[0] - 2
    ny = dUFLXdt.shape[1] - 2
    i, j, k = cuda.grid(3)
    if i > 0 and i < nx+1 and j > 0 and j < ny+1:

        # HORIZONTAL ADVECTION
        if i_UVFLX_hor_adv:
            dUFLXdt[i  ,j  ,k] = dUFLXdt[i  ,j  ,k] + \
                    + BFLX [i-1,j  ,k] * \
                    ( UWIND[i-1,j  ,k] + UWIND[i  ,j  ,k] )/2. \
                    - BFLX [i  ,j  ,k] * \
                    ( UWIND[i  ,j  ,k] + UWIND[i+1,j  ,k] )/2. \
                    \
                    + CFLX [i  ,j  ,k] * \
                    ( UWIND[i  ,j-1,k] + UWIND[i  ,j  ,k] )/2. \
                    - CFLX [i  ,j+1,k] * \
                    ( UWIND[i  ,j  ,k] + UWIND[i  ,j+1,k] )/2. \
                    \
                    + DFLX [i-1,j  ,k] * \
                    ( UWIND[i-1,j-1,k] + UWIND[i  ,j  ,k] )/2. \
                    - DFLX [i  ,j+1,k] * \
                    ( UWIND[i  ,j  ,k] + UWIND[i+1,j+1,k] )/2. \
                    \
                    + EFLX [i  ,j  ,k] * \
                    ( UWIND[i+1,j-1,k] + UWIND[i  ,j  ,k] )/2. \
                    - EFLX [i-1,j+1,k] * \
                    ( UWIND[i  ,j  ,k] + UWIND[i-1,j+1,k] )/2. 


        # VERTICAL ADVECTION
        if i_UVFLX_vert_adv:
            dUFLXdt[i  ,j  ,k] = dUFLXdt[i  ,j  ,k] + \
                                (WWIND_UWIND[i  ,j  ,k  ] - \
                                 WWIND_UWIND[i  ,j  ,k+1]  ) / dsigma[k]


        # CORIOLIS AND SPHERICAL GRID CONVERSION
        if i_UVFLX_coriolis:
            dUFLXdt[i  ,j  ,k] = dUFLXdt[i  ,j  ,k] + \
                con_rE*dlon_rad*dlon_rad/2.*(\
                  COLP [i-1,j    ] * \
                ( VWIND[i-1,j  ,k] + VWIND[i-1,j+1,k] )/2. * \
                ( corf_is[i  ,j  ] * con_rE *\
                  cos(latis_rad[i  ,j  ]) + \
                  ( UWIND[i-1,j  ,k] + UWIND[i  ,j  ,k] )/2. * \
                  sin(latis_rad[i  ,j  ]) )\
                + COLP [i  ,j    ] * \
                ( VWIND[i  ,j  ,k] + VWIND[i  ,j+1,k] )/2. * \
                ( corf_is[i  ,j  ] * con_rE * \
                  cos(latis_rad[i  ,j  ]) + \
                  ( UWIND[i  ,j  ,k] + UWIND[i+1,j  ,k] )/2. * \
                  sin(latis_rad[i  ,j  ]) )\
                )


        # PRESSURE GRADIENT
        if i_UVFLX_pre_grad:
            dUFLXdt[i  ,j  ,k] = dUFLXdt[i  ,j  ,k] + \
                 - dy * ( \
                ( PHI [i  ,j  ,k]  - PHI [i-1,j  ,k] ) * \
                ( COLP[i  ,j    ]  + COLP[i-1,j    ] )/2. + \
                ( COLP[i  ,j    ]  - COLP[i-1,j    ] ) * con_cp/2. * \
                (\
                  + POTT[i-1,j  ,k] / dsigma[k] * \
                    ( \
                        sigma_vb[k+1] * \
                        ( PVTFVB[i-1,j  ,k+1] - PVTF  [i-1,j  ,k] ) + \
                        sigma_vb[k  ] * \
                        ( PVTF  [i-1,j  ,k  ] - PVTFVB[i-1,j  ,k] )   \
                    ) \
                  + POTT[i  ,j  ,k] / dsigma[k] * \
                    ( \
                        sigma_vb[k+1] * \
                        ( PVTFVB[i  ,j  ,k+1] - PVTF  [i  ,j  ,k] ) + \
                        sigma_vb[k  ] * \
                        ( PVTF  [i  ,j  ,k  ] - PVTFVB[i  ,j  ,k] )   \
                    ) \
                ) )


        # HORIZONTAL DIFFUSION
        if i_UVFLX_num_dif and (UVFLX_dif_coef > 0):
            dUFLXdt[i  ,j  ,k] = dUFLXdt[i  ,j  ,k] + \
                                UVFLX_dif_coef * \
                             (  UFLX[i-1,j  ,k] + UFLX[i+1,j  ,k] \
                              + UFLX[i  ,j-1,k] + UFLX[i  ,j+1,k] \
                           - 4.*UFLX[i  ,j  ,k] )

    cuda.syncthreads()


@jit([wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:  ], '+ \
      wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+ \
      wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+ \
      wp_old+'[:,:  ], '+wp_old+'[:,:  ], '+wp_old+', '+ \
      wp_old+'[:    ], '+wp_old+'[:    ], '+wp_old+'[:,:  ]'], target='gpu')
def run_VWIND(dVFLXdt, UWIND, VWIND, COLP,
                VFLX, RFLX, QFLX, SFLX, TFLX,
                PHI, POTT, PVTF, PVTFVB, WWIND_VWIND,
                corf, lat_rad, dlon_rad,
                dsigma, sigma_vb, dxjs):
    nx = dVFLXdt.shape[0] - 2
    ny = dVFLXdt.shape[1] - 2
    i, j, k = cuda.grid(3)
    if i > 0 and i < nx+1 and j > 0 and j < ny+1:

        # HORIZONTAL ADVECTION
        if i_UVFLX_hor_adv:
            dVFLXdt[i  ,j  ,k] = dVFLXdt[i  ,j  ,k] + \
                      RFLX [i  ,j-1,k] * \
                    ( VWIND[i  ,j-1,k] + VWIND[i  ,j  ,k] )/2. \
                    - RFLX [i  ,j  ,k] * \
                    ( VWIND[i  ,j  ,k] + VWIND[i  ,j+1,k] )/2. \
                    \
                    + QFLX [i  ,j  ,k] * \
                    ( VWIND[i-1,j  ,k] + VWIND[i  ,j  ,k] )/2. \
                    - QFLX [i+1,j  ,k] * \
                    ( VWIND[i  ,j  ,k] + VWIND[i+1,j  ,k] )/2. \
                    \
                    + SFLX [i  ,j-1,k] * \
                    ( VWIND[i-1,j-1,k] + VWIND[i  ,j  ,k] )/2. \
                    - SFLX [i+1,j  ,k] * \
                    ( VWIND[i  ,j  ,k] + VWIND[i+1,j+1,k] )/2. \
                    \
                    + TFLX [i+1,j-1,k] * \
                    ( VWIND[i+1,j-1,k] + VWIND[i  ,j  ,k] )/2. \
                    - TFLX [i  ,j  ,k] * \
                    ( VWIND[i  ,j  ,k] + VWIND[i-1,j+1,k] )/2. 


        # VERTICAL ADVECTION
        if i_UVFLX_vert_adv:
            dVFLXdt[i  ,j  ,k] = dVFLXdt[i  ,j  ,k] + \
                                (WWIND_VWIND[i  ,j  ,k  ] - \
                                 WWIND_VWIND[i  ,j  ,k+1]  ) / dsigma[k]


        # CORIOLIS AND SPHERICAL GRID CONVERSION
        if i_UVFLX_coriolis:
            dVFLXdt[i  ,j  ,k] = dVFLXdt[i  ,j  ,k] + \
                 - con_rE*dlon_rad*dlon_rad/2.*(\
                  COLP[i  ,j-1  ] * \
                ( UWIND[i  ,j-1,k] + UWIND[i+1,j-1,k] )/2. * \
                ( corf[i  ,j-1  ] * con_rE *\
                  cos(lat_rad[i  ,j-1  ]) +\
                  ( UWIND[i  ,j-1,k] + UWIND[i+1,j-1,k] )/2. * \
                  sin(lat_rad[i  ,j-1  ]) )\

                + COLP [i  ,j    ] * \
                ( UWIND[i  ,j  ,k] + UWIND[i+1,j  ,k] )/2. * \
                ( corf [i  ,j    ] * con_rE *\
                  cos(lat_rad[i  ,j    ]) +\
                  ( UWIND[i  ,j  ,k] + UWIND[i+1,j  ,k] )/2. * \
                  sin(lat_rad[i  ,j    ]) )\
                )


        # PRESSURE GRADIENT
        if i_UVFLX_pre_grad:
            dVFLXdt[i  ,j  ,k] = dVFLXdt[i  ,j  ,k] + \
                - dxjs[i  ,j    ] * ( \
                ( PHI [i  ,j  ,k] - PHI [i  ,j-1,k] ) *\
                ( COLP[i  ,j    ] + COLP[i  ,j-1  ] )/2. + \
                ( COLP[i  ,j    ] - COLP[i  ,j-1  ] ) * con_cp/2. * \
                (\
                    POTT[i  ,j-1,k] / dsigma[k] * \
                    ( \
                        + sigma_vb[k+1] * \
                        ( PVTFVB[i  ,j-1,k+1] - PVTF  [i  ,j-1,k] ) \
                        + sigma_vb[k  ] * \
                        ( PVTF  [i  ,j-1,k  ] - PVTFVB[i  ,j-1,k] ) \
                    ) +\
                    POTT[i  ,j  ,k] / dsigma[k] * \
                    ( \
                        + sigma_vb[k+1] * \
                        ( PVTFVB[i  ,j  ,k+1] - PVTF  [i  ,j  ,k] ) \
                        + sigma_vb[k  ] * \
                        ( PVTF  [i  ,j  ,k  ] - PVTFVB[i  ,j  ,k] ) \
                    ) \
                ) )


        # HORIZONTAL DIFFUSION
        if i_UVFLX_num_dif and (UVFLX_dif_coef > 0):
            dVFLXdt[i  ,j  ,k] = dVFLXdt[i  ,j  ,k] + \
                                UVFLX_dif_coef * \
                             (  VFLX[i-1,j  ,k] + VFLX[i+1,j  ,k] \
                              + VFLX[i  ,j-1,k] + VFLX[i  ,j+1,k] \
                           - 4.*VFLX[i  ,j  ,k] )

    cuda.syncthreads()



@jit([wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:]'], target='gpu')
def calc_fluxes_ij(BFLX, RFLX, UFLX, VFLX):
    nx = BFLX.shape[0] - 2
    ny = BFLX.shape[1] - 2
    i, j, k = cuda.grid(3)
    if i > 0 and i < nx+1 and j > 0 and j < ny+1:
        BFLX[i  ,j  ,k] = 1./12. * (      UFLX[i  ,j-1,k] + \
                                          UFLX[i+1,j-1,k]   + \
                                     2.*( UFLX[i  ,j  ,k] + \
                                          UFLX[i+1,j  ,k] ) + \
                                          UFLX[i  ,j+1,k] + \
                                          UFLX[i+1,j+1,k]     )

        RFLX[i  ,j  ,k] = 1./12. * (      VFLX[i-1,j  ,k] + \
                                          VFLX[i-1,j+1,k]   +\
                                     2.*( VFLX[i  ,j  ,k] + \
                                          VFLX[i  ,j+1,k] ) +\
                                          VFLX[i+1,j  ,k] + \
                                          VFLX[i+1,j+1,k]    )
    cuda.syncthreads()

@jit([wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:]'], target='gpu')
def calc_fluxes_isj(SFLX, TFLX, UFLX, VFLX):
    nx = SFLX.shape[0] - 2
    ny = SFLX.shape[1] - 2
    i, j, k = cuda.grid(3)
    if i > 0 and i < nx+1 and j > 0 and j < ny+1:
        SFLX[i  ,j  ,k]  = 1./24. * (  VFLX[i-1,j  ,k]  + \
                                       VFLX[i-1,j+1,k] +\
                                       VFLX[i  ,j  ,k]  +   \
                                       VFLX[i  ,j+1,k] +\
                                       UFLX[i-1,j  ,k]  + \
                                    2.*UFLX[i  ,j  ,k] +\
                                       UFLX[i+1,j  ,k]   )

        TFLX[i  ,j  ,k]  = 1./24. * (  VFLX[i-1,j  ,k] + \
                                       VFLX[i-1,j+1,k] +\
                                       VFLX[i  ,j  ,k] + \
                                       VFLX[i  ,j+1,k] +\
                                     - UFLX[i-1,j  ,k] - \
                                    2.*UFLX[i  ,j  ,k] +\
                                     - UFLX[i+1,j  ,k]   )
    cuda.syncthreads()


@jit([wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:]'], target='gpu')
def calc_fluxes_ijs(DFLX, EFLX, UFLX, VFLX):
    nx = DFLX.shape[0] - 2
    ny = DFLX.shape[1] - 2
    i, j, k = cuda.grid(3)
    if i > 0 and i < nx+1 and j > 0 and j < ny+1:
        DFLX[i  ,j  ,k]  = 1./24. * (  VFLX[i  ,j-1,k]   + \
                                    2.*VFLX[i  ,j  ,k] +\
                                       VFLX[i  ,j+1,k]   + \
                                       UFLX[i  ,j-1,k]   +\
                                       UFLX[i  ,j  ,k]   + \
                                       UFLX[i+1,j-1,k]   +\
                                       UFLX[i+1,j  ,k]   )

        EFLX[i  ,j  ,k]  = 1./24. * (  VFLX[i  ,j-1,k]    + \
                                    2.*VFLX[i  ,j  ,k]  +\
                                       VFLX[i  ,j+1,k]    - \
                                       UFLX[i  ,j-1,k]    +\
                                     - UFLX[i  ,j  ,k]    - \
                                       UFLX[i+1,j-1,k]    +\
                                     - UFLX[i+1,j  ,k]    )
    cuda.syncthreads()

@jit([wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:,:]'], target='gpu')
def calc_fluxes_isjs(CFLX, QFLX, UFLX, VFLX):
    nx = CFLX.shape[0] - 2
    ny = CFLX.shape[1] - 2
    i, j, k = cuda.grid(3)
    if i > 0 and i < nx+1 and j > 0 and j < ny+1:
        CFLX[i  ,j  ,k] = 1./12. * (  VFLX[i-1,j-1,k]   + \
                                      VFLX[i  ,j-1,k]   +\
                                 2.*( VFLX[i-1,j  ,k]   + \
                                      VFLX[i  ,j  ,k] ) +\
                                      VFLX[i-1,j+1,k]   + \
                                      VFLX[i  ,j+1,k]   )

        QFLX[i  ,j  ,k] = 1./12. * (  UFLX[i-1,j-1,k]   + \
                                      UFLX[i-1,j  ,k]   +\
                                 2.*( UFLX[i  ,j-1,k]   + \
                                      UFLX[i  ,j  ,k] ) +\
                                      UFLX[i+1,j-1,k]   + \
                                      UFLX[i+1,j  ,k]    )
    cuda.syncthreads()




@jit([wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:  ], '+wp_old+'[:,:,:], '+wp_old+'[:,:  ], '+ \
      wp_old+'[:    ]'], target='gpu')
def calc_WWIND_UWIND(WWIND_UWIND, UWIND, COLP_NEW, WWIND, A,
                        dsigma):
    nx = WWIND_UWIND.shape[0] - 2
    ny = WWIND_UWIND.shape[1] - 2
    nz = WWIND_UWIND.shape[2]
    i, j, k = cuda.grid(3)
    if i > 0 and i < nx+1 and j > 0 and j < ny+1 and k > 0 and k < nz-1:
        if j == 1:
            # INTERPOLATE DIFFERENTLY AT MERID. BOUNDARIES (JACOBSON)
            COLPAWWIND_is_ks = 1./4.*( \
                COLP_NEW[i-1,j  ] * A[i-1,j  ] * \
                                WWIND[i-1,j  ,k ] + \
                COLP_NEW[i  ,j  ] * A[i  ,j  ] * \
                                WWIND[i  ,j  ,k ] + \
                COLP_NEW[i-1,j+1] * A[i-1,j+1] * \
                                WWIND[i-1,j+1,k ] + \
                COLP_NEW[i ,j+1] * A[i   ,j+1] * \
                                WWIND[i  ,j+1,k ]   )
        elif j == ny:
            # INTERPOLATE DIFFERENTLY AT MERID. BOUNDARIES (JACOBSON)
            COLPAWWIND_is_ks = 1./4.*( \
                COLP_NEW[i-1,j  ] * A[i-1,j  ] * \
                                WWIND[i-1,j  ,k ] + \
                COLP_NEW[i  ,j  ] * A[i  ,j  ] * \
                                WWIND[i  ,j  ,k ] + \
                COLP_NEW[i-1,j-1] * A[i-1,j-1] * \
                                WWIND[i-1,j-1,k ] + \
                COLP_NEW[i  ,j-1] * A[i  ,j-1] * \
                                WWIND[i  ,j-1,k ]  )
        else:
            COLPAWWIND_is_ks = 1./8.*( \
                COLP_NEW[i-1,j+1] * A[-1,j+1] * \
                                WWIND[i-1,j+1,k] + \
                COLP_NEW[i  ,j+1] * A[i  ,j+1] * \
                                WWIND[i  ,j+1,k] + \
           2. * COLP_NEW[i-1,j  ] * A[i-1,j  ] * \
                                WWIND[i-1,j  ,k] + \
           2. * COLP_NEW[i  ,j  ] * A[i  ,j  ] * \
                                WWIND[i  ,j  ,k] + \
                COLP_NEW[i-1,j-1] * A[i-1,j-1] * \
                                WWIND[i-1,j-1,k] + \
                COLP_NEW[i  ,j-1] * A[i  ,j-1] * \
                                WWIND[i  ,j-1,k]   )

        UWIND_ks = ( dsigma[k  ] * UWIND[i  ,j  ,k-1] +   \
                     dsigma[k-1] * UWIND[i  ,j  ,k  ] ) / \
                   ( dsigma[k  ] + dsigma[k-1] )
        WWIND_UWIND[i  ,j  ,k ] = COLPAWWIND_is_ks * UWIND_ks

    if k == 0 or k == nz-1:
        WWIND_UWIND[i  ,j  ,k ] = 0.

    cuda.syncthreads()





@jit([wp_old+'[:,:,:], '+wp_old+'[:,:,:], '+wp_old+'[:,:  ], '+wp_old+'[:,:,:], '+wp_old+'[:,:  ], '+ \
      wp_old+'[:    ]'], target='gpu')
def calc_WWIND_VWIND(WWIND_VWIND, VWIND, COLP_NEW, WWIND, A,
                        dsigma):
    nx = WWIND_VWIND.shape[0] - 2
    ny = WWIND_VWIND.shape[1] - 2
    nz = WWIND_VWIND.shape[2]
    i, j, k = cuda.grid(3)
    if i > 0 and i < nx+1 and j > 0 and j < ny+1 and k > 0 and k < nz-1:
        COLPAWWIND_js_ks = 1./8.*( \
                 COLP_NEW[i+1,j-1] * A[i+1,j-1] * \
                                 WWIND[i+1,j-1,k] + \
                 COLP_NEW[i+1,j  ] * A[i+1,j  ] * \
                                 WWIND[i+1,j  ,k] + \
            2. * COLP_NEW[i  ,j-1] * A[i  ,j-1] * \
                                 WWIND[i  ,j-1,k] + \
            2. * COLP_NEW[i  ,j  ] * A[i  ,j  ] * \
                                 WWIND[i  ,j  ,k] + \
                 COLP_NEW[i-1,j-1] * A[i-1,j-1] * \
                                 WWIND[i-1,j-1,k] + \
                 COLP_NEW[i-1,j  ] * A[i-1,j  ] * \
                                 WWIND[i-1,j  ,k]   )

        VWIND_ks = ( dsigma[k  ] * VWIND[i  ,j  ,k-1] +   \
                     dsigma[k-1] * VWIND[i  ,j  ,k  ] ) / \
                   ( dsigma[k  ] + dsigma[k-1] )
        WWIND_VWIND[i  ,j  ,k ] = COLPAWWIND_js_ks * VWIND_ks

    if k == 0 or k == nz-1:
        WWIND_VWIND[i  ,j  ,k ] = 0.

    cuda.syncthreads()


@jit([wp_old+'[:,:,:], '+wp_old],target='gpu')
def set_to(FIELD, number):
    i, j, k = cuda.grid(3)
    FIELD[i,j,k] = number 
    cuda.syncthreads()



