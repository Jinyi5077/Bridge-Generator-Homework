"""Course-design global-section verification for BridgeGenerator V0.10.

The checks in this module are deliberately limited to the longitudinal plane
beam model.  Every reported PASS/FAIL therefore belongs to a named check and
does not imply complete bridge-code compliance.
"""
import math
import numpy as np


def _bar_area(diameter_mm):
    return math.pi*diameter_mm**2/4.0


def _even_ceil(value):
    return max(2, int(math.ceil(value/2.0))*2)


def _capacity_one(geometry, x, section, top_compression, steel_area_mm2,
                  steel_cover_m, tendon_depth_m, tendon_area_mm2,
                  fcd, fsd, fpd, xi_b):
    top_y, bottom_y = section["top_y"], section["bottom_y"]
    tension_y = bottom_y-steel_cover_m if top_compression else top_y+steel_cover_m
    tendon_on_tension_side = (tendon_depth_m > section["y"] if top_compression
                              else tendon_depth_m < section["y"])
    tp = fpd*tendon_area_mm2/1000.0 if tendon_on_tension_side else 0.0
    ts = fsd*steel_area_mm2/1000.0
    target = tp+ts
    if target <= 0:
        return dict(capacity_knm=0.0, depth_m=0.0, depth_ratio=0.0,
                    depth_limit_ok=True, tendon_counted=False)
    height = bottom_y-top_y
    lo, hi = 1e-7, height
    full_area, _ = geometry.compression_block(x, hi, top=top_compression)
    if fcd*full_area*1000.0 < target:
        return dict(capacity_knm=0.0, depth_m=height, depth_ratio=1.0,
                    depth_limit_ok=False, tendon_counted=tendon_on_tension_side)
    for _ in range(40):
        mid = (lo+hi)/2.0
        area, _ = geometry.compression_block(x, mid, top=top_compression)
        if fcd*area*1000.0 < target:
            lo = mid
        else:
            hi = mid
    depth = hi
    _, yc = geometry.compression_block(x, depth, top=top_compression)
    capacity = ts*abs(tension_y-yc)+tp*abs(tendon_depth_m-yc)
    if target > 0:
        force_y = (ts*tension_y+tp*tendon_depth_m)/target
    else:
        force_y = tension_y
    compression_edge = top_y if top_compression else bottom_y
    h0 = abs(force_y-compression_edge)
    depth_ratio = depth/max(h0, 1e-9)
    return dict(capacity_knm=float(capacity), depth_m=float(depth),
                depth_ratio=float(depth_ratio), depth_limit_ok=depth_ratio <= xi_b+1e-9,
                tendon_counted=tendon_on_tension_side)


def _flexural_arrays(cfg, geometry, analysis, material, reinforcement, bar_count, positive):
    x = np.asarray(analysis["x"])
    sections = geometry.section(x)
    # The profile ordinate already uses the section centreline datum. Adding
    # top_y again shifts all tendons when crossfall is nonzero.
    tendon_depth = np.asarray(analysis["tendon_depth_from_top"])
    area = bar_count*_bar_area(cfg["longitudinal_bar_diameter_mm"])
    capacities, depths, ratios, limits = [], [], [], []
    xi_b = 0.38 if cfg["concrete"] in {"C40", "C45", "C50", "C55", "C60"} else 0.36
    for i, station in enumerate(x):
        section = {key: float(value[i]) for key, value in sections.items()}
        result = _capacity_one(
            geometry, float(station), section, top_compression=positive,
            steel_area_mm2=area, steel_cover_m=max(0.08, cfg["prestress_cover"]*0.65),
            tendon_depth_m=float(tendon_depth[i]),
            tendon_area_mm2=float(reinforcement["prestress_area_profile_mm2"][i]),
            fcd=material["fcd_mpa"], fsd=reinforcement["fsd_mpa"],
            fpd=reinforcement["fpd_mpa"], xi_b=xi_b)
        capacities.append(result["capacity_knm"])
        depths.append(result["depth_m"])
        ratios.append(result["depth_ratio"])
        limits.append(result["depth_limit_ok"])
    return (np.asarray(capacities), np.asarray(depths), np.asarray(ratios),
            np.asarray(limits, dtype=bool))


def _design_longitudinal_rebar(cfg, geometry, analysis, material, reinforcement):
    gross_max_mm2 = float(np.max(np.asarray(analysis["area"])))*1e6
    single = _bar_area(cfg["longitudinal_bar_diameter_mm"])
    start = _even_ceil(cfg["longitudinal_rebar_ratio_per_face"]*gross_max_mm2/single)
    demand_positive = np.maximum(np.asarray(analysis["M_uls_max"]), 0.0)
    demand_negative = np.maximum(-np.asarray(analysis["M_uls_min"]), 0.0)

    def choose(positive, demand):
        count = start
        best = None
        while count <= 600:
            capacity, depth, ratio, limits = _flexural_arrays(
                cfg, geometry, analysis, material, reinforcement, count, positive)
            utilization = np.divide(demand, capacity, out=np.where(demand > 1e-6,1e12,0.0),
                                    where=capacity > 1e-9)
            active = demand > 1e-6
            maximum = float(np.max(utilization[active])) if np.any(active) else 0.0
            limit_ok = bool(np.all(limits[active])) if np.any(active) else True
            best = (count, capacity, depth, ratio, limits, utilization, maximum, limit_ok)
            if maximum <= 1.0 and limit_ok:
                break
            # Increasing tensile steel cannot repair an already overdeep block.
            if not limit_ok:
                break
            count += 2
        return best

    bottom = choose(True, demand_positive)
    top = choose(False, demand_negative)
    return dict(
        top_bar_count=top[0], bottom_bar_count=bottom[0],
        bar_diameter_mm=cfg["longitudinal_bar_diameter_mm"],
        top_area_mm2=top[0]*single, bottom_area_mm2=bottom[0]*single,
        input_ratio_per_face=cfg["longitudinal_rebar_ratio_per_face"],
        design_rule="先按输入的单面毛截面配筋率取偶数根，再逐两根增加至全桥正截面承载力满足且受压区高度不超限",
        top=top, bottom=bottom)


def _shear_check(cfg, geometry, analysis, material, reinforcement, prestress):
    x = np.asarray(analysis["x"])
    sec = geometry.section(x)
    b = 2.0*sec["tw"]*1000.0
    h0 = (sec["bottom_y"]-sec["top_y"]-max(0.10, cfg["prestress_cover"]*0.65))*1000.0
    asv = 2*cfg["stirrup_legs_per_web"]*_bar_area(cfg["stirrup_diameter_mm"])
    rho_long = 100.0*(reinforcement["top_area_mm2"]+reinforcement["bottom_area_mm2"]+
                      reinforcement["prestress_area_profile_mm2"])/(b*h0)
    rho_long = np.minimum(rho_long, 2.5)
    alpha1, alpha2, alpha3 = 0.9, 1.0, 1.1
    profile_x = np.asarray(prestress['profile']['x'])
    depth = np.asarray(prestress['profile']['depth_from_top'])
    slope = np.arctan(np.gradient(depth, profile_x))
    theta = np.interp(x, profile_x, slope)
    v_pb = (0.75e-3*reinforcement["fpd_mpa"]*reinforcement["prestress_area_profile_mm2"]*
            np.sin(theta))
    demand = np.asarray(analysis["V_uls"])
    candidates = sorted(set([float(cfg["stirrup_spacing_mm"]), 250.0, 200.0, 180.0,
                             150.0, 125.0, 100.0, 80.0]), reverse=True)
    candidates = [value for value in candidates if value <= cfg["stirrup_spacing_mm"]+1e-9]
    selected_spacing = candidates[-1]
    for spacing in candidates:
        rho_sv = asv/(spacing*b)
        v_cs = (0.45e-3*alpha1*alpha2*alpha3*b*h0*
                np.sqrt((2.0+0.6*rho_long)*math.sqrt(material["fcu_k_mpa"])*
                        (rho_sv*reinforcement["fsd_mpa"])))
        capacity = v_cs
        effective_demand = np.maximum(abs(np.asarray(analysis['V_uls_min'])-v_pb),
                                      abs(np.asarray(analysis['V_uls_max'])-v_pb))
        utilization = effective_demand/np.maximum(v_cs, 1e-9)
        selected_spacing = spacing
        if np.max(utilization) <= 1.0:
            break
    max_section_limit = 0.51e-3*np.sqrt(material["fcu_k_mpa"])*b*h0
    web_utilization = demand/np.maximum(max_section_limit, 1e-9)
    j = int(np.argmax(utilization))
    jw = int(np.argmax(web_utilization))
    return dict(
        status="PASS" if np.max(utilization) <= 1.0 and np.max(web_utilization) <= 1.0 else "FAIL",
        max_utilization=float(np.max(utilization)), critical_x_m=float(x[j]),
        demand_kn=float(effective_demand[j]), capacity_kn=float(capacity[j]),
        web_dimension_status="PASS" if np.max(web_utilization) <= 1.0 else "FAIL",
        web_dimension_max_utilization=float(np.max(web_utilization)),
        web_dimension_critical_x_m=float(x[jw]),
        stirrup=dict(diameter_mm=cfg["stirrup_diameter_mm"],
                     spacing_mm=selected_spacing,
                     input_max_spacing_mm=cfg["stirrup_spacing_mm"],
                     legs_per_web=cfg["stirrup_legs_per_web"],
                     total_legs=2*cfg["stirrup_legs_per_web"],
                     area_per_section_mm2=asv),
        coefficients=dict(alpha1=alpha1, alpha2=alpha2, alpha3=alpha3),
        tendon_direction_checked=True,
        arrays=dict(capacity_kn=capacity, utilization=utilization,
                    web_dimension_utilization=web_utilization))


def _service_checks(cfg, geometry, analysis, material, prestress, traffic, reinforcement):
    x = np.asarray(analysis["x"])
    top_freq = [np.asarray(analysis["stress_top_frequent_min"]),
                np.asarray(analysis["stress_top_frequent_max"])]
    bottom_freq = [np.asarray(analysis["stress_bottom_frequent_min"]),
                   np.asarray(analysis["stress_bottom_frequent_max"])]
    maximum_edge_tension = max(0.0, max(float(np.max(-v)) for v in top_freq+bottom_freq))
    edge_limit = 0.0 if cfg["prestress_class"] == "full" else 0.5*material["ftk_mpa"]
    edge_status = "PASS" if maximum_edge_tension <= edge_limit+1e-9 else "FAIL"

    sec = geometry.section(x)
    q_values, widths = [], []
    for station in x:
        props = geometry.shear_properties(float(station))
        q_values.append(props["Q"]); widths.append(props["b"])
    q_values, widths = np.asarray(q_values), np.asarray(widths)
    shear = np.maximum(abs(np.asarray(analysis["V_frequent_min"])),
                       abs(np.asarray(analysis["V_frequent_max"])))
    tau = shear*q_values/(sec["I"]*widths)/1000.0
    sigma_centroid = np.asarray(analysis["prestress_force_effective"])/sec["A"]/1000.0
    principal_tension = np.sqrt((sigma_centroid/2.0)**2+tau**2)-sigma_centroid/2.0
    principal_limit = (0.4 if cfg["prestress_class"] == "full" else 0.5)*material["ftk_mpa"]
    jp = int(np.argmax(principal_tension))

    standard_stresses = [np.asarray(analysis[key]) for key in [
        "stress_top_standard_min", "stress_top_standard_max",
        "stress_bottom_standard_min", "stress_bottom_standard_max"]]
    max_compression = max(float(np.max(v)) for v in standard_stresses)
    compression_limit = 0.5*material["fck_mpa"]

    # JTG 3362 6.5.2/6.5.3: uncracked transformed B0=.95 Ec I0;
    # frequent vehicle effect without impact, then long-term growth factor.
    from .fem import Beam
    nodes = np.unique(x); mids=(nodes[:-1]+nodes[1:])/2
    ms=geometry.section(mids); ec=material['E_mpa']
    yp=np.interp(mids,x,analysis['tendon_depth_from_top'])
    ap=np.interp(mids,x,analysis['prestress_area_active_mm2'])/1e6
    ast=reinforcement['top_area_mm2']/1e6;asb=reinforcement['bottom_area_mm2']/1e6
    cover=max(.08,cfg['prestress_cover']*.65)
    yt=ms['top_y']+cover;yb=ms['bottom_y']-cover
    ns=200000/ec-1;np_=cfg['strand_E_mpa']/ec-1
    area0=ms['A']+ns*(ast+asb)+np_*ap
    y0=(ms['A']*ms['y']+ns*(ast*yt+asb*yb)+np_*ap*yp)/area0
    i0=ms['I']+ms['A']*(ms['y']-y0)**2+ns*(ast*(yt-y0)**2+asb*(yb-y0)**2)+np_*ap*(yp-y0)**2
    service_beam=Beam(nodes,.95*ec*1000*i0,geometry.supports)
    influence=service_beam.influences();nu=influence['u'][0::2]
    wi=np.stack((nu[:-1],nu[1:]),axis=1).reshape(len(x),-1)
    low=(traffic['qk']*(np.minimum(wi,0)@influence['weights'])+traffic['pk']*np.minimum(np.min(wi,axis=1),0))*traffic['effective_lanes']
    high=(traffic['qk']*(np.maximum(wi,0)@influence['weights'])+traffic['pk']*np.maximum(np.max(wi,axis=1),0))*traffic['effective_lanes']
    strength=float(cfg['concrete'][1:])
    long_factor=1.45-(strength-40.0)*(.10/40.0)
    live_low=low*.7*long_factor;live_high=high*.7*long_factor
    span_rows = []
    for number, (start, end) in enumerate(zip(geometry.supports[:-1], geometry.supports[1:]), 1):
        mask = (x >= start-1e-8) & (x <= end+1e-8)
        maximum = float(max(np.max(abs(live_low[mask])), np.max(abs(live_high[mask]))))
        limit = float((end-start)/600.0)
        span_rows.append(dict(span=number, start_m=float(start), end_m=float(end),
                              maximum_live_impact_mm=maximum*1000.0,
                              maximum_frequent_long_term_mm=maximum*1000.0,
                              limit_mm=limit*1000.0, utilization=maximum/limit,
                              status="PASS" if maximum <= limit+1e-12 else "FAIL"))

    # Long-term camber is a separate EcI0 calculation (6.5.4).
    camber_beam=Beam(nodes,ec*1000*i0,geometry.supports)
    px=np.asarray(prestress['profile']['x']);mp=-np.asarray(prestress['profile']['force_effective'])*np.asarray(prestress['profile']['eccentricity'])
    pu=camber_beam.initial_moment(lambda t:np.interp(t,px,mp))['u'][0::2]
    pdef=np.column_stack((pu[:-1],pu[1:])).ravel()
    q1=ms['A']*cfg['concrete_weight'];q2=(geometry.width-2*cfg['barrier_width'])*cfg['pavement_thickness']*cfg['pavement_weight']+cfg['barrier_line_load']+cfg['other_dead_load']
    du=service_beam.distributed(-(q1+q2))['u'][0::2]
    dservice=np.column_stack((du[:-1],du[1:])).ravel()
    long_low=long_factor*dservice+live_low+2*pdef
    long_high=long_factor*dservice+live_high+2*pdef
    camber = []
    for number, (start, end) in enumerate(zip(geometry.supports[:-1], geometry.supports[1:]), 1):
        mask = (x >= start-1e-8) & (x <= end+1e-8)
        dead_long = long_factor*dservice[mask]
        prestress_long = 2.0*pdef[mask]
        net = dead_long+prestress_long
        camber.append(dict(span=number, recommended_upward_camber_mm=max(0.0, -float(np.min(net))*1000.0),
                           dead_long_term_downward_mm=max(0.0, -float(np.min(dead_long))*1000.0),
                           prestress_long_term_upward_mm=max(0.0, float(np.max(prestress_long))*1000.0)))

    analysis_update = dict(
        deflection_live_impact_min=np.asarray(analysis['deflection_live_min'])*(1+traffic['impact']),
        deflection_live_impact_max=np.asarray(analysis['deflection_live_max'])*(1+traffic['impact']),
        deflection_service_live_min=live_low,deflection_service_live_max=live_high,
        deflection_standard_total_min=np.asarray(analysis["deflection_standard_min"])+np.asarray(analysis['deflection_prestress']),
        deflection_standard_total_max=np.asarray(analysis["deflection_standard_max"])+np.asarray(analysis['deflection_prestress']),
        deflection_frequent_total_min=np.asarray(analysis["deflection_frequent_min"])+np.asarray(analysis['deflection_prestress']),
        deflection_frequent_total_max=np.asarray(analysis["deflection_frequent_max"])+np.asarray(analysis['deflection_prestress']),
        deflection_quasi_total_min=np.asarray(analysis["deflection_quasi_min"])+np.asarray(analysis['deflection_prestress']),
        deflection_quasi_total_max=np.asarray(analysis["deflection_quasi_max"])+np.asarray(analysis['deflection_prestress']),
        deflection_long_term_min=long_low, deflection_long_term_max=long_high,
        principal_tensile_stress_frequent=principal_tension,
        web_shear_stress_frequent=tau)
    return dict(
        crack_resistance=dict(
            status="PASS" if edge_status == "PASS" and np.max(principal_tension) <= principal_limit else "FAIL",
            edge_status=edge_status, maximum_edge_tension_mpa=maximum_edge_tension,
            edge_limit_mpa=edge_limit, principal_status="PASS" if np.max(principal_tension) <= principal_limit else "FAIL",
            maximum_principal_tension_mpa=float(np.max(principal_tension)),
            principal_limit_mpa=principal_limit, principal_critical_x_m=float(x[jp]),
            class_name=cfg["prestress_class"], cast_in_place=True),
        concrete_stress=dict(status="PASS" if max_compression <= compression_limit else "FAIL",
                             maximum_compression_mpa=max_compression,
                             compression_limit_mpa=compression_limit),
        deflection=dict(status="PASS" if all(v["status"] == "PASS" for v in span_rows) else "FAIL",
                        rule_version='frequent_no_impact_eta_theta_B0',
                        stiffness_basis='0.95 Ec I0; equivalent accepted rebar/strand; steel local inertia neglected',
                        span_checks=span_rows, long_term_factor=long_factor,
                        prestress_camber_long_term_factor=2.0,
                        recommended_camber=camber,
                        maximum_total_long_term_mm=float(max(np.max(abs(long_low)), np.max(abs(long_high))))*1000.0),
        analysis_update=analysis_update)


def verify_structure(cfg, geometry, analysis, profile, prestress, construction, traffic):
    material = profile["materials"][cfg["concrete"]]
    rebar = profile["reinforcement"][cfg["rebar_grade"]]
    strand = profile["reinforcement"]["strand_1860"]
    reinforcement = dict(
        grade=cfg["rebar_grade"], fsd_mpa=rebar["fsd_mpa"], fsk_mpa=rebar["fsk_mpa"],
        fpd_mpa=strand["fpd_mpa"], prestress_area_mm2=prestress["total_area_mm2"],
        prestress_area_profile_mm2=np.asarray(analysis["prestress_area_active_mm2"]))
    designed = _design_longitudinal_rebar(cfg, geometry, analysis, material, reinforcement)
    reinforcement.update({key: designed[key] for key in [
        "top_bar_count", "bottom_bar_count", "bar_diameter_mm", "top_area_mm2",
        "bottom_area_mm2", "input_ratio_per_face", "design_rule"]})
    reinforcement["prestress_area_profile_min_mm2"] = float(
        np.min(reinforcement["prestress_area_profile_mm2"]))

    top = designed["top"]; bottom = designed["bottom"]
    x = np.asarray(analysis["x"])
    positive_demand = np.maximum(np.asarray(analysis["M_uls_max"]), 0.0)
    negative_demand = np.maximum(-np.asarray(analysis["M_uls_min"]), 0.0)
    pos_j, neg_j = int(np.argmax(bottom[5])), int(np.argmax(top[5]))
    pos_depth_j = int(np.argmax(np.where(positive_demand > 1e-6, bottom[3], 0.0)))
    neg_depth_j = int(np.argmax(np.where(negative_demand > 1e-6, top[3], 0.0)))
    flexure = dict(
        status="PASS" if bottom[6] <= 1.0 and top[6] <= 1.0 and bottom[7] and top[7] else "FAIL",
        positive=dict(status="PASS" if bottom[6] <= 1.0 and bottom[7] else "FAIL",
                      max_utilization=bottom[6], critical_x_m=float(x[pos_j]),
                      demand_knm=float(positive_demand[pos_j]), capacity_knm=float(bottom[1][pos_j]),
                      compression_depth_ratio=float(bottom[3][pos_j]), depth_limit=0.38,
                      maximum_compression_depth_ratio=float(bottom[3][pos_depth_j]),
                      depth_critical_x_m=float(x[pos_depth_j])),
        negative=dict(status="PASS" if top[6] <= 1.0 and top[7] else "FAIL",
                      max_utilization=top[6], critical_x_m=float(x[neg_j]),
                      demand_knm=float(negative_demand[neg_j]), capacity_knm=float(top[1][neg_j]),
                      compression_depth_ratio=float(top[3][neg_j]), depth_limit=0.38,
                      maximum_compression_depth_ratio=float(top[3][neg_depth_j]),
                      depth_critical_x_m=float(x[neg_depth_j])))
    shear = _shear_check(cfg, geometry, analysis, material, reinforcement, prestress)
    service = _service_checks(cfg, geometry, analysis, material, prestress, traffic, reinforcement)
    stage_max_compression = max(max(row["top_stress_mpa"], row["bottom_stress_mpa"])
                                for row in construction["stages"])
    temporary = dict(status="PASS" if stage_max_compression <= 0.8*material["fck_mpa"] else "FAIL",
                     maximum_compression_mpa=float(stage_max_compression),
                     compression_limit_mpa=0.8*material["fck_mpa"])
    analysis_update = dict(
        flexural_capacity_positive=bottom[1], flexural_capacity_negative=top[1],
        flexural_utilization_positive=bottom[5], flexural_utilization_negative=top[5],
        shear_capacity=shear["arrays"]["capacity_kn"],
        shear_utilization=shear["arrays"]["utilization"],
        web_dimension_utilization=shear["arrays"]["web_dimension_utilization"],
        **service.pop("analysis_update"))
    shear.pop("arrays")
    checks = dict(flexure=flexure, shear=shear, crack_resistance=service["crack_resistance"],
                  concrete_stress=service["concrete_stress"], deflection=service["deflection"],
                  temporary_concrete_stress=temporary)
    passed = sum(value["status"] == "PASS" for value in checks.values())
    return dict(
        scope="纵向平面梁全桥正截面抗弯、斜截面抗剪、正截面与腹板抗裂、使用阶段压应力、活载挠度和施工阶段压应力",
        material=material, reinforcement=reinforcement, checks=checks,
        summary=dict(passed=passed, total=len(checks), all_named_checks_pass=passed == len(checks)),
        analysis_update=analysis_update,
        out_of_course_scope=[
            "横向桥面板、腹板局部、横隔板、齿块和锚下局部承载力。",
            "空间扭转、剪力滞、畸变、支座沉降、温度、风、地震及偶然作用。",
            "普通钢筋分区截断、锚固、接头和施工图级构造详图。",
            "逐节段空间施工控制分析。",
        ])

