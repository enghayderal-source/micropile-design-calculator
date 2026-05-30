"""
Micropile axial design/check engine.

Preliminary ASD calculations based mainly on FHWA NHI-05-039 Chapter 5:
- Eq. 5-1: Allowable compression load for cased length
- Eq. 5-2: Allowable tension load for cased length
- Eq. 5-7: Allowable compression load for uncased length
- Eq. 5-8: Allowable tension load for uncased length
- Eq. 5-9 / 5-10: Grout-to-ground bond capacity and required bond length

Important: this is a preliminary tool for estimating and screening. It is not a sealed design.
Final design must be reviewed by the EOR/geotechnical engineer and must address buckling,
lateral load, bending, eccentricity, group effects, corrosion classification, connections,
load testing acceptance criteria, and applicable specifications.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from math import pi, sqrt
from typing import Dict, Any, Optional


@dataclass
class Bar:
    name: str
    area_in2: float
    od_in: float
    id_in: float
    fy_ksi: float
    source: str = ""


@dataclass
class Casing:
    name: str
    od_in: float
    wall_in: float
    fy_ksi: float
    source: str = ""


@dataclass
class MicropileInputs:
    pile_configuration: str
    required_compression_kips: float
    required_tension_kips: float
    bar: Bar
    casing: Optional[Casing]
    grout_fc_psi: float
    bond_diameter_in: float
    provided_bond_length_ft: float
    corrosion_allowance_in: float = 0.0
    use_user_allowable_bond: bool = False
    alpha_ultimate_comp_psi: float = 150.0
    alpha_ultimate_tension_psi: float = 75.0
    fs_bond_comp: float = 2.0
    fs_bond_tension: float = 2.0
    allowable_bond_comp_psi: float = 75.0
    allowable_bond_tension_psi: float = 25.0
    count_casing_in_tension: bool = False
    casing_extends_full_bond: bool = False
    proof_factor_comp: float = 1.0
    proof_factor_tension: float = 1.0
    min_socket_ft: float = 0.0
    round_socket_up_to_ft: float = 0.5


def area_circle(d_in: float) -> float:
    return pi * d_in**2 / 4.0 if d_in > 0 else 0.0


def casing_effective_section(casing: Optional[Casing], corrosion_allowance_in: float) -> Dict[str, float]:
    if casing is None or casing.od_in <= 0 or casing.wall_in <= 0:
        return {"od_eff_in": 0.0, "wall_eff_in": 0.0, "id_eff_in": 0.0, "area_in2": 0.0, "I_in4": 0.0, "S_in3": 0.0, "r_in": 0.0}

    wall_eff = max(casing.wall_in - corrosion_allowance_in, 0.0)
    id_eff = max(casing.od_in - 2.0 * wall_eff, 0.0)
    area = pi / 4.0 * max(casing.od_in**2 - id_eff**2, 0.0)
    I = pi / 64.0 * max(casing.od_in**4 - id_eff**4, 0.0)
    S = I / (casing.od_in / 2.0) if casing.od_in > 0 else 0.0
    r = sqrt(I / area) if area > 0 else 0.0
    return {"od_eff_in": casing.od_in, "wall_eff_in": wall_eff, "id_eff_in": id_eff, "area_in2": area, "I_in4": I, "S_in3": S, "r_in": r}


def steel_fy_for_compression(bar: Bar, casing: Optional[Casing]) -> float:
    values = [bar.fy_ksi, 87.0]  # FHWA strain compatibility cap for compression.
    if casing is not None and casing.od_in > 0 and casing.wall_in > 0:
        values.append(casing.fy_ksi)
    return min(values)


def steel_fy_for_cased_tension(bar: Bar, casing: Optional[Casing]) -> float:
    values = [bar.fy_ksi]
    if casing is not None and casing.od_in > 0 and casing.wall_in > 0:
        values.append(casing.fy_ksi)
    return min(values)


def grout_area_inside_casing(casing_section: Dict[str, float], bar_area_in2: float) -> float:
    if casing_section["id_eff_in"] <= 0:
        return 0.0
    return max(area_circle(casing_section["id_eff_in"]) - bar_area_in2, 0.0)


def grout_area_uncased(bond_diameter_in: float, bar_area_in2: float) -> float:
    return max(area_circle(bond_diameter_in) - bar_area_in2, 0.0)


def allowable_cased_compression(inputs: MicropileInputs) -> Dict[str, float]:
    cs = casing_effective_section(inputs.casing, inputs.corrosion_allowance_in)
    if cs["area_in2"] <= 0:
        return {"capacity_kips": 0.0, "grout_area_in2": 0.0, "steel_fy_ksi": 0.0, **cs}
    fc_ksi = inputs.grout_fc_psi / 1000.0
    fy = steel_fy_for_compression(inputs.bar, inputs.casing)
    agrout = grout_area_inside_casing(cs, inputs.bar.area_in2)
    capacity = 0.4 * fc_ksi * agrout + 0.47 * fy * (inputs.bar.area_in2 + cs["area_in2"])
    return {"capacity_kips": capacity, "grout_area_in2": agrout, "steel_fy_ksi": fy, **cs}


def allowable_cased_tension(inputs: MicropileInputs) -> Dict[str, float]:
    cs = casing_effective_section(inputs.casing, inputs.corrosion_allowance_in)
    casing_area = cs["area_in2"] if inputs.count_casing_in_tension else 0.0
    fy = steel_fy_for_cased_tension(inputs.bar, inputs.casing) if casing_area > 0 else inputs.bar.fy_ksi
    capacity = 0.55 * fy * (inputs.bar.area_in2 + casing_area)
    return {"capacity_kips": capacity, "steel_fy_ksi": fy, "casing_area_counted_in2": casing_area, **cs}


def allowable_uncased_compression(inputs: MicropileInputs) -> Dict[str, float]:
    fc_ksi = inputs.grout_fc_psi / 1000.0
    fy = min(inputs.bar.fy_ksi, 87.0)
    agrout = grout_area_uncased(inputs.bond_diameter_in, inputs.bar.area_in2)
    capacity = 0.4 * fc_ksi * agrout + 0.47 * fy * inputs.bar.area_in2
    return {"capacity_kips": capacity, "grout_area_in2": agrout, "steel_fy_ksi": fy}


def allowable_uncased_tension(inputs: MicropileInputs) -> Dict[str, float]:
    capacity = 0.55 * inputs.bar.fy_ksi * inputs.bar.area_in2
    return {"capacity_kips": capacity, "steel_fy_ksi": inputs.bar.fy_ksi}


def bond_allowable_stresses(inputs: MicropileInputs) -> Dict[str, float]:
    if inputs.use_user_allowable_bond:
        comp_allow = inputs.allowable_bond_comp_psi
        tension_allow = inputs.allowable_bond_tension_psi
        comp_ult = comp_allow
        tension_ult = tension_allow
        fs_comp = 1.0
        fs_tension = 1.0
    else:
        comp_ult = inputs.alpha_ultimate_comp_psi
        tension_ult = inputs.alpha_ultimate_tension_psi
        fs_comp = inputs.fs_bond_comp
        fs_tension = inputs.fs_bond_tension
        comp_allow = comp_ult / fs_comp if fs_comp > 0 else 0.0
        tension_allow = tension_ult / fs_tension if fs_tension > 0 else 0.0
    return {
        "compression_allowable_psi": comp_allow,
        "tension_allowable_psi": tension_allow,
        "compression_ultimate_psi": comp_ult,
        "tension_ultimate_psi": tension_ult,
        "fs_comp": fs_comp,
        "fs_tension": fs_tension,
    }


def bond_capacity_kips(diameter_in: float, length_ft: float, allowable_bond_psi: float) -> float:
    return pi * diameter_in * (length_ft * 12.0) * allowable_bond_psi / 1000.0


def required_bond_length_ft(load_kips: float, diameter_in: float, allowable_bond_psi: float) -> float:
    if load_kips <= 0:
        return 0.0
    if diameter_in <= 0 or allowable_bond_psi <= 0:
        return float("inf")
    return load_kips * 1000.0 / (pi * diameter_in * allowable_bond_psi) / 12.0


def round_up(value: float, increment: float) -> float:
    if value == float("inf"):
        return value
    if increment <= 0:
        return value
    from math import ceil
    return ceil(value / increment) * increment


def configuration_structural_capacities(inputs: MicropileInputs) -> Dict[str, Any]:
    cased_comp = allowable_cased_compression(inputs)
    cased_tension = allowable_cased_tension(inputs)
    uncased_comp = allowable_uncased_compression(inputs)
    uncased_tension = allowable_uncased_tension(inputs)

    config = inputs.pile_configuration.lower()
    if "hollow bar only" in config or "bar only" in config:
        compression_controlling = uncased_comp["capacity_kips"]
        tension_controlling = uncased_tension["capacity_kips"]
        controlling_comp_section = "bar + grout / no casing"
        controlling_tension_section = "bar only"
    elif "casing only" in config:
        # Conservative: casing must extend through the governing section. No uncased bar section exists.
        compression_controlling = cased_comp["capacity_kips"]
        tension_controlling = cased_tension["capacity_kips"]
        controlling_comp_section = "casing + grout"
        controlling_tension_section = "casing only; verify joints if used in tension"
    else:
        # Typical composite micropile: cased upper length plus uncased bond zone with center bar.
        if inputs.casing_extends_full_bond:
            compression_controlling = cased_comp["capacity_kips"]
            tension_controlling = cased_tension["capacity_kips"]
            controlling_comp_section = "full-depth cased section"
            controlling_tension_section = "full-depth cased section"
        else:
            compression_controlling = min(cased_comp["capacity_kips"], uncased_comp["capacity_kips"])
            tension_controlling = min(cased_tension["capacity_kips"], uncased_tension["capacity_kips"])
            controlling_comp_section = "min(cased upper length, uncased bond length)"
            controlling_tension_section = "min(cased upper length, uncased bond length)"

    return {
        "cased_compression": cased_comp,
        "cased_tension": cased_tension,
        "uncased_compression": uncased_comp,
        "uncased_tension": uncased_tension,
        "controlling_compression_capacity_kips": compression_controlling,
        "controlling_tension_capacity_kips": tension_controlling,
        "controlling_compression_section": controlling_comp_section,
        "controlling_tension_section": controlling_tension_section,
    }


def calculate(inputs: MicropileInputs) -> Dict[str, Any]:
    structural = configuration_structural_capacities(inputs)
    bond = bond_allowable_stresses(inputs)

    comp_capacity_geo = bond_capacity_kips(inputs.bond_diameter_in, inputs.provided_bond_length_ft, bond["compression_allowable_psi"])
    tension_capacity_geo = bond_capacity_kips(inputs.bond_diameter_in, inputs.provided_bond_length_ft, bond["tension_allowable_psi"])

    req_comp_load_for_bond = max(inputs.required_compression_kips, inputs.required_compression_kips * inputs.proof_factor_comp)
    req_tension_load_for_bond = max(inputs.required_tension_kips, inputs.required_tension_kips * inputs.proof_factor_tension)

    req_len_comp = required_bond_length_ft(req_comp_load_for_bond, inputs.bond_diameter_in, bond["compression_allowable_psi"])
    req_len_tension = required_bond_length_ft(req_tension_load_for_bond, inputs.bond_diameter_in, bond["tension_allowable_psi"])
    req_len_governing = max(req_len_comp, req_len_tension, inputs.min_socket_ft)
    req_len_governing_rounded = round_up(req_len_governing, inputs.round_socket_up_to_ft)

    comp_struct_ok = structural["controlling_compression_capacity_kips"] >= inputs.required_compression_kips
    tension_struct_ok = structural["controlling_tension_capacity_kips"] >= inputs.required_tension_kips if inputs.required_tension_kips > 0 else True
    comp_geo_ok = comp_capacity_geo >= inputs.required_compression_kips
    tension_geo_ok = tension_capacity_geo >= inputs.required_tension_kips if inputs.required_tension_kips > 0 else True
    provided_len_ok = inputs.provided_bond_length_ft >= req_len_governing

    final_ok = comp_struct_ok and tension_struct_ok and comp_geo_ok and tension_geo_ok and provided_len_ok

    warnings = []
    if inputs.count_casing_in_tension:
        warnings.append("Casing is counted in tension. Verify threaded joints/couplers and applicable specifications; FHWA cautions tension joints may need data/testing.")
    if inputs.corrosion_allowance_in > 0 and inputs.casing and inputs.casing.wall_in - inputs.corrosion_allowance_in <= 0:
        warnings.append("Corrosion allowance eliminates casing wall. Select larger wall thickness or reduce corrosion assumption if justified.")
    if inputs.required_tension_kips > inputs.required_compression_kips and bond["tension_allowable_psi"] < bond["compression_allowable_psi"]:
        warnings.append("Tension bond controls. Required socket may become much longer than compression socket.")
    if inputs.pile_configuration.lower().startswith("casing only") and not inputs.count_casing_in_tension and inputs.required_tension_kips > 0:
        warnings.append("Casing-only pile has tension demand but casing in tension is not enabled; tension capacity will be near zero.")
    if not final_ok:
        warnings.append("One or more checks fail. Increase bar/casing size, bond diameter, bond length, grout strength, or revise loads/assumptions.")

    return {
        "inputs": asdict(inputs),
        "structural": structural,
        "bond": bond,
        "geotechnical": {
            "provided_compression_bond_capacity_kips": comp_capacity_geo,
            "provided_tension_bond_capacity_kips": tension_capacity_geo,
            "required_length_compression_ft": req_len_comp,
            "required_length_tension_ft": req_len_tension,
            "required_length_governing_ft": req_len_governing,
            "required_length_governing_rounded_ft": req_len_governing_rounded,
        },
        "checks": {
            "compression_structural_ok": comp_struct_ok,
            "tension_structural_ok": tension_struct_ok,
            "compression_geotechnical_ok": comp_geo_ok,
            "tension_geotechnical_ok": tension_geo_ok,
            "provided_length_ok": provided_len_ok,
            "final_ok": final_ok,
        },
        "warnings": warnings,
    }


def flat_summary(results: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "Final OK": "OK" if results["checks"]["final_ok"] else "NG",
        "Controlling compression structural capacity (kips)": round(results["structural"]["controlling_compression_capacity_kips"], 1),
        "Controlling tension structural capacity (kips)": round(results["structural"]["controlling_tension_capacity_kips"], 1),
        "Provided compression bond capacity (kips)": round(results["geotechnical"]["provided_compression_bond_capacity_kips"], 1),
        "Provided tension bond capacity (kips)": round(results["geotechnical"]["provided_tension_bond_capacity_kips"], 1),
        "Required compression bond length (ft)": round(results["geotechnical"]["required_length_compression_ft"], 2),
        "Required tension bond length (ft)": round(results["geotechnical"]["required_length_tension_ft"], 2),
        "Governing required bond length rounded (ft)": results["geotechnical"]["required_length_governing_rounded_ft"],
        "Compression structural OK": results["checks"]["compression_structural_ok"],
        "Tension structural OK": results["checks"]["tension_structural_ok"],
        "Compression geotechnical OK": results["checks"]["compression_geotechnical_ok"],
        "Tension geotechnical OK": results["checks"]["tension_geotechnical_ok"],
        "Provided length OK": results["checks"]["provided_length_ok"],
    }
