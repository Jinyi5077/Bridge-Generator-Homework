"""Preliminary longitudinal prestress design and effect calculation.

The model uses one equivalent tendon resultant for each independent deck.  It
is intended for scheme design: tendon quantity, geometry, losses, primary and
secondary effects are calculated, while anchorage-zone, local tendon grouping
remain outside this version. Named section checks are evaluated separately by
the verification module.
"""
import math
import numpy as np


def _smooth_values(values, passes=4, symmetric=True):
    values = np.asarray(values, dtype=float)
    kernel = np.array([0.2, 0.6, 0.2])
    result = values.copy()
    for _ in range(passes):
        result = np.convolve(np.pad(result, (1, 1), mode="edge"), kernel, mode="valid")
    return (result + result[::-1]) / 2.0 if symmetric else result


def _station_displacements(displacements):
    nodes = np.asarray(displacements)[0::2]
    return np.column_stack((nodes[:-1], nodes[1:])).ravel()


def design_prestress(cfg, geometry, beam, analysis, material):
    """Return a traceable equivalent-tendon design for one carriageway."""
    # Keep the equivalent design's physical spacing independent of FE mesh.
    # Refining the analysis must not shrink smoothing/tendon termination zones.
    design_nodes=[]
    for start,end in zip(geometry.supports[:-1],geometry.supports[1:]):
        ne=max(8,int(math.ceil((end-start)/2.0)))
        ne=int(math.ceil(ne/4))*4
        design_nodes.extend(np.linspace(start,end,ne+1))
    x=np.unique(design_nodes)
    sec = geometry.section(x)
    stations = np.asarray(analysis["x"])

    # Collapse the duplicated element-end station results to nodal envelopes.
    frequent_min = np.empty_like(x)
    frequent_max = np.empty_like(x)
    nodes=np.unique(stations)
    grouped=[np.flatnonzero(np.isclose(stations,node,atol=1e-8)) for node in nodes]
    nodal_min=np.array([np.min(np.asarray(analysis['M_frequent_min'])[ids]) for ids in grouped])
    nodal_max=np.array([np.max(np.asarray(analysis['M_frequent_max'])[ids]) for ids in grouped])
    for i, node in enumerate(x):
        frequent_min[i] = np.interp(node,nodes,nodal_min)
        frequent_max[i] = np.interp(node,nodes,nodal_max)
    control_moment = np.where(np.abs(frequent_min) >= np.abs(frequent_max),
                              frequent_min, frequent_max)
    # Hinged end moments are physically zero. Round-off must not select
    # opposite anchorage profiles when the solver/mesh changes.
    control_moment[[0,-1]]=0.0

    cover = cfg["prestress_cover"]
    upper_limit = np.maximum(sec["y"] - cover, 0.05)
    lower_limit = np.maximum(sec["h"] - sec["y"] - cover, 0.05)
    # Use the available eccentricity in both positive- and negative-moment
    # zones.  Scaling eccentricity only by the relative moment
    # unnecessarily increased steel area in lower-demand spans and could create
    # an over-reinforced ultimate section.
    raw_e = np.where(control_moment >= 0,
                     0.98*lower_limit,
                     -0.98*upper_limit)
    eccentricity = _smooth_values(raw_e, passes=2, symmetric=geometry.is_symmetric)
    eccentricity = np.minimum(np.maximum(eccentricity, -upper_limit), lower_limit)
    end_indexes = np.array([0, len(x)-1])
    end_kern_upper = sec["Wt"][end_indexes]/sec["A"][end_indexes]
    end_kern_lower = -sec["Wb"][end_indexes]/sec["A"][end_indexes]
    supplied_end_eccentricity = cfg.get("prestress_end_eccentricity_m")
    original_end_eccentricity = eccentricity[end_indexes].copy()
    if supplied_end_eccentricity is None:
        # A0/A3 have negligible externally applied bending moment.  Selecting
        # maximum lower eccentricity there can introduce top-fibre tension
        # from prestress alone even when effective force demand is satisfied.
        # The elastic no-tension kern follows P/A-P*e/Wt >=0 and
        # P/A+P*e/Wb >=0.  It is a starting anchorage position, not a changed
        # resistance limit.  Explicit user end eccentricities remain untouched.
        eccentricity[end_indexes] = np.clip(eccentricity[end_indexes],
            np.maximum(end_kern_lower,-upper_limit[end_indexes]),
            np.minimum(end_kern_upper,lower_limit[end_indexes]))
    else:
        eccentricity[end_indexes] = float(supplied_end_eccentricity)
    end_anchor_rule = dict(
        mode="auto_kern" if supplied_end_eccentricity is None else "user_explicit",
        formula="-W_b/A <= e_end <= W_t/A",
        stress_basis="sigma_top=P/A-P*e/W_t; sigma_bottom=P/A+P*e/W_b",
        source="毛截面线弹性偏心压力应力公式；桥台端截面核心初选，不改变规范应力限值",
        x_m=x[end_indexes], original_eccentricity_m=original_end_eccentricity,
        eccentricity_m=eccentricity[end_indexes],
        kern_lower_m=end_kern_lower, kern_upper_m=end_kern_upper,
        note="显式端部偏心保留；正常使用与施工应力仍按实际完整效应验算",
    )

    # Required effective force for the selected prestress crack-resistance
    # class under the frequent combination (JTG 3362—2018, 6.3.1).
    allowable_tension = 0.0 if cfg["prestress_class"] == "full" else 0.5*material["ftk_mpa"]
    denom_positive = sec["Wb"]/sec["A"] + eccentricity
    denom_negative = sec["Wt"]/sec["A"] - eccentricity
    required = np.where(control_moment >= 0,
                        np.maximum(control_moment-allowable_tension*1000.0*sec["Wb"], 0)/np.maximum(denom_positive, 0.05),
                        np.maximum(-control_moment-allowable_tension*1000.0*sec["Wt"], 0)/np.maximum(denom_negative, 0.05))
    # Web principal-tension criterion also establishes a minimum centroidal
    # precompression at each node.
    v_frequent = np.empty_like(x)
    nodal_v=np.array([max(np.max(abs(np.asarray(analysis['V_frequent_min'])[ids])),
                         np.max(abs(np.asarray(analysis['V_frequent_max'])[ids]))) for ids in grouped])
    for i, node in enumerate(x):
        v_frequent[i] = np.interp(node,nodes,nodal_v)
    shear_q = np.asarray([geometry.shear_properties(float(node))["Q"] for node in x])
    shear_b = np.asarray([geometry.shear_properties(float(node))["b"] for node in x])
    tau = v_frequent*shear_q/(sec["I"]*shear_b)/1000.0
    principal_limit = (0.4 if cfg["prestress_class"] == "full" else 0.5)*material["ftk_mpa"]
    required_centroid_stress = np.maximum((tau*tau-principal_limit**2)/principal_limit, 0.0)
    required = np.maximum(required, required_centroid_stress*1000.0*sec["A"])
    required *= 1.05

    sigma_jack = cfg["strand_fpk_mpa"]*cfg["jacking_stress_ratio"]
    slope = np.arctan(np.gradient(sec['y']+eccentricity, x))
    mu, wobble = cfg["friction_mu"], cfg["wobble_k_per_m"]
    # Equivalent tendon groups are tensioned within side-span and main-span
    # regions.  Calculating one cumulative angular change over the entire bridge
    # falsely treats separately anchored positive- and negative-moment groups as
    # one cable and greatly overstates friction loss.
    anchors = np.unique(np.r_[0.0, geometry.left_side/2.0, geometry.left_side,
                              geometry.left_side+geometry.main/2.0,
                              geometry.left_side+geometry.main,
                              geometry.length-geometry.right_side/2.0, geometry.length])
    sigma_friction = np.zeros_like(x)
    region_lengths = []
    for start, end in zip(anchors[:-1], anchors[1:]):
        ids = np.where((x >= start-1e-9) & (x <= end+1e-9))[0]
        if len(ids) < 2:
            continue
        local_x = x[ids]
        local_slope = slope[ids]
        dtheta = np.abs(np.diff(local_slope))
        theta_left = np.r_[0.0, np.cumsum(dtheta)]
        theta_right = np.r_[np.cumsum(dtheta[::-1])[::-1], 0.0]
        sigma_left = sigma_jack*np.exp(-(mu*theta_left+wobble*(local_x-start)))
        sigma_right = sigma_jack*np.exp(-(mu*theta_right+wobble*(end-local_x)))
        sigma_friction[ids] = np.maximum(sigma_friction[ids], np.maximum(sigma_left, sigma_right))
        region_lengths.append(end-start)

    anchorage_length = max(max(region_lengths), 1.0)
    anchorage_loss = cfg["strand_E_mpa"]*(cfg["anchorage_slip_mm"]/1000.0)/anchorage_length
    sigma_anchor = np.maximum(sigma_friction-anchorage_loss, 0.25*sigma_jack)
    sigma_immediate = sigma_anchor*(1.0-cfg["elastic_shortening_ratio"])
    long_term_loss = (cfg["strand_E_mpa"]*cfg["shrinkage_strain"]
                      + sigma_jack*(cfg["creep_loss_ratio"]+cfg["relaxation_loss_ratio"]))
    sigma_effective = np.maximum(sigma_immediate-long_term_loss, 0.20*sigma_jack)

    bundle = cfg["strands_per_tendon"]
    bundle_area = bundle*cfg["strand_area_mm2"]
    per_tendon_effective = sigma_effective*bundle_area/1000.0
    active_tendons = np.ceil(required/np.maximum(per_tendon_effective, 1e-9)).astype(int)
    active_tendons = np.maximum(active_tendons, 1)
    # Envelope adjacent stations so tendon terminations do not oscillate at
    # individual finite elements; restore exact bridge symmetry afterwards.
    padded = np.pad(active_tendons, (2, 2), mode="edge")
    active_tendons = np.maximum.reduce([padded[i:i+len(active_tendons)] for i in range(5)])
    if geometry.is_symmetric:
        active_tendons = np.maximum(active_tendons, active_tendons[::-1])
    tendon_count = int(np.max(active_tendons))
    strand_count = tendon_count*bundle
    total_area = strand_count*cfg["strand_area_mm2"]
    active_area = active_tendons*bundle_area
    p_jack = sigma_jack*active_area/1000.0
    p_immediate = sigma_immediate*active_area/1000.0
    p_effective = sigma_effective*active_area/1000.0

    primary_immediate = -p_immediate*eccentricity
    primary_effective = -p_effective*eccentricity
    immediate_response = beam.initial_moment(
        lambda q: np.interp(q, x, primary_immediate))
    effective_response = beam.initial_moment(
        lambda q: np.interp(q, x, primary_effective))

    e_s = np.interp(stations, x, eccentricity)
    area_s = np.interp(stations, x, active_area)
    tendon_count_s = np.interp(stations, x, active_tendons)
    p_i_s = np.interp(stations, x, p_immediate)
    p_e_s = np.interp(stations, x, p_effective)
    h_s = np.asarray(analysis["height"])
    a_s = np.asarray(analysis["area"])
    wt_s = np.asarray(analysis["section_modulus_top"])
    wb_s = np.asarray(analysis["section_modulus_bottom"])
    y_s = np.interp(stations, x, sec["y"])
    secondary_i = np.asarray(immediate_response["secondary_M"])
    secondary_e = np.asarray(effective_response["secondary_M"])

    def stresses(force, moment_secondary, external_moment):
        top = (force/a_s-force*e_s/wt_s+(external_moment+moment_secondary)/wt_s)/1000.0
        bottom = (force/a_s+force*e_s/wb_s-(external_moment+moment_secondary)/wb_s)/1000.0
        return top, bottom

    top_transfer, bottom_transfer = stresses(
        p_i_s, secondary_i, np.asarray(analysis["M_dead1"]))
    top_std_min, bottom_std_min = stresses(
        p_e_s, secondary_e, np.asarray(analysis["M_standard_min"]))
    top_std_max, bottom_std_max = stresses(
        p_e_s, secondary_e, np.asarray(analysis["M_standard_max"]))
    top_freq_min, bottom_freq_min = stresses(
        p_e_s, secondary_e, np.asarray(analysis["M_frequent_min"]))
    top_freq_max, bottom_freq_max = stresses(
        p_e_s, secondary_e, np.asarray(analysis["M_frequent_max"]))
    top_quasi_min, bottom_quasi_min = stresses(
        p_e_s, secondary_e, np.asarray(analysis["M_quasi_min"]))
    top_quasi_max, bottom_quasi_max = stresses(
        p_e_s, secondary_e, np.asarray(analysis["M_quasi_max"]))

    friction_loss = sigma_jack-sigma_friction
    anchor_component = sigma_friction-sigma_anchor
    elastic_component = sigma_anchor-sigma_immediate
    shrink_component = np.full_like(x, cfg["strand_E_mpa"]*cfg["shrinkage_strain"])
    creep_component = np.full_like(x, sigma_jack*cfg["creep_loss_ratio"])
    relaxation_component = np.full_like(x, sigma_jack*cfg["relaxation_loss_ratio"])
    total_loss = sigma_jack-sigma_effective
    loss_summary = {
        "friction_mpa_mean": float(np.mean(friction_loss)),
        "anchorage_mpa_mean": float(np.mean(anchor_component)),
        "elastic_shortening_mpa_mean": float(np.mean(elastic_component)),
        "shrinkage_mpa": float(shrink_component[0]),
        "creep_mpa": float(creep_component[0]),
        "relaxation_mpa": float(relaxation_component[0]),
        "total_mpa_mean": float(np.mean(total_loss)),
        "total_ratio_mean": float(np.mean(total_loss/sigma_jack)),
        "effective_ratio_min": float(np.min(sigma_effective/sigma_jack)),
    }

    analysis_update = {
        "tendon_eccentricity": e_s,
        "tendon_depth_from_top": y_s+e_s,
        "prestress_force_immediate": p_i_s,
        "prestress_force_effective": p_e_s,
        "prestress_area_active_mm2": area_s,
        "active_tendon_count": tendon_count_s,
        "M_prestress_primary": np.interp(stations, x, primary_effective),
        "M_prestress_secondary": secondary_e,
        "M_prestress_total": np.asarray(effective_response["M"]),
        "deflection_prestress": _station_displacements(effective_response["u"]),
        "stress_top_transfer": top_transfer,
        "stress_bottom_transfer": bottom_transfer,
        "stress_top_standard_min": top_std_min,
        "stress_top_standard_max": top_std_max,
        "stress_bottom_standard_min": bottom_std_min,
        "stress_bottom_standard_max": bottom_std_max,
        "stress_top_frequent_min": top_freq_min,
        "stress_top_frequent_max": top_freq_max,
        "stress_bottom_frequent_min": bottom_freq_min,
        "stress_bottom_frequent_max": bottom_freq_max,
        "stress_top_quasi_min": top_quasi_min,
        "stress_top_quasi_max": top_quasi_max,
        "stress_bottom_quasi_min": bottom_quasi_min,
        "stress_bottom_quasi_max": bottom_quasi_max,
    }
    return {
        "model": "单幅等效纵向钢束合力模型",
        "angle_basis": "absolute_depth",
        "design_profile_step_m": 2.0,
        "design_basis": ("按频遇组合及"+cfg["prestress_class"]+
                         "类抗裂限值初估有效预应力，并取1.05方案裕量；"
                         + ("桥台端偏心按实际截面核心自动初选" if supplied_end_eccentricity is None
                            else "桥台端偏心按用户显式输入")),
        "end_anchor_rule": end_anchor_rule,
        "strand_diameter_mm": cfg["strand_diameter"],
        "strand_area_mm2": cfg["strand_area_mm2"],
        "strand_fpk_mpa": cfg["strand_fpk_mpa"],
        "strand_E_mpa": cfg["strand_E_mpa"],
        "jacking_stress_mpa": sigma_jack,
        "strands_per_tendon": bundle,
        "strand_count": strand_count,
        "tendon_count": tendon_count,
        "total_area_mm2": total_area,
        "jacking_force_kn": float(np.max(p_jack)),
        "required_effective_force_max_kn": float(np.max(required)),
        "effective_force_min_kn": float(np.min(p_effective)),
        "effective_force_max_kn": float(np.max(p_effective)),
        "minimum_force_margin_kn": float(np.min(p_effective-required)),
        "loss_summary": loss_summary,
        "profile": {
            "x": x, "eccentricity": eccentricity,
            "depth_from_top": sec["y"]+eccentricity,
            "upper_eccentricity_limit": upper_limit,
            "lower_eccentricity_limit": lower_limit,
            "control_moment": control_moment,
            "required_effective_force": required,
            "sigma_jack": np.full_like(x, sigma_jack),
            "sigma_after_friction": sigma_friction,
            "sigma_immediate": sigma_immediate,
            "sigma_effective": sigma_effective,
            "jacking_region_anchors": anchors,
            "force_jack": p_jack,
            "force_immediate": p_immediate,
            "force_effective": p_effective,
            "active_tendon_count": active_tendons,
            "active_area_mm2": active_area,
        },
        "stress_summary": {
            "transfer_top_min_mpa": float(np.min(top_transfer)),
            "transfer_bottom_min_mpa": float(np.min(bottom_transfer)),
            "standard_top_min_mpa": float(min(np.min(top_std_min), np.min(top_std_max))),
            "standard_top_max_mpa": float(max(np.max(top_std_min), np.max(top_std_max))),
            "standard_bottom_min_mpa": float(min(np.min(bottom_std_min), np.min(bottom_std_max))),
            "standard_bottom_max_mpa": float(max(np.max(bottom_std_min), np.max(bottom_std_max))),
        },
        "analysis_update": analysis_update,
        "limitations": [
            "钢束按截面需求形成对称的整束数量包络，尚未完成实际分束、锚固齿块、平弯竖弯及局部构造设计。",
            "收缩、徐变与松弛按可编辑简化损失参数计算，未进行逐龄期耦合分析。",
            "具名截面应力验算由验算模块判断；端部核心初选不代表实际锚固区局部验算完成。",
        ],
    }
