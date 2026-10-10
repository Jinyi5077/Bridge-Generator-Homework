"""Versioned design-code parameters used by the action and resistance solver.

The numerical solver receives a profile object and contains no design-code
coefficients of its own.  This module remains intentionally small; later
releases can add profiles without changing the finite-element routines.
"""
from copy import deepcopy
import math


DEFAULT_PROFILE = "JTG_D60_2015_JTG_3362_2018"


CODE_PROFILES = {
    DEFAULT_PROFILE: {
        "id": DEFAULT_PROFILE,
        "name": "公路桥涵作用与混凝土材料基础配置",
        "versions": {
            "actions": "JTG D60—2015",
            "concrete": "JTG 3362—2018",
        },
        "traffic": {
            "class": "公路-I级",
            "qk_kn_per_m": 10.5,
            "pk_bending_kn": 360.0,
            "pk_applicable_min_span_m": 50.0,
            "longitudinal_reduction_starts_above_m": 150.0,
            "shear_point_factor": 1.2,
            "lane_factors": {"1": 1.20, "2": 1.0, "3": 0.78},
            "lane_factor_source_url": "https://xxgk.mot.gov.cn/jigou/glj/202006/P020240327350422059754.pdf",
            "impact": {
                "lower_frequency_hz": 1.5,
                "upper_frequency_hz": 14.0,
                "lower_value": 0.05,
                "upper_value": 0.45,
                "log_a": 0.1767,
                "log_b": -0.0157,
            },
            "source": "JTG D60—2015 第4.3.1、4.3.2条及表4.3.1-2、4.3.1-5、4.3.1-6；本程序适用主跨50～150 m",
        },
        "combinations": {
            "uls": {
                "id": "ULS_BASIC",
                "name": "承载能力极限状态基本组合的作用效应",
                "gamma_g_options": [1.0, 1.2],
                "gamma_q": 1.4,
                "vehicle_factor": 1.0,
                "include_impact": True,
                "apply_importance_factor": True,
                "source": "JTG D60—2015 第4.1.6条；恒载系数按效应枚举取包络",
            },
            "standard": {
                "id": "SLS_STANDARD",
                "name": "正常使用极限状态标准组合",
                "gamma_g_options": [1.0],
                "gamma_q": 1.0,
                "vehicle_factor": 1.0,
                "include_impact": True,
                "apply_importance_factor": False,
                "source": "JTG D60—2015 第4.1.7条",
            },
            "frequent": {
                "id": "SLS_FREQUENT",
                "name": "正常使用极限状态频遇组合",
                "gamma_g_options": [1.0],
                "gamma_q": 1.0,
                "vehicle_factor": 0.7,
                "include_impact": False,
                "apply_importance_factor": False,
                "source": "JTG D60—2015 第4.1.7条；汽车荷载频遇值系数0.7",
            },
            "quasi": {
                "id": "SLS_QUASI_PERMANENT",
                "name": "正常使用极限状态准永久组合",
                "gamma_g_options": [1.0],
                "gamma_q": 1.0,
                "vehicle_factor": 0.4,
                "include_impact": False,
                "apply_importance_factor": False,
                "source": "JTG D60—2015 第4.1.7条；汽车荷载准永久值系数0.4",
            },
        },
        "materials": {
            "C40": {"E_mpa": 32500.0, "fck_mpa": 26.8, "ftk_mpa": 2.40,
                    "fcd_mpa": 18.4, "ftd_mpa": 1.65, "fcu_k_mpa": 40.0},
            "C45": {"E_mpa": 33500.0, "fck_mpa": 29.6, "ftk_mpa": 2.51,
                    "fcd_mpa": 20.5, "ftd_mpa": 1.74, "fcu_k_mpa": 45.0},
            "C50": {"E_mpa": 34500.0, "fck_mpa": 32.4, "ftk_mpa": 2.65,
                    "fcd_mpa": 22.4, "ftd_mpa": 1.83, "fcu_k_mpa": 50.0},
            "C55": {"E_mpa": 35500.0, "fck_mpa": 35.5, "ftk_mpa": 2.74,
                    "fcd_mpa": 24.4, "ftd_mpa": 1.89, "fcu_k_mpa": 55.0},
            "C60": {"E_mpa": 36000.0, "fck_mpa": 38.5, "ftk_mpa": 2.85,
                    "fcd_mpa": 26.5, "ftd_mpa": 1.96, "fcu_k_mpa": 60.0},
        },
        "reinforcement": {
            "HRB400": {"fsk_mpa": 400.0, "fsd_mpa": 330.0,
                       "fsd_compression_mpa": 330.0, "E_mpa": 200000.0},
            "strand_1860": {"fpk_mpa": 1860.0, "fpd_mpa": 1260.0,
                            "fpd_compression_mpa": 390.0, "E_mpa": 195000.0},
        },
    }
}


def get_profile(profile_id):
    try:
        return deepcopy(CODE_PROFILES[profile_id])
    except KeyError as exc:
        raise ValueError("未知规范配置: " + str(profile_id)) from exc


def impact_coefficient(frequency_hz, profile):
    cfg = profile["traffic"]["impact"]
    f = float(frequency_hz)
    if not math.isfinite(f) or f <= 0:
        raise ValueError("结构基频必须为正数")
    if f < cfg["lower_frequency_hz"]:
        return cfg["lower_value"]
    if f > cfg["upper_frequency_hz"]:
        return cfg["upper_value"]
    return cfg["log_a"]*math.log(f)+cfg["log_b"]

