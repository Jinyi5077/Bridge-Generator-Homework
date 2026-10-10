"""Canonical units and field metadata for V0.10 calculation records."""


UNIT_SYSTEM = {
    "name": "SI-kN-m",
    "calculation": {
        "length": "m",
        "area": "m²",
        "section_inertia": "m⁴",
        "section_modulus": "m³",
        "force": "kN",
        "line_load": "kN/m",
        "moment": "kN·m",
        "elastic_modulus": "MPa",
        "mass_per_length": "kN·s²/m²",
        "frequency": "Hz",
        "displacement": "m",
    },
    "drawing": {"model_space_unit": "mm", "calculation_to_drawing": 1000.0},
    "sign_convention": {
        "vertical_displacement": "向上为正",
        "bending_moment": "下缘受拉的正弯矩为正",
        "shear": "按梁单元左、右端内力恢复并保留截面两侧值",
        "reaction": "向上为正",
    },
}


FIELD_UNITS = {
    "main_span": "m", "side_span_ratio": "1", "left_side_span": "m",
    "right_side_span": "m", "side_span_mode": "text", "layout": "类别", "lane_width": "m",
    "barrier_width": "m", "deck_gap": "m", "inner_margin": "m",
    "outer_margin": "m", "cantilever_width": "m",
    "height_reference_span": "m", "height_mid": "m", "height_pier": "m",
    "height_curve_exponent": "1", "cross_slope": "1",
    "top_thickness": "m", "tip_thickness": "m",
    "top_haunch_horizontal": "m", "top_haunch_vertical": "m",
    "bottom_mid": "m", "bottom_pier": "m",
    "bottom_chamfer_horizontal": "m", "bottom_chamfer_vertical": "m",
    "web_mid": "m", "web_pier": "m", "concrete_weight": "kN/m³",
    "pavement_thickness": "m", "pavement_weight": "kN/m³",
    "barrier_line_load": "kN/m", "other_dead_load": "kN/m",
    "mesh_length": "m", "importance_factor": "1", "pier_height": "m",
    "pile_length": "m", "lanes": "条", "cells": "个",
    "segment_length": "m", "form_traveler_load": "kN", "closure_age_days": "d",
    "strand_diameter": "mm", "strand_area_mm2": "mm²",
    "strand_fpk_mpa": "MPa", "strand_E_mpa": "MPa",
    "jacking_stress_ratio": "1", "strands_per_tendon": "根/束",
    "prestress_cover": "m", "friction_mu": "1", "wobble_k_per_m": "1/m",
    "anchorage_slip_mm": "mm", "elastic_shortening_ratio": "1",
    "shrinkage_strain": "1", "creep_loss_ratio": "1", "relaxation_loss_ratio": "1",
    "prestress_class": "类别", "environment_class": "类别", "rebar_grade": "牌号",
    "longitudinal_bar_diameter_mm": "mm", "longitudinal_rebar_ratio_per_face": "1",
    "stirrup_diameter_mm": "mm", "stirrup_spacing_mm": "mm",
    "stirrup_legs_per_web": "肢/腹板",
}


def field_unit(name):
    return FIELD_UNITS.get(name, "")


def bridge_description(config, geometry):
    """Describe the actual carriageways once for reports and presentations."""
    decks = int(geometry.get("deck_count", 1 if config.get("layout") == "single" else 2))
    lanes = int(geometry.get("lanes_per_deck", int(config.get("lanes", 4)) // decks))
    total_lanes = int(config.get("lanes", decks * lanes))
    count = {2: "二", 3: "三", 4: "四", 6: "六"}.get(total_lanes, str(total_lanes))
    per_deck = {2: "两", 3: "三"}.get(lanes, str(lanes))
    arrangement = (f"左右分离两幅，每幅{per_deck}车道、单箱单室" if decks == 2
                   else f"单幅{'双向' if total_lanes == 2 else ''}{per_deck}车道、单箱单室")
    return dict(deck_count=decks, lanes_per_deck=lanes, total_lanes=total_lanes,
                title=f"{count}车道{'分离式' if decks == 2 else ('单幅双向' if total_lanes == 2 else '单幅')}变截面连续箱梁",
                arrangement=arrangement,
                gap=float(config.get("deck_gap", 0)) if decks == 2 else 0.0)

