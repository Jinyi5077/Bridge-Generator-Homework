"""Simplified balanced-cantilever construction-stage calculations for both main piers."""
import math
import numpy as np


def _cantilever_response(cfg, geometry, length, pier_x, direction):
    """Return one-arm response on the main-span side of a selected pier."""
    s = np.linspace(0.0, length, max(41, int(math.ceil(length/0.25))+1))
    x = pier_x+direction*s
    sec = geometry.section(x)
    q = sec["A"]*cfg["concrete_weight"]
    traveler = cfg["form_traveler_load"]
    root_shear = float(np.trapezoid(q, s)+traveler)
    self_moment = -float(np.trapezoid(q*s, s))
    traveler_moment = -traveler*length
    moment = np.zeros_like(s)
    for i, si in enumerate(s):
        moment[i] = -float(np.trapezoid(q[i:]*(s[i:]-si), s[i:]))-traveler*(length-si)
    e_concrete = cfg.get("concrete_E_mpa", 34500.0)*1000.0
    tip_deflection = float(np.trapezoid(moment*(-(length-s))/(e_concrete*sec["I"]), s))
    return self_moment, traveler_moment, root_shear, tip_deflection


def _pier_stages(cfg, geometry, prestress, analysis, pier_id, pier_x, direction,
                 cantilever_length, stage_count):
    """Calculate the construction sequence at one main pier."""
    segment = cfg["segment_length"]
    px = np.asarray(prestress["profile"]["x"])
    e_pier = float(np.interp(pier_x, px, prestress["profile"]["eccentricity"]))
    p_immediate = float(np.interp(pier_x, px, prestress["profile"]["force_immediate"]))
    tendon_count = max(1, int(round(np.interp(
        pier_x, px, prestress["profile"]["active_tendon_count"]))))
    force_per_tendon = p_immediate/tendon_count
    sec = geometry.section(pier_x)
    stages = []
    previous_tendons = 0
    for number in range(1, stage_count+1):
        length = min(number*segment, cantilever_length)
        self_m, traveler_m, root_v, tip_w = _cantilever_response(
            cfg, geometry, length, pier_x, direction)
        external_moment = self_m+traveler_m
        force_coefficient = 1.0/sec["A"]-e_pier/sec["Wt"]
        required_force = max(0.0, -(external_moment/sec["Wt"])/max(force_coefficient, 1e-12))
        activated_tendons = max(previous_tendons, int(math.ceil(required_force/force_per_tendon)))
        activated_tendons = min(tendon_count, max(1, activated_tendons))
        previous_tendons = activated_tendons
        force = force_per_tendon*activated_tendons
        balance_moment = -force*e_pier
        top = (force/sec["A"]-force*e_pier/sec["Wt"]+external_moment/sec["Wt"])/1000.0
        bottom = (force/sec["A"]+force*e_pier/sec["Wb"]-external_moment/sec["Wb"])/1000.0
        stages.append({
            "stage_id": f"C{number:02d}", "name": f"对称悬臂第{number}节段",
            "pier_id": pier_id, "pier_x_m": pier_x,
            "system": "双悬臂静定阶段", "active_segments_each_side": number,
            "active_length_each_side_m": length,
            "self_weight_root_moment_knm": self_m,
            "traveler_root_moment_knm": traveler_m,
            "external_root_moment_knm": external_moment,
            "prestress_force_kn": force,
            "required_prestress_force_kn": required_force,
            "activated_tendons": activated_tendons,
            "total_tendons": tendon_count,
            "activated_tendon_ratio": activated_tendons/tendon_count,
            "prestress_balance_moment_knm": balance_moment,
            "net_root_moment_knm": external_moment+balance_moment,
            "root_shear_kn": root_v,
            "tip_deflection_mm": tip_w*1000.0,
            "top_stress_mpa": top, "bottom_stress_mpa": bottom,
            "active_loads": ["已浇节段自重", "挂篮等效集中荷载"],
            "active_prestress": "按墩顶上缘零拉应力需求取最少整束，并保持已张拉束数单调增加",
        })

    station_x = np.asarray(analysis["x"])
    pier_ids = np.where(np.isclose(station_x, pier_x, atol=1e-8))[0]
    j = int(pier_ids[0])
    closure = {
        "stage_id": "CLOSE", "name": "边跨与中跨合龙、体系转换",
        "pier_id": pier_id, "pier_x_m": pier_x,
        "system": "连续体系形成", "active_segments_each_side": stage_count,
        "active_length_each_side_m": cantilever_length,
        "self_weight_root_moment_knm": stages[-1]["self_weight_root_moment_knm"],
        "traveler_root_moment_knm": 0.0,
        "external_root_moment_knm": float(np.asarray(analysis["M_dead1"])[j]),
        "prestress_force_kn": p_immediate,
        "required_prestress_force_kn": p_immediate,
        "activated_tendons": tendon_count, "total_tendons": tendon_count,
        "activated_tendon_ratio": 1.0,
        "prestress_balance_moment_knm": float(-p_immediate*e_pier),
        "net_root_moment_knm": float(np.asarray(analysis["M_dead1"])[j]
                                      + np.asarray(analysis["M_prestress_total"])[j]),
        "root_shear_kn": float(abs(np.asarray(analysis["V_dead1"])[j])),
        "tip_deflection_mm": 0.0,
        "top_stress_mpa": float(np.asarray(analysis["stress_top_transfer"])[j]),
        "bottom_stress_mpa": float(np.asarray(analysis["stress_bottom_transfer"])[j]),
        "active_loads": ["一期恒载"],
        "active_prestress": "成桥即时有效预应力及连续体系次效应",
    }
    stages.append(closure)
    service_moment = max([analysis["M_standard_min"][j], analysis["M_standard_max"][j]], key=abs)
    service_top = max([analysis["stress_top_standard_min"][j],
                       analysis["stress_top_standard_max"][j]], key=abs)
    service_bottom = max([analysis["stress_bottom_standard_min"][j],
                          analysis["stress_bottom_standard_max"][j]], key=abs)
    p_effective_pier = float(np.interp(pier_x, px, prestress["profile"]["force_effective"]))
    completed = dict(closure)
    completed.update({
        "stage_id": "SERVICE", "name": "二期恒载完成及标准组合",
        "system": "成桥连续体系", "external_root_moment_knm": float(service_moment),
        "prestress_force_kn": p_effective_pier,
        "prestress_balance_moment_knm": float(-p_effective_pier*e_pier),
        "net_root_moment_knm": float(service_moment+analysis["M_prestress_total"][j]),
        "top_stress_mpa": float(service_top), "bottom_stress_mpa": float(service_bottom),
        "active_loads": ["一期恒载", "二期恒载", "公路I级汽车标准组合"],
        "active_prestress": "长期有效预应力及连续体系次效应",
    })
    stages.append(completed)
    governing = max(stages, key=lambda row: max(abs(row["top_stress_mpa"]),
                                                  abs(row["bottom_stress_mpa"])))
    return {
        "pier_id": pier_id, "pier_x_m": pier_x, "main_span_direction": direction,
        "stages": stages, "governing_stage": governing["stage_id"],
        "governing_stage_name": governing["name"],
        "max_abs_stage_stress_mpa": float(max(abs(governing["top_stress_mpa"]),
                                                 abs(governing["bottom_stress_mpa"]))),
    }


def analyse_construction(cfg, geometry, prestress, material, analysis):
    """Calculate both main-pier sequences and expose the governing result by stage."""
    cfg = dict(cfg, concrete_E_mpa=material["E"])
    segment = cfg["segment_length"]
    cantilever_length = min(geometry.main/2.0, geometry.left_side, geometry.right_side)
    stage_count = int(math.ceil(cantilever_length/segment))
    p1 = _pier_stages(cfg, geometry, prestress, analysis, "P1", geometry.left_side,
                      1.0, cantilever_length, stage_count)
    p2 = _pier_stages(cfg, geometry, prestress, analysis, "P2",
                      geometry.left_side+geometry.main, -1.0,
                      cantilever_length, stage_count)
    piers = [p1, p2]
    stages = []
    for index in range(len(p1["stages"])):
        rows = [pier["stages"][index] for pier in piers]
        selected = max(rows, key=lambda row: max(abs(row["top_stress_mpa"]),
                                                   abs(row["bottom_stress_mpa"])))
        row = dict(selected)
        row["activated_tendons"] = max(item["activated_tendons"] for item in rows)
        row["governing_pier_id"] = selected["pier_id"]
        row["pier_results"] = {
            item["pier_id"]: {
                "top_stress_mpa": item["top_stress_mpa"],
                "bottom_stress_mpa": item["bottom_stress_mpa"],
                "net_root_moment_knm": item["net_root_moment_knm"],
                "activated_tendons": item["activated_tendons"],
            } for item in rows
        }
        stages.append(row)
    governing = max(stages, key=lambda row: max(abs(row["top_stress_mpa"]),
                                                  abs(row["bottom_stress_mpa"])))
    return {
        "method": "双主墩对称悬臂根部截面施工阶段法",
        "construction_method": cfg["construction_method"],
        "segment_length_m": segment, "cantilever_length_m": cantilever_length,
        "segment_stage_count": stage_count,
        "form_traveler_load_kn": cfg["form_traveler_load"],
        "closure_age_days": cfg["closure_age_days"],
        "piers": piers, "stages": stages,
        "governing_pier_id": governing["governing_pier_id"],
        "governing_stage": governing["stage_id"],
        "governing_stage_name": governing["name"],
        "max_abs_stage_stress_mpa": float(max(abs(governing["top_stress_mpa"]),
                                                 abs(governing["bottom_stress_mpa"]))),
        "limitations": [
            "P1与P2分别计算并逐阶段选取控制主墩，未建立逐节段空间有限元。",
            "挂篮采用可编辑的等效竖向集中荷载；临时固结、合龙顶推及温度作用未计。",
            "钢束张拉进度按根部截面需求生成整束数量，尚未替代实际分束与施工张拉批次设计。",
        ],
    }
