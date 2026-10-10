"""Traceable course-design effects and named checks for V0.12."""
from dataclasses import asdict
from datetime import datetime
import itertools
import numpy as np

from .code_profiles import get_profile, impact_coefficient
from .config import validate, span_candidates, section_suggestions
from .geometry import Geometry
from .fem import Beam
from .state import (CalculationRecord, CombinationDefinition, DesignState,
                    LoadCase, records_to_dict)
from .units import UNIT_SYSTEM, field_unit
from .prestress import design_prestress
from .construction import analyse_construction
from .verification import verify_structure


VERSION = "0.12.0"

REFERENCES = [
    dict(code="JTG D60—2015", clause="4.1.5～4.1.7", topic="作用组合",
         implementation="组合由规范配置读取；一期、二期恒载分别枚举系数并保存控制组合"),
    dict(code="JTG D60—2015", clause="4.3.1、4.3.2", topic="汽车作用",
         implementation="公路I级车道荷载；按每幅实际2或3条车道枚举布载并保存纵横向控制位置"),
    dict(code="JTG 3362—2018", clause="3.1.5", topic="弹性模量",
         implementation="未开裂混凝土毛截面弹性刚度EcIg；输出弯矩、剪力、反力和竖向位移"),
    dict(code="JTG 3362—2018", clause="5.2、6.3、6.5、7.1", topic="纵向整体验算",
         implementation="正截面抗弯、斜截面抗剪、抗裂、使用阶段压应力、活载挠度和施工阶段压应力"),
    dict(code="高邮湖特大桥87.5+145+87.5m箱梁一般构造图", clause="第3至18张", topic="构造参考",
         implementation="借鉴单箱单室、上下加腋倒角和1.8次变高形式；项目尺寸仍需后续验算确定"),
]

OUT_OF_COURSE_SCOPE = [
    "横向桥面板、横隔板、齿块和锚下局部承载力属于本次课程设计范围外。",
    "空间扭转、剪力滞、畸变、温度、支座沉降、风、地震及偶然作用属于本次课程设计范围外。",
    "下部结构仅按任务书绘制合理示意，不进行桥墩、承台和桩基承载力验算。",
    "普通钢筋和预应力采用课程设计级初配，不作为施工图级分区截断、锚固、接头和齿块详图。",
]


def serial(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    return value


def _station_displacements(displacements):
    """Convert nodal vertical DOFs to the duplicated section-station layout."""
    values = np.asarray(displacements)
    nodes = values[0::2]
    if values.ndim == 1:
        return np.column_stack((nodes[:-1], nodes[1:])).ravel()
    return np.stack((nodes[:-1], nodes[1:]), axis=1).reshape(-1, values.shape[1])


def _single_lane_envelope(influence, weights, load_x, qk, pk):
    pos = np.maximum(influence, 0.0)
    neg = np.minimum(influence, 0.0)
    pos_index = np.argmax(influence, axis=1)
    neg_index = np.argmin(influence, axis=1)
    rows = np.arange(influence.shape[0])
    positive_area = pos @ weights
    negative_area = neg @ weights
    eta_max = influence[rows, pos_index]
    eta_min = influence[rows, neg_index]
    low = qk*negative_area + pk*eta_min
    high = qk*positive_area + pk*eta_max
    trace = dict(
        positive_area=positive_area, negative_area=negative_area,
        eta_max=eta_max, eta_min=eta_min,
        load_x_max=load_x[pos_index], load_x_min=load_x[neg_index],
    )
    return low, high, trace


def _transverse_cases(cfg, geometry, profile):
    """Enumerate actual lane centre lines on one independent carriageway."""
    lane_width = cfg["lane_width"]
    count_per_deck = geometry.lanes_per_deck
    # Match the CAD section's local axis: inner edge at negative lateral
    # coordinates, outer edge at positive coordinates; the other deck mirrors it.
    offset = (cfg["inner_margin"]-cfg["outer_margin"])/2.0
    centres = [offset+(i-(count_per_deck-1)/2.0)*lane_width
               for i in range(count_per_deck)]
    if geometry.deck_count == 1:
        names = [f"双向车道{i+1}" for i in range(count_per_deck)]
    else:
        names = ["内侧车道", "外侧车道"] if count_per_deck == 2 else ["内侧车道", "中间车道", "外侧车道"]
    cases = []
    combinations = (indexes for count in range(1, count_per_deck+1)
                    for indexes in itertools.combinations(range(count_per_deck), count))
    for indexes in combinations:
        count = len(indexes)
        factor = float(profile["traffic"]["lane_factors"][str(count)])
        eccentricities = [centres[i] for i in indexes]
        cases.append(dict(
            id="Q_LANE_" + "_".join(str(i+1) for i in indexes),
            name="＋".join(names[i] for i in indexes),
            active_lanes=[i+1 for i in indexes], lane_centres_m=eccentricities,
            lane_factor=factor, vertical_multiplier=count*factor,
            resultant_eccentricity_m=float(sum(eccentricities)/count),
            eccentricity_sum_m=float(factor*sum(eccentricities)),
            method="单箱整体截面合力法",
        ))
    return cases


def _apply_transverse(base_low, base_high, cases):
    low_values = np.asarray([base_low*c["vertical_multiplier"] for c in cases])
    high_values = np.asarray([base_high*c["vertical_multiplier"] for c in cases])
    low_index = np.argmin(low_values, axis=0)
    high_index = np.argmax(high_values, axis=0)
    rows = np.arange(low_values.shape[1])
    return (low_values[low_index, rows], high_values[high_index, rows],
            low_index, high_index)


def _combination_definition(key, profile):
    cfg = profile["combinations"][key]
    return CombinationDefinition(
        id=cfg["id"], name=cfg["name"],
        gamma_g_options=tuple(float(v) for v in cfg["gamma_g_options"]),
        gamma_q=float(cfg["gamma_q"]),
        vehicle_factor=float(cfg["vehicle_factor"]),
        include_impact=bool(cfg["include_impact"]),
        apply_importance_factor=bool(cfg["apply_importance_factor"]),
        source=cfg["source"],
    )


def _combine(dead1, dead2, live_low, live_high, definition, impact, importance):
    variants = []
    values = []
    live_factor = definition.gamma_q*definition.vehicle_factor
    if definition.include_impact:
        live_factor *= 1.0+impact
    outer_factor = importance if definition.apply_importance_factor else 1.0
    for g1, g2 in itertools.product(definition.gamma_g_options, repeat=2):
        permanent = g1*dead1+g2*dead2
        for branch, live_value in [("min", live_low), ("max", live_high)]:
            values.append(outer_factor*(permanent+live_factor*live_value))
            variants.append(dict(
                gamma_g1=g1, gamma_g2=g2, gamma_q=definition.gamma_q,
                vehicle_factor=definition.vehicle_factor,
                impact_factor=(1.0+impact) if definition.include_impact else 1.0,
                importance_factor=outer_factor, live_branch=branch,
            ))
    stack = np.asarray(values)
    rows = np.arange(stack.shape[1])
    low_index = np.argmin(stack, axis=0)
    high_index = np.argmax(stack, axis=0)
    return (stack[low_index, rows], stack[high_index, rows],
            low_index, high_index, variants)


def _input_audit(raw, cfg, geometry):
    audit = []
    for name, value in cfg.items():
        origin = "用户输入" if name in raw else "程序默认"
        starters = {"web_mid", "web_pier", "stirrup_diameter_mm"} if cfg["lanes"] == 6 else set()
        if cfg["main_span"] > 120:
            starters |= {"web_mid", "web_pier", "stirrup_diameter_mm", "top_thickness", "tip_thickness",
                         "bottom_mid", "bottom_pier", "top_haunch_horizontal", "top_haunch_vertical",
                         "bottom_chamfer_horizontal", "bottom_chamfer_vertical"}
        if name not in raw and name in starters:
            origin = "程序推导"
        unit = {"deck_elevation": "m", "longitudinal_slope": "1", "prestress_end_eccentricity_m": "m",
                "elevation_mode": "类别"}.get(name, field_unit(name))
        audit.append(dict(name=name, value=value, unit=unit, origin=origin))
    audit.extend([
        dict(name="left_side_span_actual", value=geometry.left_side, unit="m", origin="程序推导"),
        dict(name="right_side_span_actual", value=geometry.right_side, unit="m", origin="程序推导"),
        dict(name="deck_width", value=geometry.width, unit="m", origin="程序推导"),
        dict(name="total_width", value=geometry.total_width, unit="m", origin="程序推导"),
        dict(name="lanes_per_deck", value=geometry.lanes_per_deck, unit="条", origin="程序推导"),
        dict(name="deck_count", value=geometry.deck_count, unit="幅", origin="程序推导"),
        dict(name="height_mid_actual", value=geometry.section(geometry.left_side+geometry.main/2)["h"], unit="m", origin="程序推导"),
        dict(name="height_pier_actual", value=geometry.section(geometry.left_side)["h"], unit="m", origin="程序推导"),
    ])
    return audit


def traffic(cfg, beam, geometry, profile):
    frequency = beam.frequency()
    mu = impact_coefficient(frequency, profile)
    tc = profile["traffic"]
    cases = _transverse_cases(cfg, geometry, profile)
    return dict(
        class_name=tc["class"], qk=tc["qk_kn_per_m"], pk=tc["pk_bending_kn"],
        shear_point_factor=tc["shear_point_factor"],
        effective_lanes=max(c["vertical_multiplier"] for c in cases),
        lanes_per_deck=geometry.lanes_per_deck, frequency_hz=frequency,
        impact=float(mu), longitudinal_factor=1.0,
        controlling_span_m=float(max(geometry.spans)),
        longitudinal_factor_basis="按连续结构最大计算跨径；50～150 m不作纵向折减，150 m仍为1.0",
        transverse_method=cfg["transverse_method"], transverse_cases=cases,
        source=tc["source"],
    )


def analyse(raw, progress=lambda message: None):
    raw = dict(raw)
    cfg = validate(raw)
    if not 50 <= cfg["main_span"] <= 150:
        raise ValueError("本版主跨计算范围为50至150m")
    profile = get_profile(cfg["code_profile"])
    geometry = Geometry(cfg)
    material_profile = profile["materials"][cfg["concrete"]]
    material = {"E": material_profile["E_mpa"], **material_profile}

    progress("读取规范配置，建立单位、输入来源和荷载工况")
    x = geometry.mesh()
    element_mid = (x[:-1]+x[1:])/2
    element_section = geometry.section(element_mid)
    gz,gw=np.polynomial.legendre.leggauss(4)
    sample_x=element_mid[:,None]+np.diff(x)[:,None]*gz[None,:]/2
    average_area=geometry.section(sample_x)['A']@gw/2
    q_self = average_area*cfg["concrete_weight"]
    pavement_width = geometry.width-2*cfg["barrier_width"]
    q_pavement = pavement_width*cfg["pavement_thickness"]*cfg["pavement_weight"]
    q_barrier = cfg["barrier_line_load"]
    q_other = cfg["other_dead_load"]
    q_dead2 = q_pavement+q_barrier+q_other

    beam = Beam(x, material["E"]*1000*element_section["I"], geometry.supports,
                (q_self+q_dead2)/9.80665,
                ei_function=lambda t:material['E']*1000*geometry.section(t)['I'])
    progress("计算分项恒载的内力、支反力和竖向位移")
    g1 = beam.distributed(lambda t:-geometry.section(t)['A']*cfg['concrete_weight'])
    g2_pavement = beam.distributed(-q_pavement)
    g2_barrier = beam.distributed(-q_barrier)
    g2_other = beam.distributed(-q_other)
    g2 = {key: g2_pavement[key]+g2_barrier[key]+g2_other[key]
          for key in ["u", "M", "V", "R"]}
    dead = {key: g1[key]+g2[key] for key in ["u", "M", "V", "R"]}

    progress("计算纵向影响线、横向车道工况及汽车作用包络")
    influences = beam.influences()
    traffic_data = traffic(cfg, beam, geometry, profile)
    influence_by_kind = {
        "M": influences["M"], "V": influences["V"],
        "W": _station_displacements(influences["u"]), "R": influences["R"],
    }
    point_factor = {"M": 1.0, "W": 1.0, "V": traffic_data["shear_point_factor"],
                    "R": traffic_data["shear_point_factor"]}
    live = {}
    live_provenance = {}
    for kind, influence in influence_by_kind.items():
        base_low, base_high, trace = _single_lane_envelope(
            influence, influences["weights"], influences["load_x"],
            traffic_data["qk"], traffic_data["pk"]*point_factor[kind])
        low, high, low_case, high_case = _apply_transverse(
            base_low, base_high, traffic_data["transverse_cases"])
        live[kind] = (low, high)
        trace.update(transverse_case_min=low_case, transverse_case_max=high_case)
        live_provenance[kind] = trace

    dead_response = {
        "M": (g1["M"], g2["M"]), "V": (g1["V"], g2["V"]),
        "W": (_station_displacements(g1["u"]), _station_displacements(g2["u"])),
        "R": (g1["R"], g2["R"]),
    }
    dead_total = {kind: parts[0]+parts[1] for kind, parts in dead_response.items()}

    progress("按规范配置生成基本、标准、频遇和准永久组合并保存控制来源")
    definitions = {key: _combination_definition(key, profile)
                   for key in ["uls", "standard", "frequent", "quasi"]}
    combined = {}
    combination_indices = {}
    combination_variants = {}
    for kind in ["M", "V", "W", "R"]:
        combined[kind] = {}
        for combo_key, definition in definitions.items():
            low, high, low_index, high_index, variants = _combine(
                dead_response[kind][0], dead_response[kind][1],
                live[kind][0], live[kind][1], definition,
                traffic_data["impact"], cfg["importance_factor"])
            combined[kind][combo_key] = (low, high)
            combination_indices[f"{kind}_{combo_key}_min"] = low_index
            combination_indices[f"{kind}_{combo_key}_max"] = high_index
            combination_variants[f"{kind}_{combo_key}"] = variants

    stations = beam.stations
    section = geometry.section(stations)
    analysis = dict(
        x=stations, height=section["h"], area=section["A"], inertia=section["I"],
        section_modulus_top=section["Wt"], section_modulus_bottom=section["Wb"],
        M_dead1=g1["M"], M_dead2=g2["M"], M_dead=dead_total["M"],
        V_dead1=g1["V"], V_dead2=g2["V"], V_dead=dead_total["V"],
        deflection_dead1=dead_response["W"][0], deflection_dead2=dead_response["W"][1],
        deflection_dead=dead_total["W"],
        M_live_min=live["M"][0], M_live_max=live["M"][1],
        V_live_min=live["V"][0], V_live_max=live["V"][1],
        deflection_live_min=live["W"][0], deflection_live_max=live["W"][1],
    )
    for kind, prefix in [("M", "M"), ("V", "V"), ("W", "deflection")]:
        for combo_key in definitions:
            low, high = combined[kind][combo_key]
            analysis[f"{prefix}_{combo_key}_min"] = low
            analysis[f"{prefix}_{combo_key}_max"] = high
    analysis["V_uls"] = np.maximum(abs(analysis["V_uls_min"]), abs(analysis["V_uls_max"]))

    progress("初估纵向钢束，计算摩阻、锚缩和长期预应力损失")
    prestress = design_prestress(cfg, geometry, beam, analysis, material_profile)
    analysis.update(prestress.pop("analysis_update"))
    progress("计算预应力主次效应及P1、P2双主墩施工阶段")
    construction = analyse_construction(cfg, geometry, prestress, material, analysis)
    progress("进行抗弯、抗剪、抗裂、应力和挠度具名验算")
    structural = verify_structure(cfg, geometry, analysis, profile, prestress,
                                  construction, traffic_data)
    analysis.update(structural.pop("analysis_update"))

    reactions = dict(names=["A0", "P1", "P2", "A3"], x=geometry.supports,
                     dead1=g1["R"], dead2=g2["R"], dead=dead_total["R"],
                     live_min=live["R"][0], live_max=live["R"][1])
    for combo_key in definitions:
        reactions[f"{combo_key}_min"] = combined["R"][combo_key][0]
        reactions[f"{combo_key}_max"] = combined["R"][combo_key][1]

    locations = [
        ("左桥台", 0.0), ("左边跨跨中", geometry.left_side/2),
        ("左主墩", geometry.left_side), ("主跨四分点", geometry.left_side+geometry.main/4),
        ("主跨跨中", geometry.left_side+geometry.main/2),
        ("右主墩", geometry.left_side+geometry.main),
        ("右边跨跨中", geometry.length-geometry.right_side/2), ("右桥台", geometry.length),
    ]
    for name, array, fn in [
        ("最大正弯矩", analysis["M_uls_max"], np.argmax),
        ("最大负弯矩", analysis["M_uls_min"], np.argmin),
        ("最大剪力", analysis["V_uls"], np.argmax),
        ("最大竖向位移", np.maximum(abs(analysis["deflection_standard_total_min"]),
                                  abs(analysis["deflection_standard_total_max"])), np.argmax),
    ]:
        locations.append((name, float(stations[int(fn(array))])))

    controls = []
    transverse_cases = traffic_data["transverse_cases"]
    for name, location in locations:
        nearest = float(stations[np.argmin(abs(stations-location))])
        ids = np.where(abs(stations-nearest) < 1e-7)[0]
        j = int(ids[0])
        sec = geometry.section(nearest)
        governing = {}
        for kind in ["M", "V", "W"]:
            for bound in ["min", "max"]:
                variant_index = int(combination_indices[f"{kind}_uls_{bound}"][j])
                variant = combination_variants[f"{kind}_uls"][variant_index]
                branch = variant["live_branch"]
                case_index = int(live_provenance[kind][f"transverse_case_{branch}"][j])
                governing[f"{kind}_{bound}"] = dict(
                    combination_id=definitions["uls"].id, factors=variant,
                    transverse_case=transverse_cases[case_index]["id"],
                    transverse_case_name=transverse_cases[case_index]["name"],
                    point_load_x_m=float(live_provenance[kind][f"load_x_{branch}"][j]),
                )
        controls.append(dict(
            name=name, x=nearest, height=sec["h"], area=sec["A"], inertia=sec["I"],
            section_modulus_top=sec["Wt"], section_modulus_bottom=sec["Wb"],
            M_uls_min=float(min(analysis["M_uls_min"][ids])),
            M_uls_max=float(max(analysis["M_uls_max"][ids])),
            V_uls_min=float(min(analysis["V_uls_min"][ids])),
            V_uls_max=float(max(analysis["V_uls_max"][ids])),
            deflection_standard_min=float(min(analysis["deflection_standard_min"][ids])),
            deflection_standard_max=float(max(analysis["deflection_standard_max"][ids])),
            deflection_standard_total_min=float(min(analysis["deflection_standard_total_min"][ids])),
            deflection_standard_total_max=float(max(analysis["deflection_standard_total_max"][ids])),
            tendon_eccentricity=float(np.mean(np.asarray(analysis["tendon_eccentricity"])[ids])),
            prestress_force_effective=float(np.mean(np.asarray(analysis["prestress_force_effective"])[ids])),
            stress_top_standard_min=float(min(np.asarray(analysis["stress_top_standard_min"])[ids])),
            stress_top_standard_max=float(max(np.asarray(analysis["stress_top_standard_max"])[ids])),
            stress_bottom_standard_min=float(min(np.asarray(analysis["stress_bottom_standard_min"])[ids])),
            stress_bottom_standard_max=float(max(np.asarray(analysis["stress_bottom_standard_max"])[ids])),
            flexural_capacity_positive=float(np.mean(np.asarray(analysis["flexural_capacity_positive"])[ids])),
            flexural_capacity_negative=float(np.mean(np.asarray(analysis["flexural_capacity_negative"])[ids])),
            shear_capacity=float(np.mean(np.asarray(analysis["shear_capacity"])[ids])),
            governing=governing,
        ))

    volume = float(np.sum(average_area*beam.L))
    total_dead_weight = float(np.sum((q_self+q_dead2)*beam.L))
    balance = float(abs(sum(dead["R"])-total_dead_weight))

    load_cases = [
        LoadCase("G1_SELF", "主梁混凝土自重", "permanent", float(np.mean(q_self)), "kN/m",
                 "成桥一期恒载", "实际倒角毛截面面积×混凝土容重",
                 f"沿桥变化，范围{min(q_self):.3f}～{max(q_self):.3f} kN/m"),
        LoadCase("G2_PAVEMENT", "桥面铺装", "permanent", q_pavement, "kN/m",
                 "成桥二期恒载", "输入桥面宽度、铺装厚度和容重", "全桥均布"),
        LoadCase("G2_BARRIER", "两侧护栏", "permanent", q_barrier, "kN/m",
                 "成桥二期恒载", "用户输入", "每幅两侧护栏合计线荷载"),
        LoadCase("G2_OTHER", "其他附属恒载", "permanent", q_other, "kN/m",
                 "成桥二期恒载", "用户输入", "每幅其他均布线荷载"),
        LoadCase("Q_TRAFFIC", "公路-I级汽车荷载", "variable", traffic_data["qk"], "kN/m",
                 "成桥活载", traffic_data["source"],
                 f"集中荷载{traffic_data['pk']:.1f} kN；横向工况{len(transverse_cases)}个"),
        LoadCase("P_PRESTRESS", "纵向预应力", "prestress", prestress["jacking_force_kn"], "kN",
                 "施工与成桥阶段", "用户输入钢绞线和损失参数",
                 f"等效合力线；{prestress['tendon_count']}束×{prestress['strands_per_tendon']}根"),
        LoadCase("C_FORM_TRAVELER", "挂篮等效荷载", "construction", cfg["form_traveler_load"], "kN",
                 "对称悬臂施工阶段", "用户输入",
                 "每个悬臂端的等效竖向集中荷载"),
    ]

    records = [
        CalculationRecord("SEC_GROSS", "section", "毛截面性质",
                          "A=A_outer-A_void; I=I_outer-I_void-A*y_c^2",
                          {"section_count": len(stations)}, "已按实际倒角多边形逐截面计算",
                          "m²,m⁴", "geometry.py"),
        CalculationRecord("G1", "load", "一期恒载", "g1(x)=A(x)*gamma_c",
                          {"gamma_c": cfg["concrete_weight"]},
                          float(np.sum(q_self*beam.L)), "kN", "用户输入与实际截面"),
        CalculationRecord("G2", "load", "二期恒载",
                          "g2=B_p*t_p*gamma_p+g_barrier+g_other",
                          {"pavement_width": pavement_width,
                           "pavement_thickness": cfg["pavement_thickness"],
                           "pavement_weight": cfg["pavement_weight"],
                           "barrier": q_barrier, "other": q_other},
                          q_dead2, "kN/m", "用户输入"),
        CalculationRecord("FREQ", "dynamic", "一阶竖弯基频",
                          "(K-omega^2*M)*phi=0; f=omega/(2*pi)", {},
                          traffic_data["frequency_hz"], "Hz", "一致质量矩阵"),
        CalculationRecord("IMPACT", "dynamic", "汽车冲击系数",
                          "mu=0.1767*ln(f)-0.0157（区间内）",
                          {"frequency_hz": traffic_data["frequency_hz"]},
                          traffic_data["impact"], "1", traffic_data["source"]),
        CalculationRecord("TRAFFIC_TRANSVERSE", "load", "横向车道工况",
                          "S_Q=sum(xi_i*S_lane_i)",
                          {"lane_centres_m": transverse_cases[-1]["lane_centres_m"],
                           "lanes_per_deck": geometry.lanes_per_deck,
                           "lane_factors": profile["traffic"]["lane_factors"]},
                          len(transverse_cases), "个工况", traffic_data["source"]),
        CalculationRecord("DISPLACEMENT", "analysis", "竖向位移作用效应", "K*u=F",
                          {"model": "Euler-Bernoulli beam"},
                          float(max(abs(analysis["deflection_standard_min"]))), "m",
                          "与内力相同有限元模型；计入预应力反拱后另行验算"),
        CalculationRecord("P_REQUIRED", "prestress", "有效预应力需求",
                          "P_req=1.05*(M-sigma_allow*W)/(W/A+e)",
                          {"basis": "频遇组合与预应力度类别抗裂限值"},
                          prestress["required_effective_force_max_kn"], "kN",
                          "按频遇组合及预应力度类别抗裂限值的方案初估"),
        CalculationRecord("P_END_KERN", "prestress", "桥台端等效钢束偏心初选",
                          "-W_b/A <= e_end <= W_t/A; sigma_top=P/A-P*e/W_t; sigma_bottom=P/A+P*e/W_b",
                          {"mode": prestress["end_anchor_rule"]["mode"],
                           "kern_lower_m": prestress["end_anchor_rule"]["kern_lower_m"],
                           "kern_upper_m": prestress["end_anchor_rule"]["kern_upper_m"]},
                          prestress["end_anchor_rule"]["eccentricity_m"], "m",
                          prestress["end_anchor_rule"]["source"]),
        CalculationRecord("P_LOSS", "prestress", "预应力损失",
                          "sigma_p=sigma_con*exp[-(mu*theta+k*x)]-Delta_sigma",
                          {"mu": cfg["friction_mu"], "k": cfg["wobble_k_per_m"],
                           "slip_mm": cfg["anchorage_slip_mm"]},
                          prestress["loss_summary"]["total_mpa_mean"], "MPa",
                          "双端张拉，采用左右端较大剩余应力"),
        CalculationRecord("P_SECONDARY", "prestress", "预应力次效应",
                          "K*u_p=F_p; M=M_primary+M_secondary",
                          {"tendon_count": prestress["tendon_count"]},
                          float(np.max(abs(analysis["M_prestress_secondary"]))), "kN*m",
                          "连续体系等效初始弯矩法"),
        CalculationRecord("C_STAGE", "construction", "双主墩对称悬臂施工阶段",
                          "M_root=-integral[q(s)*s ds]-P_traveler*l-P_e*e",
                          {"segment_length_m": cfg["segment_length"],
                           "stage_count": construction["segment_stage_count"],
                           "pier_count": len(construction["piers"])},
                          construction["max_abs_stage_stress_mpa"], "MPa",
                          "P1、P2根部控制截面分别计算并逐阶段取控制值"),
        CalculationRecord("ULS_FLEXURE", "verification", "正截面抗弯承载力",
                          "gamma0*M_d <= M_u",
                          {"top_bars": structural["reinforcement"]["top_bar_count"],
                           "bottom_bars": structural["reinforcement"]["bottom_bar_count"]},
                          max(structural["checks"]["flexure"]["positive"]["max_utilization"],
                              structural["checks"]["flexure"]["negative"]["max_utilization"]),
                          "利用率", "JTG 3362—2018 第5.2.1～5.2.3条"),
        CalculationRecord("ULS_SHEAR", "verification", "斜截面抗剪承载力",
                          "max(abs(gamma0*V_d,min-V_pb),abs(gamma0*V_d,max-V_pb)) <= V_cs; V_pb is signed",
                          structural["checks"]["shear"]["stirrup"],
                          structural["checks"]["shear"]["max_utilization"],
                          "利用率", "JTG 3362—2018 第5.2.9～5.2.13条"),
        CalculationRecord("SLS_CRACK", "verification", "抗裂验算",
                          ("sigma_st-sigma_pc <= 0 (全预应力)" if cfg['prestress_class']=='full' else
                           "sigma_st-sigma_pc <= 0.5*f_tk (A类现浇)"),
                          {"class": cfg["prestress_class"]},
                          structural["checks"]["crack_resistance"]["maximum_edge_tension_mpa"],
                          "MPa", "JTG 3362—2018 第6.3.1～6.3.3条"),
        CalculationRecord("SLS_CONCRETE_STRESS", "verification", "使用阶段混凝土压应力",
                          "sigma_kc+sigma_pt <= 0.50*fck",
                          {"limit_mpa": structural["checks"]["concrete_stress"]["compression_limit_mpa"]},
                          structural["checks"]["concrete_stress"]["maximum_compression_mpa"],
                          "MPa", "JTG 3362—2018 第7.1.5条"),
        CalculationRecord("SLS_DEFLECTION", "verification", "活载挠度与预拱度",
                          "B0=.95 Ec I0; eta_theta*.7*f_Q(no impact) <= L/600; f_lt=eta_theta*f_frequent+2*f_p",
                          {"eta_theta": structural["checks"]["deflection"]["long_term_factor"]},
                          max(v["utilization"] for v in structural["checks"]["deflection"]["span_checks"]),
                          "利用率", "JTG 3362—2018 第6.5.3～6.5.5条"),
        CalculationRecord("TEMP_CONCRETE_STRESS", "verification", "施工阶段混凝土压应力",
                          "sigma_cc <= 0.80*fck",
                          {"limit_mpa": structural["checks"]["temporary_concrete_stress"]["compression_limit_mpa"]},
                          structural["checks"]["temporary_concrete_stress"]["maximum_compression_mpa"],
                          "MPa", "JTG 3362—2018 第7.2节"),
    ]

    def sensitivity_case(case_id, name, permanent_factor=1.0, traffic_factor=1.0):
        values = {}
        for kind in ["M", "V"]:
            low, high, *_ = _combine(
                permanent_factor*dead_response[kind][0],
                permanent_factor*dead_response[kind][1],
                traffic_factor*live[kind][0], traffic_factor*live[kind][1],
                definitions["uls"], traffic_data["impact"], cfg["importance_factor"])
            values[f"{kind}_min"] = float(np.min(low))
            values[f"{kind}_max"] = float(np.max(high))
            values[f"{kind}_abs_max"] = float(max(np.max(abs(low)), np.max(abs(high))))
        return dict(id=case_id, name=name, permanent_factor=permanent_factor,
                    traffic_factor=traffic_factor, **values)

    sensitivity = [
        sensitivity_case("BASE", "基准参数"),
        sensitivity_case("G_PLUS_5", "恒载增加5%", permanent_factor=1.05),
        sensitivity_case("Q_PLUS_5", "汽车荷载增加5%", traffic_factor=1.05),
    ]
    base_sensitivity = sensitivity[0]
    for row in sensitivity:
        row["moment_change_ratio"] = row["M_abs_max"]/base_sensitivity["M_abs_max"]-1.0
        row["shear_change_ratio"] = row["V_abs_max"]/base_sensitivity["V_abs_max"]-1.0

    chapter_by_category = {
        "section": "第2章", "load": "第3至4章", "dynamic": "第4章",
        "analysis": "第5章", "prestress": "第6章", "construction": "第7章",
        "verification": "第8至9章",
    }
    calculation_trace = []
    for record in records:
        calculation_trace.append(dict(
            id=record.id, chapter=chapter_by_category.get(record.category, "计算记录"),
            name=record.purpose, input=record.inputs, formula=record.formula,
            intermediate={"category": record.category, "purpose": record.purpose},
            result=record.result, unit=record.unit, source=record.source,
            result_path=f"calculation_records[id={record.id}]",
        ))
    for index, control in enumerate(controls[:8]):
        calculation_trace.append(dict(
            id=f"CTRL_M_{index+1:02d}", chapter="第5章",
            name=control["name"]+"基本组合最大弯矩",
            input={"x_m": control["x"], "combination": "ULS_BASIC"},
            formula="Sd=gamma0*(gammaG1*SG1+gammaG2*SG2+1.4*(1+mu)*SQ)",
            intermediate=control["governing"]["M_max"], result=control["M_uls_max"],
            unit="kN*m", source="JTG D60—2015及控制车位搜索",
            result_path=f"controls[{index}].M_uls_max",
        ))
    for row in sensitivity:
        calculation_trace.append(dict(
            id="SENS_"+row["id"], chapter="第10章", name=row["name"],
            input={"permanent_factor": row["permanent_factor"],
                   "traffic_factor": row["traffic_factor"]},
            formula="保持组合规则不变，分别缩放恒载或汽车荷载后重新形成ULS包络",
            intermediate={"M_min": row["M_min"], "M_max": row["M_max"],
                          "V_min": row["V_min"], "V_max": row["V_max"]},
            result=row["M_abs_max"], unit="kN*m", source="程序参数敏感性复算",
            result_path=f"sensitivity[{row['id']}].M_abs_max",
        ))

    live_trace = []
    for name, location in locations[:8]:
        ids = np.where(abs(stations-location) < 1e-7)[0]
        for j in ids:
            side = ("左侧" if j % 2 else "右侧") if len(ids) > 1 and location in geometry.supports else ""
            if len(ids) > 1 and not side and j != ids[0]:
                continue
            item = dict(name=name+side, x=float(stations[j]), station_index=int(j))
            for kind in ["M", "V", "W"]:
                tr = live_provenance[kind]
                item[kind] = dict(
                    positive_area=float(tr["positive_area"][j]),
                    negative_area=float(tr["negative_area"][j]),
                    eta_max=float(tr["eta_max"][j]), eta_min=float(tr["eta_min"][j]),
                    load_x_max=float(tr["load_x_max"][j]), load_x_min=float(tr["load_x_min"][j]),
                    transverse_case_max=transverse_cases[int(tr["transverse_case_max"][j])]["id"],
                    transverse_case_min=transverse_cases[int(tr["transverse_case_min"][j])]["id"],
                )
            live_trace.append(item)

    details = dict(
        elements=dict(x0=x[:-1], x1=x[1:], area=average_area,
                      inertia=element_section["I"], dead1=q_self),
        live_trace=live_trace, live_provenance=live_provenance,
        combination_indices=combination_indices, combination_variants=combination_variants,
        pavement_width=pavement_width, pavement_load=q_pavement,
        dead1_weight=float(sum(q_self*beam.L)), dead2_weight=float(q_dead2*geometry.length),
    )

    moment_min_j = int(np.argmin(np.asarray(analysis["M_uls_min"])))
    moment_max_j = int(np.argmax(np.asarray(analysis["M_uls_max"])))
    shear_candidates = np.maximum(abs(np.asarray(analysis["V_uls_min"])),
                                  abs(np.asarray(analysis["V_uls_max"])))
    shear_j = int(np.argmax(shear_candidates))
    shear_value = (analysis["V_uls_min"][shear_j]
                   if abs(analysis["V_uls_min"][shear_j]) >= abs(analysis["V_uls_max"][shear_j])
                   else analysis["V_uls_max"][shear_j])
    checks = structural["checks"]
    deflection_control = max(checks["deflection"]["span_checks"],
                             key=lambda item: item["utilization"])
    stage_control = max(construction["stages"],
                        key=lambda item: max(abs(item["top_stress_mpa"]),
                                             abs(item["bottom_stress_mpa"])))
    presentation_summary = dict(
        design_boundary=dict(
            completed="纵向平面梁作用效应、预应力、施工阶段与6项具名验算",
            out_of_scope="空间、横向局部、锚固区实体与下部结构承载力"),
        critical_effects=dict(
            negative_moment_knm=float(analysis["M_uls_min"][moment_min_j]),
            negative_moment_x_m=float(stations[moment_min_j]),
            positive_moment_knm=float(analysis["M_uls_max"][moment_max_j]),
            positive_moment_x_m=float(stations[moment_max_j]),
            shear_kn=float(shear_value), shear_x_m=float(stations[shear_j])),
        prestress=dict(
            tendon_count=prestress["tendon_count"],
            strands_per_tendon=prestress["strands_per_tendon"],
            total_loss_mpa=prestress["loss_summary"]["total_mpa_mean"],
            total_loss_ratio=prestress["loss_summary"]["total_ratio_mean"],
            effective_ratio_min=prestress["loss_summary"]["effective_ratio_min"]),
        construction=dict(
            checked_piers=[pier["pier_id"] for pier in construction["piers"]],
            governing_pier=stage_control["governing_pier_id"],
            governing_stage=stage_control["stage_id"],
            governing_stage_name=stage_control["name"],
            max_abs_stress_mpa=float(max(abs(stage_control["top_stress_mpa"]),
                                         abs(stage_control["bottom_stress_mpa"]))),
            compression_limit_mpa=checks["temporary_concrete_stress"]["compression_limit_mpa"]),
        resistance=dict(
            positive_flexure_utilization=checks["flexure"]["positive"]["max_utilization"],
            negative_flexure_utilization=checks["flexure"]["negative"]["max_utilization"],
            shear_utilization=checks["shear"]["max_utilization"]),
        service=dict(
            crack_edge_utilization=(checks["crack_resistance"]["maximum_edge_tension_mpa"]/
                                    checks["crack_resistance"]["edge_limit_mpa"] if checks["crack_resistance"]["edge_limit_mpa"]>0 else
                                    (0.0 if checks["crack_resistance"]["maximum_edge_tension_mpa"]<=1e-9 else None)),
            crack_principal_utilization=checks["crack_resistance"]["maximum_principal_tension_mpa"]/
                                         checks["crack_resistance"]["principal_limit_mpa"],
            concrete_compression_utilization=checks["concrete_stress"]["maximum_compression_mpa"]/
                                             checks["concrete_stress"]["compression_limit_mpa"],
            deflection_utilization=deflection_control["utilization"],
            deflection_control_span=deflection_control["span"],
            maximum_live_deflection_mm=deflection_control["maximum_frequent_long_term_mm"],
            deflection_limit_mm=deflection_control["limit_mm"]),
    )

    ratio = geometry.main/cfg["height_reference_span"]
    named = structural["summary"]
    course_complete = bool(named["all_named_checks_pass"])
    status_code = "COURSE_SCOPE_COMPLETE" if course_complete else "COURSE_SCOPE_FAILED"
    status = (f"{status_code}｜课程设计范围内{named['total']}项具名验算中"
              f"{named['passed']}项通过；工程级横向、局部与空间分析属课程范围外")
    payload = dict(
        created_at=datetime.now().isoformat(timespec="seconds"),
        state_schema="bridgegen.design_state.v0.12", input=cfg,
        input_audit=_input_audit(raw, cfg, geometry), unit_system=UNIT_SYSTEM,
        code_profile=profile, status=status, course_scope_complete=course_complete,
        complete_code_compliance=False,
        calculation_scope="course_design_global_longitudinal_effects_and_named_section_checks",
        controls=controls, analysis=analysis, reactions=reactions,
        prestress=prestress, construction_stages=construction,
        structural_verification=structural,
        calculation_details=details, calculation_records=records_to_dict(records),
        calculation_trace=calculation_trace, sensitivity=sensitivity,
        presentation_summary=presentation_summary,
        load_cases=records_to_dict(load_cases),
        combinations=[asdict(definitions[key]) for key in definitions],
        geometry=dict(
            spans=geometry.spans, supports=geometry.supports, total_length=geometry.length,
            left_side_span=geometry.left_side, right_side_span=geometry.right_side,
            side_span_mode=cfg["side_span_mode"], is_symmetric=geometry.is_symmetric,
            width=geometry.width, total_width=geometry.total_width, deck_count=geometry.deck_count,
            lanes_per_deck=geometry.lanes_per_deck, box_width=geometry.box_width, cells=1, height_scale=1.0,
            span_height_ratio=ratio,
            height_mid=geometry.section(geometry.left_side+geometry.main/2)["h"],
            height_pier=geometry.section(geometry.left_side)["h"],
            minimum_mid_height_initial_m=1.8,
            section_initial_guess_rule=section_suggestions(cfg["main_span"],cfg["lanes"])["suggestion_basis"],
            curve_exponent=cfg["height_curve_exponent"],
            elevation=dict(mode=cfg["elevation_mode"],
                datum_m=cfg["deck_elevation"], longitudinal_slope=cfg["longitudinal_slope"],
                reference_location="全桥长度中点、结构顶板横向中心线",
                supports_top_m=geometry.deck_top_elevation(geometry.supports),
                supports_bottom_m=geometry.deck_top_elevation(geometry.supports)-geometry.section(geometry.supports)["h"],
                datum_source=("用户明确提供的绝对高程；未推导地形或水位" if cfg["elevation_mode"] == "absolute"
                              else "相对高程基准；不代表现场绝对高程")),
        ),
        loads=dict(
            traffic=traffic_data, dead1_min=float(min(q_self)), dead1_max=float(max(q_self)),
            dead2=q_dead2,
            dead2_components=dict(pavement=q_pavement, barrier=q_barrier, other=q_other),
            total_dead_weight_per_deck=total_dead_weight,
        ),
        material=material,
        quantities=dict(concrete_per_deck_m3=volume, concrete_total_m3=geometry.deck_count*volume),
        verification=dict(
            model=("单幅双向；采用成桥毛截面平面连续梁模型" if geometry.deck_count == 1
                   else "左右两幅相互独立；每幅采用成桥毛截面平面连续梁模型"),
            elements=beam.ne, mesh_nodes=len(x), force_balance_error_kn=balance,
            element_integration='four_point_Gauss_variable_EI_and_self_weight',
            max_standard_deflection_mm=float(
                max(np.max(abs(analysis["deflection_standard_total_min"])),
                    np.max(abs(analysis["deflection_standard_total_max"]))))*1000,
            max_abs_stage_stress_mpa=construction["max_abs_stage_stress_mpa"],
            effective_prestress_margin_kn=prestress["minimum_force_margin_kn"],
            transverse_scope="记录实际车道位置与控制横向工况；空间扭转响应未计算",
            elevation_scope="高程与纵坡用于制图定位；纵向计算采用跨度的水平投影，未引入斜梁轴力或地形作用",
            named_checks=structural["summary"],
        ),
        candidates=span_candidates(cfg), references=REFERENCES,
        out_of_course_scope=OUT_OF_COURSE_SCOPE,
    )
    state = DesignState.freeze(VERSION, status_code, payload)
    return serial(state.to_dict())

