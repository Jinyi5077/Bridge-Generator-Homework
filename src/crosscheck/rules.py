"""Separately maintained course rules, in N/mm/MPa; no main-profile imports.

Sources: JTG D60-2015 4.1/4.3; JTG 3362-2018 3.1/5.2/6.3/6.5/7.1.
These constants describe the supported course model, not all bridge actions.
"""
SOURCES = {
    'traffic': 'https://xxgk.mot.gov.cn/jigou/glj/202006/P020240327350422059754.pdf',
    'concrete': 'https://xxgk.mot.gov.cn/2020/jigou/glj/202006/t20200623_3312720.html',
}
CONCRETE = {
    'C40': (32500., 26.8, 2.40, 18.4, 1.65, 40.),
    'C45': (33500., 29.6, 2.51, 20.5, 1.74, 45.),
    'C50': (34500., 32.4, 2.65, 22.4, 1.83, 50.),
    'C55': (35500., 35.5, 2.74, 24.4, 1.89, 55.),
    'C60': (36000., 38.5, 2.85, 26.5, 1.96, 60.),
}
LANE_REDUCTION = {1: 1.2, 2: 1.0, 3: .78}
QK, PK, SHEAR_POINT_FACTOR = 10.5, 360000., 1.2
FSD, FPD = 330., 1260.
COMBINATIONS = {
    'uls': ((1., 1.2), 1.4, True, True),
    'standard': ((1.,), 1., True, False),
    'frequent': ((1.,), .7, False, False),
    'quasi': ((1.,), .4, False, False),
}

def impact(frequency):
    import math
    return .05 if frequency < 1.5 else (.45 if frequency > 14 else .1767*math.log(frequency)-.0157)
