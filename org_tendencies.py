#!/usr/bin/env python
#-*- coding: utf-8 -*-
"""
####################################################################
File name:          org_tendencies.py  
Author:             Christoph Heim (CH)
Date created:       20190509
Last modified:      20190523
License:            MIT

Organise the computation of all tendencies in dynamical core:
- potential temperature POTT

Differentiate between computation targets:
- GPU
- CPU
####################################################################
"""
import math
import numpy as np
from numba import cuda

from namelist import (i_UVFLX_hor_adv, i_UVFLX_vert_adv)
from org_namelist import HOST, DEVICE
from tendency_POTT import POTT_tendency_gpu, POTT_tendency_cpu
from tendency_UVFLX_prepare import (UVFLX_prep_adv_gpu,
                                    UVFLX_prep_adv_cpu)
from tendency_UFLX import (UFLX_tendency_gpu, UFLX_tendency_cpu)
from tendency_VFLX import (VFLX_tendency_gpu, VFLX_tendency_cpu)
from grid import tpb, tpb_ks, bpg
####################################################################



class TendencyFactory:
    """
    Depending on computation target, calls the right function
    to calculate the tendencies.
    """
    
    def __init__(self, target):
        """
        INPUT:
        - target: either 'CPU' or 'GPU'
        """
        self.target = target

        self.fields_POTT = ['dPOTTdt', 'POTT', 'UFLX', 'VFLX',
                             'COLP', 'POTTVB', 'WWIND', 'COLP_NEW']
        self.fields_UVFLX= ['dUFLXdt', 'dVFLXdt',
                        'UWIND', 'VWIND', 'WWIND',
                        'UFLX', 'VFLX',
                        'CFLX', 'QFLX', 'DFLX', 'EFLX',
                        'SFLX', 'TFLX', 'BFLX', 'RFLX',
                        'PHI', 'COLP', 'COLP_NEW', 'POTT',
                        'PVTF', 'PVTFVB',
                        'WWIND_UWIND', 'WWIND_VWIND']


    def POTT_tendency(self, target, GR,
                            dPOTTdt, POTT, UFLX, VFLX,
                            COLP, POTTVB, WWIND, COLP_NEW):
        if target == DEVICE:
            POTT_tendency_gpu[bpg, tpb](GR.Ad, GR.dsigmad,
                    dPOTTdt, POTT, UFLX, VFLX, COLP,
                    POTTVB, WWIND, COLP_NEW)
            #cuda.synchronize()
        elif target == HOST:
            POTT_tendency_cpu(GR.A, GR.dsigma,
                    dPOTTdt, POTT, UFLX, VFLX, COLP,
                    POTTVB, WWIND, COLP_NEW)
        return(dPOTTdt)


    def UVFLX_tendency(self, GR, dUFLXdt, dVFLXdt,
                        UWIND, VWIND, WWIND,
                        UFLX, VFLX,
                        CFLX, QFLX, DFLX, EFLX,
                        SFLX, TFLX, BFLX, RFLX,
                        PHI, COLP, COLP_NEW, POTT,
                        PVTF, PVTFVB,
                        WWIND_UWIND, WWIND_VWIND):

        if self.target == 'GPU':
            # PREPARE ADVECTIVE FLUXES
            if i_UVFLX_hor_adv or i_UVFLX_vert_adv:
                UVFLX_prep_adv_gpu[bpg, tpb_ks](
                            WWIND_UWIND, WWIND_VWIND,
                            UWIND, VWIND, WWIND,
                            UFLX, VFLX,
                            CFLX, QFLX, DFLX, EFLX,
                            SFLX, TFLX, BFLX, RFLX,
                            COLP_NEW, GR.Ad, GR.dsigmad)
                #cuda.synchronize()

            # UFLX
            UFLX_tendency_gpu[bpg, tpb](
                        dUFLXdt, UFLX, UWIND, VWIND,
                        BFLX, CFLX, DFLX, EFLX,
                        PHI, COLP, POTT,
                        PVTF, PVTFVB, WWIND_UWIND,
                        GR.corf_isd, GR.lat_is_radd,
                        GR.dlon_radd, GR.dlat_radd,
                        GR.dyisd,
                        GR.dsigmad, GR.sigma_vbd)
            #cuda.synchronize()

            # VFLX
            VFLX_tendency_gpu[bpg, tpb](
                        dVFLXdt, VFLX, UWIND, VWIND,
                        RFLX, SFLX, TFLX, QFLX,
                        PHI, COLP, POTT,
                        PVTF, PVTFVB, WWIND_VWIND,
                        GR.corfd,       GR.lat_radd,
                        GR.dlon_radd,   GR.dlat_radd,
                        GR.dxjsd, 
                        GR.dsigmad,     GR.sigma_vbd)
            #cuda.synchronize()


        elif self.target == 'CPU':
            # PREPARE ADVECTIVE FLUXES
            if i_UVFLX_hor_adv or i_UVFLX_vert_adv:
                UVFLX_prep_adv_cpu(
                            WWIND_UWIND, WWIND_VWIND,
                            UWIND, VWIND, WWIND,
                            UFLX, VFLX,
                            CFLX, QFLX, DFLX, EFLX,
                            SFLX, TFLX, BFLX, RFLX,
                            COLP_NEW, GR.A, GR.dsigma)
            # UFLX
            UFLX_tendency_cpu(
                        dUFLXdt, UFLX, UWIND, VWIND,
                        BFLX, CFLX, DFLX, EFLX,
                        PHI, COLP, POTT,
                        PVTF, PVTFVB, WWIND_UWIND,
                        GR.corf_is,     GR.lat_is_rad,
                        GR.dlon_rad,    GR.dlat_rad,
                        GR.dyis,
                        GR.dsigma,      GR.sigma_vb)

            # VFLX
            VFLX_tendency_cpu(
                        dVFLXdt, VFLX, UWIND, VWIND,
                        RFLX, SFLX, TFLX, QFLX,
                        PHI, COLP, POTT,
                        PVTF, PVTFVB, WWIND_VWIND,
                        GR.corf,        GR.lat_rad,
                        GR.dlon_rad,    GR.dlat_rad,
                        GR.dxjs, 
                        GR.dsigma,      GR.sigma_vb)

        return(dUFLXdt, dVFLXdt)
