import copy
import time
import numpy as np
from namelist import comp_mode
from boundaries import exchange_BC
from jacobson import tendencies_jacobson, proceed_timestep_jacobson, \
                    diagnose_fields_jacobson
from bin.jacobson_cython import proceed_timestep_jacobson_c
#from jacobson import proceed_timestep_jacobson
from diagnostics import interp_COLPA


######################################################################################
######################################################################################
######################################################################################

def RK_time_step(GR, COLP0, UWIND0, VWIND0, POTT0, QV0, QC0, \
                COLP1, UWIND1, VWIND1, POTT1, QV1, QC1, \
                dCOLP, dUFLX, dVFLX, dPOTT, dQV, dQC, factor):

    COLPA_is_0, COLPA_js_0 = interp_COLPA(GR, COLP0)
    COLP1[GR.iijj] = COLP0[GR.iijj] + dCOLP/factor
    COLP1 = exchange_BC(GR, COLP1)
    COLPA_is_1, COLPA_js_1 = interp_COLPA(GR, COLP1)
    for k in range(0,GR.nz):
        UWIND1[:,:,k][GR.iisjj] = UWIND0[:,:,k][GR.iisjj] * \
                    COLPA_is_0/COLPA_is_1 + dUFLX[:,:,k]/factor/COLPA_is_1
        VWIND1[:,:,k][GR.iijjs] = VWIND0[:,:,k][GR.iijjs] * \
                     COLPA_js_0/COLPA_js_1 + dVFLX[:,:,k]/factor/COLPA_js_1
        POTT1[:,:,k][GR.iijj] = POTT0[:,:,k][GR.iijj] * \
                        COLP0[GR.iijj]/COLP1[GR.iijj] + \
                        dPOTT[:,:,k]/factor/COLP1[GR.iijj]
        QV1[:,:,k][GR.iijj] = QV0[:,:,k][GR.iijj] * \
                        COLP0[GR.iijj]/COLP1[GR.iijj] + \
                        dQV[:,:,k]/factor/COLP1[GR.iijj]
        QC1[:,:,k][GR.iijj] = QC0[:,:,k][GR.iijj] * \
                        COLP0[GR.iijj]/COLP1[GR.iijj] + \
                        dQC[:,:,k]/factor/COLP1[GR.iijj]
    QV1[QV1 < 0] = 0
    QC1[QC1 < 0] = 0
    # TODO 4 NECESSARY
    UWIND1 = exchange_BC(GR, UWIND1)
    VWIND1 = exchange_BC(GR, VWIND1)
    POTT1  = exchange_BC(GR, POTT1)
    QV1  = exchange_BC(GR, QV1)
    QC1  = exchange_BC(GR, QC1)

    return(COLP1, UWIND1, VWIND1, POTT1, QV1, QC1)

def step_RK4(GR, subgrids,
        COLP, PHI, PHIVB, POTT, POTTVB,
        UWIND, VWIND, WWIND,
        UFLX, VFLX, 
        HSURF, PVTF, PVTFVB,
        dPOTTdt_RAD, dPOTTdt_MIC,
        QV, QC, dQVdt_MIC, dQCdt_MIC):

    # INITIAL FIELDS
    UWIND_START = copy.deepcopy(UWIND)
    VWIND_START = copy.deepcopy(VWIND)
    COLP_START = copy.deepcopy(COLP)
    POTT_START = copy.deepcopy(POTT)
    POTTVB_START = copy.deepcopy(POTTVB)
    QV_START = copy.deepcopy(QV)
    QC_START = copy.deepcopy(QC)

    # INTERMEDIATE FIELDS
    UWIND_INT = copy.deepcopy(UWIND)
    VWIND_INT = copy.deepcopy(VWIND)
    COLP_INT = copy.deepcopy(COLP)
    POTT_INT = copy.deepcopy(POTT)
    QV_INT = copy.deepcopy(QV)
    QC_INT = copy.deepcopy(QC)

    ########## level 1
    dCOLPdt, dUFLXdt, dVFLXdt, \
    dPOTTdt, WWIND, \
    dQVdt, dQCdt = tendencies_jacobson(GR, subgrids,
                                        COLP, POTT, POTTVB, HSURF,
                                        UWIND, VWIND, WWIND,
                                        UFLX, VFLX, PHI, PVTF, PVTFVB,
                                        dPOTTdt_RAD, dPOTTdt_MIC,
                                        QV, QC, dQVdt_MIC, dQCdt_MIC)

    dUFLX = GR.dt*dUFLXdt
    dVFLX = GR.dt*dVFLXdt
    dCOLP = GR.dt*dCOLPdt
    dPOTT = GR.dt*dPOTTdt
    dQV = GR.dt*dQVdt
    dQC = GR.dt*dQCdt

    # TIME STEPPING
    COLP_INT, UWIND_INT, VWIND_INT, POTT_INT, QV_INT, QC_INT = \
    RK_time_step(GR, COLP_START, UWIND_START, VWIND_START, POTT_START, QV_START, QC_START, \
                COLP_INT, UWIND_INT, VWIND_INT, POTT_INT, QV_INT, QC_INT, \
                dCOLP, dUFLX, dVFLX, dPOTT, dQV, dQC, 2)

    COLP, UWIND, VWIND, POTT, QV, QC = \
    RK_time_step(GR, COLP_START, UWIND_START, VWIND_START, POTT_START, QV_START, QC_START,\
                COLP, UWIND, VWIND, POTT, QV, QC, \
                dCOLP, dUFLX, dVFLX, dPOTT, dQV, dQC, 6)

    PHI, PHIVB, PVTF, PVTFVB, POTTVB = \
            diagnose_fields_jacobson(GR, PHI, PHIVB, COLP_INT, POTT_INT,
                                        HSURF, PVTF, PVTFVB, POTTVB)

    ########## level 2
    dCOLPdt, dUFLXdt, dVFLXdt, \
    dPOTTdt, WWIND, \
    dQVdt, dQCdt = tendencies_jacobson(GR, subgrids,
                                        COLP_INT, POTT_INT, POTTVB, HSURF,
                                        UWIND_INT, VWIND_INT, WWIND,
                                        UFLX, VFLX, PHI, PVTF, PVTFVB,
                                        dPOTTdt_RAD, dPOTTdt_MIC,
                                        QV, QC, dQVdt_MIC, dQCdt_MIC)

    dUFLX = GR.dt*dUFLXdt
    dVFLX = GR.dt*dVFLXdt
    dCOLP = GR.dt*dCOLPdt
    dPOTT = GR.dt*dPOTTdt
    dQV = GR.dt*dQVdt
    dQC = GR.dt*dQCdt

    COLP_INT, UWIND_INT, VWIND_INT, POTT_INT, QV_INT, QC_INT = \
    RK_time_step(GR, COLP_START, UWIND_START, VWIND_START, POTT_START, QV_START, QC_START,\
                COLP_INT, UWIND_INT, VWIND_INT, POTT_INT, QV_INT, QC_INT,\
                dCOLP, dUFLX, dVFLX, dPOTT, dQV, dQC, 2)

    COLP_OLD = copy.deepcopy(COLP)
    COLP, UWIND, VWIND, POTT, QV, QC = \
    RK_time_step(GR, COLP_OLD, UWIND, VWIND, POTT, QV, QC, \
                COLP, UWIND, VWIND, POTT, QV, QC, \
                dCOLP, dUFLX, dVFLX, dPOTT, dQV, dQC, 3)
    
    PHI, PHIVB, PVTF, PVTFVB, POTTVB = \
            diagnose_fields_jacobson(GR, PHI, PHIVB, COLP_INT, POTT_INT,
                                        HSURF, PVTF, PVTFVB, POTTVB)

    ########## level 3
    dCOLPdt, dUFLXdt, dVFLXdt, \
    dPOTTdt, WWIND, \
    dQVdt, dQCdt = tendencies_jacobson(GR, subgrids,
                                        COLP_INT, POTT_INT, POTTVB, HSURF,
                                        UWIND_INT, VWIND_INT, WWIND,
                                        UFLX, VFLX, PHI, PVTF, PVTFVB,
                                        dPOTTdt_RAD, dPOTTdt_MIC,
                                        QV, QC, dQVdt_MIC, dQCdt_MIC)

    dUFLX = GR.dt*dUFLXdt
    dVFLX = GR.dt*dVFLXdt
    dCOLP = GR.dt*dCOLPdt
    dPOTT = GR.dt*dPOTTdt
    dQV = GR.dt*dQVdt
    dQC = GR.dt*dQCdt


    COLP_INT, UWIND_INT, VWIND_INT, POTT_INT, QV_INT, QC_INT = \
    RK_time_step(GR, COLP_START, UWIND_START, VWIND_START, POTT_START, QV_START, QC_START,\
                COLP_INT, UWIND_INT, VWIND_INT, POTT_INT, QV_INT, QC_INT,\
                dCOLP, dUFLX, dVFLX, dPOTT, dQV, dQC, 1)

    COLP_OLD = copy.deepcopy(COLP)
    COLP, UWIND, VWIND, POTT, QV, QC = \
    RK_time_step(GR, COLP_OLD, UWIND, VWIND, POTT, QV, QC,\
                COLP, UWIND, VWIND, POTT, QV, QC,\
                dCOLP, dUFLX, dVFLX, dPOTT, dQV, dQC, 3)
    
    PHI, PHIVB, PVTF, PVTFVB, POTTVB = \
            diagnose_fields_jacobson(GR, PHI, PHIVB, COLP_INT, POTT_INT,
                                        HSURF, PVTF, PVTFVB, POTTVB)

    ########## level 4
    dCOLPdt, dUFLXdt, dVFLXdt, \
    dPOTTdt, WWIND, \
    dQVdt, dQCdt = tendencies_jacobson(GR, subgrids,
                                        COLP_INT, POTT_INT, POTTVB, HSURF,
                                        UWIND_INT, VWIND_INT, WWIND,
                                        UFLX, VFLX, PHI, PVTF, PVTFVB,
                                        dPOTTdt_RAD, dPOTTdt_MIC,
                                        QV, QC, dQVdt_MIC, dQCdt_MIC)

    dUFLX = GR.dt*dUFLXdt
    dVFLX = GR.dt*dVFLXdt
    dCOLP = GR.dt*dCOLPdt
    dPOTT = GR.dt*dPOTTdt
    dQV = GR.dt*dQVdt
    dQC = GR.dt*dQCdt

    COLP_OLD = copy.deepcopy(COLP)
    COLP, UWIND, VWIND, POTT, QV, QC = \
    RK_time_step(GR, COLP_OLD, UWIND, VWIND, POTT, QV, QC,\
                COLP, UWIND, VWIND, POTT, QV, QC,\
                dCOLP, dUFLX, dVFLX, dPOTT, dQV, dQC, 6)

    PHI, PHIVB, PVTF, PVTFVB, POTTVB = \
            diagnose_fields_jacobson(GR, PHI, PHIVB, COLP, POTT, \
                                    HSURF, PVTF, PVTFVB, POTTVB)

    return(COLP, PHI, PHIVB, POTT, POTTVB,
            UWIND, VWIND, WWIND,
            UFLX, VFLX, QV, QC)






#########################################################################################
#########################################################################################
#########################################################################################
#########################################################################################
#########################################################################################





# EULER

#if i_spatial_discretization == 'UPWIND':
#    raise NotImplementedError()
#    #dCOLPdt, dUFLXMPdt, dVFLXMPdt, dPOTTdt = tendencies_upwind(GR, 
#    #                COLP, POTT, HSURF,
#    #                UWIND, VWIND, WIND,
#    #                UFLX, VFLX, UFLXMP, VFLXMP,
#    #                UUFLX, UVFLX, VUFLX, VVFLX)
#
#    #UFLXMP, VFLXMP, COLP, POTT = proceed_timestep_upwind(GR, UFLXMP, VFLXMP, 
#    #                                    COLP, POTT, dCOLPdt, dUFLXMPdt, 
#    #                                    dVFLXMPdt, dPOTTdt)
#
#    #UWIND, VWIND = diagnose_fields_upwind(GR, COLP, POTT,
#    #                UWIND, VWIND, UFLXMP, VFLXMP, HSURF)




# MATSUNO

#    if i_spatial_discretization == 'UPWIND':
#        raise NotImplementedError()
#        ########### ESTIMATE
#        #dCOLPdt, dUFLXMPdt, dVFLXMPdt, dPOTTdt = tendencies_upwind(GR, 
#        #                COLP, POTT, HSURF,
#        #                UWIND, VWIND, WIND,
#        #                UFLX, VFLX, UFLXMP, VFLXMP,
#        #                UUFLX, UVFLX, VUFLX, VVFLX)
#
#        ## has to happen after masspoint_flux_tendency function
#        #UFLXMP_OLD = copy.deepcopy(UFLXMP)
#        #VFLXMP_OLD = copy.deepcopy(VFLXMP)
#        #COLP_OLD = copy.deepcopy(COLP)
#        #POTT_OLD = copy.deepcopy(POTT)
#
#
#        #UFLXMP, VFLXMP, COLP, POTT = proceed_timestep_upwind(GR, UFLXMP, VFLXMP, COLP,
#        #                                    POTT, dCOLPdt, dUFLXMPdt, dVFLXMPdt,
#        #                                    dPOTTdt)
#
#        #UWIND, VWIND = diagnose_fields_upwind(GR, COLP, POTT,
#        #                UWIND, VWIND, UFLXMP, VFLXMP, HSURF)
#
#        ########### FINAL
#        #dCOLPdt, dUFLXMPdt, dVFLXMPdt, dPOTTdt = tendencies_upwind(GR, 
#        #                COLP, POTT, HSURF,
#        #                UWIND, VWIND, WIND,
#        #                UFLX, VFLX, UFLXMP, VFLXMP,
#        #                UUFLX, UVFLX, VUFLX, VVFLX)
#
#        #UFLXMP, VFLXMP, COLP, POTT = proceed_timestep_upwind(GR, UFLXMP_OLD,
#        #                                    VFLXMP_OLD, COLP_OLD, POTT_OLD,
#        #                                    dCOLPdt, dUFLXMPdt, dVFLXMPdt, dPOTTdt)
#
#        #UWIND, VWIND = diagnose_fields_upwind(GR, COLP, POTT,
#        #                UWIND, VWIND, UFLXMP, VFLXMP, HSURF)




# RK4


#    if i_spatial_discretization == 'UPWIND':
#        raise NotImplementedError()
#        ########## level 1
#        dCOLPdt, dUFLXMPdt, dVFLXMPdt, dPOTTdt = tendencies_upwind(GR, 
#                        COLP, POTT, HSURF,
#                        UWIND, VWIND, WIND,
#                        UFLX, VFLX, UFLXMP, VFLXMP,
#                        UUFLX, UVFLX, VUFLX, VVFLX)
#
#        # has to happen after masspoint_flux_tendency function
#        UFLXMP_OLD = copy.deepcopy(UFLXMP)
#        VFLXMP_OLD = copy.deepcopy(VFLXMP)
#        COLP_OLD = copy.deepcopy(COLP)
#        POTT_OLD = copy.deepcopy(POTT)
#
#        UFLXMP_INT = copy.deepcopy(UFLXMP)
#        VFLXMP_INT = copy.deepcopy(VFLXMP)
#        COLP_INT = copy.deepcopy(COLP)
#        POTT_INT = copy.deepcopy(POTT)
#
#        dUFLXMP = GR.dt*dUFLXMPdt
#        dVFLXMP = GR.dt*dVFLXMPdt
#        dCOLP = GR.dt*dCOLPdt
#        dPOTT = GR.dt*dPOTTdt
#
#        UFLXMP_INT[GR.iijj] = UFLXMP_OLD[GR.iijj] + dUFLXMP/2
#        VFLXMP_INT[GR.iijj] = VFLXMP_OLD[GR.iijj] + dVFLXMP/2
#        COLP_INT[GR.iijj] = COLP_OLD[GR.iijj] + dCOLP/2
#        POTT_INT[GR.iijj] = POTT_OLD[GR.iijj] + dPOTT/2
#        UFLXMP_INT = exchange_BC(GR, UFLXMP_INT)
#        VFLXMP_INT = exchange_BC(GR, VFLXMP_INT)
#        COLP_INT = exchange_BC(GR, COLP_INT)
#        POTT_INT = exchange_BC(GR, POTT_INT)
#
#        UFLXMP[GR.iijj] = UFLXMP_OLD[GR.iijj] + dUFLXMP/6
#        VFLXMP[GR.iijj] = VFLXMP_OLD[GR.iijj] + dVFLXMP/6
#        COLP[GR.iijj] = COLP_OLD[GR.iijj] + dCOLP/6
#        POTT[GR.iijj] = POTT_OLD[GR.iijj] + dPOTT/6
#        
#        UWIND, VWIND = diagnose_fields_upwind(GR, COLP_INT, POTT_INT,
#                        UWIND, VWIND, UFLXMP_INT, VFLXMP_INT, HSURF)
#
#        ########## level 2
#        dCOLPdt, dUFLXMPdt, dVFLXMPdt, dPOTTdt = tendencies_upwind(GR, 
#                        COLP_INT, POTT_INT, HSURF,
#                        UWIND, VWIND, WIND,
#                        UFLX, VFLX, UFLXMP_INT, VFLXMP_INT,
#                        UUFLX, UVFLX, VUFLX, VVFLX)
#
#        dUFLXMP = GR.dt*dUFLXMPdt
#        dVFLXMP = GR.dt*dVFLXMPdt
#        dCOLP = GR.dt*dCOLPdt
#        dPOTT = GR.dt*dPOTTdt
#
#        UFLXMP_INT[GR.iijj] = UFLXMP_OLD[GR.iijj] + dUFLXMP/2
#        VFLXMP_INT[GR.iijj] = VFLXMP_OLD[GR.iijj] + dVFLXMP/2
#        COLP_INT[GR.iijj] = COLP_OLD[GR.iijj] + dCOLP/2
#        POTT_INT[GR.iijj] = POTT_OLD[GR.iijj] + dPOTT/2
#        UFLXMP_INT = exchange_BC(GR, UFLXMP_INT)
#        VFLXMP_INT = exchange_BC(GR, VFLXMP_INT)
#        COLP_INT = exchange_BC(GR, COLP_INT)
#        POTT_INT = exchange_BC(GR, POTT_INT)
#
#        UFLXMP[GR.iijj] = UFLXMP[GR.iijj] + dUFLXMP/3
#        VFLXMP[GR.iijj] = VFLXMP[GR.iijj] + dVFLXMP/3
#        COLP[GR.iijj] = COLP[GR.iijj] + dCOLP/3
#        POTT[GR.iijj] = POTT[GR.iijj] + dPOTT/3
#        
#        UWIND, VWIND = diagnose_fields_upwind(GR, COLP_INT, POTT_INT,
#                        UWIND, VWIND, UFLXMP_INT, VFLXMP_INT, HSURF)
#
#        ########## level 3
#        dCOLPdt, dUFLXMPdt, dVFLXMPdt, dPOTTdt = tendencies_upwind(GR, 
#                        COLP_INT, POTT_INT, HSURF,
#                        UWIND, VWIND, WIND,
#                        UFLX, VFLX, UFLXMP_INT, VFLXMP_INT,
#                        UUFLX, UVFLX, VUFLX, VVFLX)
#
#        dUFLXMP = GR.dt*dUFLXMPdt
#        dVFLXMP = GR.dt*dVFLXMPdt
#        dCOLP = GR.dt*dCOLPdt
#        dPOTT = GR.dt*dPOTTdt
#
#        UFLXMP_INT[GR.iijj] = UFLXMP_OLD[GR.iijj] + dUFLXMP
#        VFLXMP_INT[GR.iijj] = VFLXMP_OLD[GR.iijj] + dVFLXMP
#        COLP_INT[GR.iijj] = COLP_OLD[GR.iijj] + dCOLP
#        POTT_INT[GR.iijj] = POTT_OLD[GR.iijj] + dPOTT
#        UFLXMP_INT = exchange_BC(GR, UFLXMP_INT)
#        VFLXMP_INT = exchange_BC(GR, VFLXMP_INT)
#        COLP_INT = exchange_BC(GR, COLP_INT)
#        POTT_INT = exchange_BC(GR, POTT_INT)
#
#        UFLXMP[GR.iijj] = UFLXMP[GR.iijj] + dUFLXMP/3
#        VFLXMP[GR.iijj] = VFLXMP[GR.iijj] + dVFLXMP/3
#        COLP[GR.iijj] = COLP[GR.iijj] + dCOLP/3
#        POTT[GR.iijj] = POTT[GR.iijj] + dPOTT/3
#        
#        UWIND, VWIND = diagnose_fields_upwind(GR, COLP_INT, POTT_INT,
#                        UWIND, VWIND, UFLXMP_INT, VFLXMP_INT, HSURF)
#
#        ########## level 4
#        dCOLPdt, dUFLXMPdt, dVFLXMPdt, dPOTTdt = tendencies_upwind(GR, 
#                        COLP_INT, POTT_INT, HSURF,
#                        UWIND, VWIND, WIND,
#                        UFLX, VFLX, UFLXMP_INT, VFLXMP_INT,
#                        UUFLX, UVFLX, VUFLX, VVFLX)
#
#        dUFLXMP = GR.dt*dUFLXMPdt
#        dVFLXMP = GR.dt*dVFLXMPdt
#        dCOLP = GR.dt*dCOLPdt
#        dPOTT = GR.dt*dPOTTdt
#
#        UFLXMP[GR.iijj] = UFLXMP[GR.iijj] + dUFLXMP/6
#        VFLXMP[GR.iijj] = VFLXMP[GR.iijj] + dVFLXMP/6
#        COLP[GR.iijj] = COLP[GR.iijj] + dCOLP/6
#        POTT[GR.iijj] = POTT[GR.iijj] + dPOTT/6
#        UFLXMP = exchange_BC(GR, UFLXMP)
#        VFLXMP = exchange_BC(GR, VFLXMP)
#        COLP = exchange_BC(GR, COLP)
#        POTT = exchange_BC(GR, POTT)
#        
#        UWIND, VWIND = diagnose_fields_upwind(GR, COLP, POTT,
#                        UWIND, VWIND, UFLXMP, VFLXMP, HSURF)
