"""Inputs, span matching and section suggestions for BridgeGenerator V0.13."""
from copy import deepcopy
import math
from .code_profiles import DEFAULT_PROFILE, get_profile


DEFAULT = {
    "project_name": "混凝土连续箱梁课程设计方案",
    "designer_name": "", "student_id": "", "institution": "",
    "class_name": "", "supervisor": "", "drawing_date": "",
    "elevation_mode": "relative", "deck_elevation": 0.0,
    "longitudinal_slope": 0.0,
    "code_profile": DEFAULT_PROFILE,
    "transverse_method": "single_box_resultant",
    "lanes": 4, "layout": "auto",
    "main_span_min": 50.0, "main_span_max": 220.0,
    "main_span": 100.0, "side_span_mode": "auto_ratio",
    "side_span_ratio": 0.6, "left_side_span": 60.0,
    "right_side_span": 60.0, "candidate_step": 10.0,
    "lane_width": 3.5, "barrier_width": 0.5, "deck_gap": 1.0,
    "inner_margin": 0.5, "outer_margin": 0.5,
    "cantilever_width": 2.0, "cells": 1,
    "height_reference_span": 100.0, "height_mid": 2.8,
    "height_pier": 5.8, "height_curve_exponent": 1.8,
    "cross_slope": 0.02, "top_thickness": 0.30, "tip_thickness": 0.20,
    "top_haunch_horizontal": 0.70, "top_haunch_vertical": 0.25,
    "bottom_mid": 0.28, "bottom_pier": 0.70,
    "bottom_chamfer_horizontal": 0.60, "bottom_chamfer_vertical": 0.30,
    "web_mid": 0.55, "web_pier": 0.80,
    "concrete": "C50", "concrete_weight": 26.0,
    "pavement_thickness": 0.10, "pavement_weight": 24.0,
    "barrier_line_load": 24.0, "other_dead_load": 5.0,
    "mesh_length": 0.5, "importance_factor": 1.1,
    "construction_method": "balanced_cantilever",
    "segment_length": 5.0, "form_traveler_load": 800.0,
    "closure_age_days": 90.0,
    "strand_diameter": 15.2, "strand_area_mm2": 140.0,
    "strand_fpk_mpa": 1860.0, "strand_E_mpa": 195000.0,
    "jacking_stress_ratio": 0.75, "strands_per_tendon": 19,
    "prestress_cover": 0.18, "friction_mu": 0.20,
    "prestress_end_eccentricity_m": None,
    "wobble_k_per_m": 0.0015, "anchorage_slip_mm": 6.0,
    "elastic_shortening_ratio": 0.04, "shrinkage_strain": 0.0002,
    "creep_loss_ratio": 0.06, "relaxation_loss_ratio": 0.025,
    "prestress_class": "A", "environment_class": "II",
    "rebar_grade": "HRB400", "longitudinal_bar_diameter_mm": 28.0,
    "longitudinal_rebar_ratio_per_face": 0.0015,
    "stirrup_diameter_mm": 16.0, "stirrup_spacing_mm": 150.0,
    "stirrup_legs_per_web": 2,
    "pier_height": 15.0, "pile_length": 25.0, "oda_path": "",
}

MATERIALS = {name: {"E": values["E_mpa"]}
             for name, values in get_profile(DEFAULT_PROFILE)["materials"].items()}

LIMITS = {
    "main_span_min": (50, 220), "main_span_max": (50, 220),
    "main_span": (50, 220), "side_span_ratio": (0.5, 0.8),
    "left_side_span": (25, 176), "right_side_span": (25, 176),
    "deck_elevation": (-1000, 10000), "longitudinal_slope": (-0.06, 0.06),
    "candidate_step": (1, 30), "lane_width": (3.0, 4.0),
    "barrier_width": (0.3, 1.0), "deck_gap": (0.2, 5.0),
    "inner_margin": (0, 4), "outer_margin": (0, 4),
    "cantilever_width": (0.8, 3.0),
    "height_reference_span": (40, 220), "height_mid": (1.8, 7.0),
    "height_pier": (2.0, 18.0), "height_curve_exponent": (1.2, 2.5),
    "cross_slope": (0.0, 0.06), "top_thickness": (0.22, 0.7),
    "tip_thickness": (0.15, 0.5), "top_haunch_horizontal": (0.1, 2.0),
    "top_haunch_vertical": (0.05, 0.7), "bottom_mid": (0.2, 0.8),
    "bottom_pier": (0.25, 1.5), "bottom_chamfer_horizontal": (0.1, 1.5),
    "bottom_chamfer_vertical": (0.05, 0.8), "web_mid": (0.3, 1.2),
    "web_pier": (0.35, 1.5), "concrete_weight": (23, 27),
    "pavement_thickness": (0, 0.3), "pavement_weight": (20, 27),
    "barrier_line_load": (0, 100), "other_dead_load": (0, 100),
    "mesh_length": (0.5, 5), "importance_factor": (1.0, 1.1),
    "segment_length": (2.0, 8.0), "form_traveler_load": (100, 2000),
    "closure_age_days": (28, 365), "strand_diameter": (12, 18),
    "strand_area_mm2": (90, 200), "strand_fpk_mpa": (1500, 2100),
    "strand_E_mpa": (180000, 210000), "jacking_stress_ratio": (0.55, 0.80),
    "strands_per_tendon": (7, 37), "prestress_cover": (0.12, 0.50),
    "friction_mu": (0.10, 0.35), "wobble_k_per_m": (0.0005, 0.004),
    "anchorage_slip_mm": (2, 12), "elastic_shortening_ratio": (0.0, 0.12),
    "shrinkage_strain": (0.00005, 0.0006), "creep_loss_ratio": (0.0, 0.15),
    "relaxation_loss_ratio": (0.0, 0.10),
    "longitudinal_bar_diameter_mm": (16, 40),
    "longitudinal_rebar_ratio_per_face": (0.0005, 0.01),
    "stirrup_diameter_mm": (10, 25), "stirrup_spacing_mm": (80, 300),
    "stirrup_legs_per_web": (2, 6),
    "pier_height": (4, 40), "pile_length": (5, 60),
}


def section_suggestions(main_span, lanes=4):
    """Return editable course-design starting dimensions for a 50--220 m span.

    These values are deterministic starting points, not an optimization or a
    substitute for the checks performed by the calculation pipeline.  The UI
    copies them into ordinary inputs so every value remains visible and can be
    overridden before calculation.
    """
    try:
        span = float(main_span)
    except (TypeError, ValueError):
        raise ValueError("主跨必须为数字")
    if not math.isfinite(span) or not 50.0 <= span <= 220.0:
        raise ValueError("主跨必须在50—220 m范围内")
    if isinstance(lanes, bool):
        raise ValueError("总车道数仅支持2、3、4、6")
    try:
        lane_count = float(lanes)
    except (TypeError, ValueError):
        raise ValueError("总车道数仅支持2、3、4、6")
    if lane_count not in {2.0, 3.0, 4.0, 6.0}:
        raise ValueError("总车道数仅支持2、3、4、6")
    # A wider three-lane independent box starts with thicker webs and larger
    # stirrups.  These are visible/editable course-design starting values,
    # not a code coefficient or a substitute for the actual section checks.
    web_factor = 1.25 if lane_count in {3, 6} else 1.0
    starter_stirrup = (20.0 if lane_count in {3, 6} else 18.0) if span > 120 else (18.0 if lane_count in {3, 6} else 16.0)
    return {
        "height_reference_span": round(span, 3),
        "height_mid": round(max(1.8, span / 35.7142857143), 2),
        "height_pier": round(span / 17.2413793103, 2),
        "top_thickness": round(0.26 + 0.0004 * span, 2),
        "tip_thickness": 0.20,
        "bottom_mid": round(0.24 + 0.0004 * span, 2),
        "bottom_pier": round(0.50 + 0.0020 * span, 2),
        "web_mid": round((0.45 + 0.0010 * span)*web_factor, 2),
        "web_pier": round((0.60 + 0.0020 * span)*web_factor, 2),
        "stirrup_diameter_mm": starter_stirrup,
        "top_haunch_horizontal": round(0.60 + 0.0010 * span, 2),
        "top_haunch_vertical": round(0.20 + 0.0005 * span, 2),
        "bottom_chamfer_horizontal": round(0.50 + 0.0010 * span, 2),
        "bottom_chamfer_vertical": round(0.25 + 0.0005 * span, 2),
        "suggestion_basis": (
            "50—220 m、2/3/4/6车道单箱单室连续梁课程设计初始值；"
            "跨中梁高设1.8 m构造初选下限；"
            + ("每幅3车道腹板厚度初选增加25%；" if lane_count in {3, 6} else "")
            + f"箍筋直径初选{starter_stirrup:g} mm，均为可编辑课程设计起始值，非规范系数；"
            + "计算前可逐项修改，最终以程序验算结果为准"
        ),
    }


def span_suggestions(main_span, ratio=0.60):
    """Return a transparent three-span arrangement derived from the main span."""
    try:
        span = float(main_span)
        ratio = float(ratio)
    except (TypeError, ValueError):
        raise ValueError("主跨和边主跨比必须为数字")
    if not math.isfinite(span) or not 50.0 <= span <= 220.0:
        raise ValueError("主跨必须在50—220 m范围内")
    if not math.isfinite(ratio) or not 0.50 <= ratio <= 0.80:
        raise ValueError("边跨与主跨之比必须在0.50—0.80范围内")
    side = round(span*ratio, 3)
    return {
        "side_span_mode": "auto_ratio",
        "side_span_ratio": ratio,
        "left_side_span": side,
        "right_side_span": side,
        "arrangement": [side, span, side],
        "suggestion_basis": "边跨按主跨乘边主跨比自动匹配；左右边跨仍可切换为手动输入",
    }


def validate(raw):
    c = deepcopy(DEFAULT)
    unknown = set(raw) - set(c)
    if unknown:
        raise ValueError("未知参数: " + ", ".join(sorted(unknown)))
    c.update(raw)
    if not isinstance(c["elevation_mode"], str) or c["elevation_mode"] not in {"relative", "absolute"}:
        raise ValueError("高程模式仅支持relative相对高程或absolute绝对高程")
    if c["elevation_mode"] == "absolute" and "deck_elevation" not in raw:
        raise ValueError("绝对高程必须由用户明确填写deck_elevation，不得由程序假定")
    metadata_lengths = {"designer_name": 16, "student_id": 32, "institution": 44,
                        "class_name": 24, "supervisor": 28, "drawing_date": 10}
    for name, maximum in metadata_lengths.items():
        if not isinstance(c[name], str):
            raise ValueError(name+"必须为文字")
        c[name] = c[name].strip()
        if len(c[name]) > maximum or any(char in c[name] for char in ("\n", "\r", "\t")):
            raise ValueError(f"{name}须为不超过{maximum}字的单行文字")
    if isinstance(c["lanes"], bool):
        raise ValueError("总车道数仅支持2、3、4、6")
    try:
        lanes = float(c["lanes"])
    except (TypeError, ValueError):
        raise ValueError("总车道数仅支持2、3、4、6")
    if lanes not in {2.0, 3.0, 4.0, 6.0}:
        raise ValueError("总车道数仅支持2、3、4、6")
    c["lanes"] = int(lanes)
    try:
        span_for_starters = float(c["main_span"])
    except (TypeError, ValueError):
        raise ValueError("main_span 必须为数字")
    if c["lanes"] in {3, 6} or span_for_starters > 120:
        suggestions = section_suggestions(c["main_span"], c["lanes"])
        names = ("web_mid", "web_pier", "stirrup_diameter_mm")
        if span_for_starters > 120:
            # Existing <=120 m defaults remain compatible.  In the added
            # span range, use visible/editable span-dependent construction
            # starters only where the caller has not supplied a value.
            names += ("top_thickness", "tip_thickness", "bottom_mid", "bottom_pier",
                      "top_haunch_horizontal", "top_haunch_vertical",
                      "bottom_chamfer_horizontal", "bottom_chamfer_vertical")
        for name in names:
            if name not in raw:
                c[name] = suggestions[name]
    expected_layout = "single" if c["lanes"] in {2, 3} else "separated"
    if c["layout"] == "auto":
        c["layout"] = expected_layout
    elif c["layout"] != expected_layout:
        raise ValueError("2、3车道采用单幅；4、6车道采用分离两幅，布局与车道数不一致")
    if c["cells"] != 1 or isinstance(c["cells"], bool):
        raise ValueError("本版每幅采用单箱单室，cells须为1")
    profile = get_profile(c["code_profile"])
    if c["transverse_method"] != "single_box_resultant":
        raise ValueError("本版横向方法须为 single_box_resultant")
    if c["side_span_mode"] not in {"auto_ratio", "manual"}:
        raise ValueError("边跨模式仅支持自动比例或手动输入")
    if c["side_span_mode"] == "auto_ratio":
        try:
            side = float(c["main_span"])*float(c["side_span_ratio"])
        except (TypeError, ValueError):
            raise ValueError("主跨和边主跨比必须为数字")
        # Derived automatic side spans replace cached/manual values before validation.
        c["left_side_span"] = side
        c["right_side_span"] = side
    for name, (lo, hi) in LIMITS.items():
        try:
            val = float(c[name])
        except (TypeError, ValueError):
            raise ValueError(name + " 必须为数字")
        if not math.isfinite(val) or not lo <= val <= hi:
            raise ValueError(f"{name} 取值范围为 {lo}–{hi}")
        c[name] = val
    if not c["main_span_min"] <= c["main_span"] <= c["main_span_max"]:
        raise ValueError("实际主跨必须位于主跨范围内")
    for name in ["left_side_span", "right_side_span"]:
        ratio = c[name]/c["main_span"]
        if not 0.50 <= ratio <= 0.80:
            label = "左边跨" if name == "left_side_span" else "右边跨"
            raise ValueError(f"{label}与主跨之比必须在0.50—0.80范围内")
    if c["height_pier"] <= c["height_mid"]:
        raise ValueError("墩顶参考梁高应大于跨中参考梁高")
    if c["bottom_pier"] < c["bottom_mid"] or c["web_pier"] < c["web_mid"]:
        raise ValueError("墩顶底板和腹板不得薄于跨中")
    if c["tip_thickness"] > c["top_thickness"]:
        raise ValueError("悬臂端厚度不得大于箱室中部顶板厚度")
    if c["construction_method"] != "balanced_cantilever":
        raise ValueError("本版施工方法须为 balanced_cantilever")
    if int(round(c["strands_per_tendon"])) != c["strands_per_tendon"]:
        raise ValueError("每束钢绞线根数必须为整数")
    c["strands_per_tendon"] = int(c["strands_per_tendon"])
    if int(round(c["stirrup_legs_per_web"])) != c["stirrup_legs_per_web"]:
        raise ValueError("每片腹板箍筋肢数必须为整数")
    c["stirrup_legs_per_web"] = int(c["stirrup_legs_per_web"])
    if c["prestress_class"] not in {"full", "A"}:
        raise ValueError("预应力度类别仅支持 full 或 A")
    if c["environment_class"] not in {"I", "II", "III", "IV", "V", "VI", "VII"}:
        raise ValueError("环境类别须为 I 至 VII")
    if c["rebar_grade"] != "HRB400":
        raise ValueError("V0.13 普通钢筋等级采用 HRB400")
    lanes_per_deck = c["lanes"] if c["layout"] == "single" else c["lanes"]//2
    deck_width = lanes_per_deck*c["lane_width"] + 2*c["barrier_width"] + c["inner_margin"] + c["outer_margin"]
    box_width = deck_width - 2*c["cantilever_width"]
    clear = box_width - 2*c["web_pier"]
    if clear <= 1.5:
        raise ValueError("箱室净宽不足，请调整悬臂或腹板")
    if 2*c["top_haunch_horizontal"] >= clear or 2*c["bottom_chamfer_horizontal"] >= clear:
        raise ValueError("上下倒角宽度与箱室净宽冲突")
    # Use the same sloping/chamfered polygons as the solver and drawings.  The
    # short-span starting-height floor belongs to Geometry, so input reference
    # heights remain visible and the output publishes actual resulting heights.
    from .geometry import Geometry
    geometry = Geometry(c)
    actual_mid_height = geometry.section(geometry.left_side+geometry.main/2)["h"]
    actual_pier_height = geometry.section(geometry.left_side)["h"]
    if actual_pier_height <= actual_mid_height:
        raise ValueError("实际墩顶梁高必须大于实际跨中梁高；短跨跨中初选下限为1.8 m")
    if c["prestress_end_eccentricity_m"] is not None:
        value = c["prestress_end_eccentricity_m"]
        if isinstance(value, bool):
            raise ValueError("桥台端预应力偏心须为数值或null自动初选")
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValueError("桥台端预应力偏心须为数值或null自动初选")
        if not math.isfinite(value):
            raise ValueError("桥台端预应力偏心必须为有限数值")
        for position in (0., geometry.length):
            sec = geometry.section(position)
            upper = sec["y"]-c["prestress_cover"]
            lower = sec["h"]-sec["y"]-c["prestress_cover"]
            if not -upper <= value <= lower:
                raise ValueError("桥台端预应力偏心超出该截面的保护层允许范围")
        c["prestress_end_eccentricity_m"] = value
    for index in range(101):
        geometry.section(geometry.length*index/100)
    if c["concrete"] not in profile["materials"]:
        raise ValueError("混凝土等级须为 C40 至 C60")
    if not all(isinstance(c[name], str) for name in
               ["oda_path", "project_name", "code_profile", "transverse_method", "side_span_mode",
                "construction_method", "prestress_class", "environment_class",
                "rebar_grade"]):
        raise ValueError("名称和转换器路径必须为文字")
    if not c["project_name"].strip() or len(c["project_name"]) > 60:
        raise ValueError("项目名称须为 1–60 字")
    return c


def span_candidates(c):
    values = []
    x = c["main_span_min"]
    while x <= c["main_span_max"] + 1e-8:
        values.append(round(x, 4))
        x += c["candidate_step"]
    values.extend([c["main_span_max"], c["main_span"]])
    return [dict(main=v, left=round(v*c["side_span_ratio"], 3),
                 right=round(v*c["side_span_ratio"], 3),
                 total=round(v*(1+2*c["side_span_ratio"]), 3), selected=v==c["main_span"])
            for v in sorted(set(values))]
