import numpy as np
import time
from namelist import QV_hor_dif_tau


i_vert_adv     = 1
i_hor_adv      = 1
i_num_dif      = 1
i_microphysics = 1


def water_vapor_tendency(GR, QV, COLP, COLP_NEW, UFLX, VFLX, WWIND, MIC):

    t_start = time.time()


    dQVdt = np.zeros( (GR.nx ,GR.ny ,GR.nz) )

    QVVB = np.zeros( (GR.nx ,GR.ny ,GR.nzs) )
    QVVB[:,:,1:(GR.nzs-1)] = (QV[:,:,:-1][GR.iijj] + QV[:,:,1:][GR.iijj])/2


    for k in range(0,GR.nz):

        # HORIZONTAL ADVECTION
        if i_hor_adv:
            dQVdt[:,:,k] = (+ UFLX[:,:,k][GR.iijj    ] *\
                                 (QV[:,:,k][GR.iijj_im1] + QV[:,:,k][GR.iijj    ])/2 \
                              - UFLX[:,:,k][GR.iijj_ip1] *\
                                 (QV[:,:,k][GR.iijj    ] + QV[:,:,k][GR.iijj_ip1])/2 \
                              + VFLX[:,:,k][GR.iijj    ] *\
                                 (QV[:,:,k][GR.iijj_jm1] + QV[:,:,k][GR.iijj    ])/2 \
                              - VFLX[:,:,k][GR.iijj_jp1] *\
                                 (QV[:,:,k][GR.iijj    ] + QV[:,:,k][GR.iijj_jp1])/2 \
                             ) / GR.A[GR.iijj]

        # VERTICAL ADVECTION
        if i_vert_adv:
            if k == 0:
                vertAdv_QV = COLP_NEW[GR.iijj] * (\
                        - WWIND[:,:,k+1][GR.iijj] * QVVB[:,:,k+1] \
                                               ) / GR.dsigma[k]
            elif k == GR.nz:
                vertAdv_QV = COLP_NEW[GR.iijj] * (\
                        + WWIND[:,:,k  ][GR.iijj] * QVVB[:,:,k  ] \
                                               ) / GR.dsigma[k]
            else:
                vertAdv_QV = COLP_NEW[GR.iijj] * (\
                        + WWIND[:,:,k  ][GR.iijj] * QVVB[:,:,k  ] \
                        - WWIND[:,:,k+1][GR.iijj] * QVVB[:,:,k+1] \
                                               ) / GR.dsigma[k]

            dQVdt[:,:,k] = dQVdt[:,:,k] + vertAdv_QV


        # NUMERICAL DIFUSION 
        if i_num_dif and (QV_hor_dif_tau > 0):
            num_diff = QV_hor_dif_tau * \
                         (+ COLP[GR.iijj_im1] * QV[:,:,k][GR.iijj_im1] \
                          + COLP[GR.iijj_ip1] * QV[:,:,k][GR.iijj_ip1] \
                          + COLP[GR.iijj_jm1] * QV[:,:,k][GR.iijj_jm1] \
                          + COLP[GR.iijj_jp1] * QV[:,:,k][GR.iijj_jp1] \
                          - 4*COLP[GR.iijj] * QV[:,:,k][GR.iijj] ) 
            dQVdt[:,:,k] = dQVdt[:,:,k] + num_diff

        # MICROPHYSICS
        if i_microphysics:
            dQVdt[:,:,k] = dQVdt[:,:,k] + MIC.dQVdt_MIC[:,:,k] * COLP[GR.iijj]

    #print(np.max(MIC.dQVdt_MIC[:,:,GR.nz-1]))

    t_end = time.time()
    GR.mic_comp_time += t_end - t_start


    return(dQVdt)



