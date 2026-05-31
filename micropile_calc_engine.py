"""
General micropile ASD axial design/check engine.

Preliminary calculations based on the FHWA NHI-05-039 Chapter 5 workflow and a
transparent calculation-report format:
- Cased compression structural capacity: casing + grout + bar components
- Cased tension structural capacity: bar, plus casing only when explicitly allowed
- Uncased/bond-zone compression structural capacity: grout + bar components
- Uncased tension structural capacity: bar components
- Multilayer grout-to-ground bond capacity below the casing end

This engine supports multilayer bond calculations below the casing end and multiple
reinforcement groups, including partial-length bars. It is intended for preliminary
ASD checks and calculation report generation; it is not a sealed design.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import pi, sqrt, ceil, isfinite
from typing import Any, Optional


@dataclass
class Bar:
    name: str
    bar_type: str
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
    area_in2: float = 0.0
    id_in: float = 0.0
    I_in4: float = 0.0
    S_in3: float = 0.0
    r_in: float = 0.0
    source: str = ""


@dataclass
class BarGroup:
    name: str
    bar: Bar
    quantity: int
    length_ft: float
    is_full_length: bool = False

    @property
    def area_total_in2(self) -> float:
        return max(self.quantity, 0) * max(self.bar.area_in2, 0.0)

    @property
    def nominal_diameter_in(self) -> float:
        if self.bar.od_in > 0:
            return self.bar.od_in
        if self.bar.area_in2 > 0:
            return sqrt(4.0 * self.bar.area_in2 / pi)
        return 0.0

    def effective_at_depth(self, depth_ft: float, tol: float = 1e-6) -> bool:
        if self.quantity <= 0:
            return False
        return self.length_ft + tol >= depth_ft


@dataclass
class SoilLayer:
    index: int
    label: str
    top_ft: float
    bottom_ft: float
    soil_type: str
    grout_type: str
    alpha_comp_psi: float
    alpha_tension_psi: float
    fs_comp: float
    fs_tension: float
    allowable_comp_psi: float
    allowable_tension_psi: float
    basis: str = "FHWA ultimate bond / FS"
    source: str = ""

    @property
    def thickness_ft(self) -> float:
        return max(self.bottom_ft - self.top_ft, 0.0)


@dataclass
class MicropileInputs:
    required_compression_kips: float
    required_tension_kips: float
    grout_fc_psi: float
    bond_diameter_in: float
    casing: Optional[Casing]
    casing_end_ft: float
    total_pile_length_ft: float
    corrosion_allowance_in: float
    pile_configuration: str
    bar_groups: list[BarGroup]
    soil_layers: list[SoilLayer]
    count_casing_in_tension: bool = False
    casing_extends_full_length: bool = False
    proof_factor_comp: float = 1.0
    proof_factor_tension: float = 1.0
    min_bond_length_ft: float = 0.0
    round_bond_up_to_ft: float = 0.5
    # Structural coefficients. Defaults follow the calculation-sheet style uploaded by the user.
    cgc: float = 0.33  # grout in cased length
    cgb: float = 0.30  # grout in bond/uncased length
    csc: float = 0.40  # casing compression steel
    csb: float = 0.40  # reinforcing bar compression steel
    cja: float = 1.00  # casing thread/joint area reduction in compression
    cbt: float = 0.55  # bar direct tension coefficient, AASHTO default. Use 0.60 if PTI allowed.


def area_circle(d_in: float) -> float:
    return pi * d_in**2 / 4.0 if d_in > 0 else 0.0


def bond_capacity_kips(diameter_in: float, length_ft: float, allowable_bond_psi: float) -> float:
    if diameter_in <= 0 or length_ft <= 0 or allowable_bond_psi <= 0:
        return 0.0
    return pi * diameter_in * length_ft * 12.0 * allowable_bond_psi / 1000.0


def bond_capacity_per_ft_kips(diameter_in: float, allowable_bond_psi: float) -> float:
    return bond_capacity_kips(diameter_in, 1.0, allowable_bond_psi)


def round_up(value: float, increment: float) -> float:
    if not isfinite(value):
        return value
    if increment <= 0:
        return value
    return ceil(value / increment) * increment


def casing_effective_section(casing: Optional[Casing], corrosion_allowance_in: float) -> dict[str, float]:
    """Return effective casing section after wall corrosion deduction.

    corrosion_allowance_in is a wall-thickness deduction. Some specifications instead state a total
    diameter loss; in that case the equivalent wall deduction is one-half of the diameter loss.
    """
    if casing is None or casing.od_in <= 0 or casing.wall_in <= 0:
        return {"od_eff_in": 0.0, "wall_eff_in": 0.0, "id_eff_in": 0.0, "area_in2": 0.0, "I_in4": 0.0, "S_in3": 0.0, "r_in": 0.0}
    wall_eff = max(casing.wall_in - max(corrosion_allowance_in, 0.0), 0.0)
    id_eff = max(casing.od_in - 2.0 * wall_eff, 0.0)
    area = pi / 4.0 * max(casing.od_in**2 - id_eff**2, 0.0)
    I = pi / 64.0 * max(casing.od_in**4 - id_eff**4, 0.0)
    S = I / (casing.od_in / 2.0) if casing.od_in > 0 else 0.0
    r = sqrt(I / area) if area > 0 else 0.0
    return {"od_eff_in": casing.od_in, "wall_eff_in": wall_eff, "id_eff_in": id_eff, "area_in2": area, "I_in4": I, "S_in3": S, "r_in": r}


def effective_bar_groups(inputs: MicropileInputs, depth_ft: float) -> list[BarGroup]:
    return [g for g in inputs.bar_groups if g.effective_at_depth(depth_ft)]


def bar_area_at_depth(inputs: MicropileInputs, depth_ft: float) -> float:
    return sum(g.area_total_in2 for g in effective_bar_groups(inputs, depth_ft))


def bar_area_fy_sum_at_depth(inputs: MicropileInputs, depth_ft: float, cap_87: bool = False) -> float:
    total = 0.0
    for g in effective_bar_groups(inputs, depth_ft):
        fy = min(g.bar.fy_ksi, 87.0) if cap_87 else g.bar.fy_ksi
        total += g.area_total_in2 * fy
    return total


def bar_min_fy_at_depth(inputs: MicropileInputs, depth_ft: float, cap_87: bool = False) -> float:
    groups = effective_bar_groups(inputs, depth_ft)
    if not groups:
        return 0.0
    fy = min(g.bar.fy_ksi for g in groups)
    return min(fy, 87.0) if cap_87 else fy


def cased_compression_at_depth(inputs: MicropileInputs, depth_ft: float) -> dict[str, float]:
    cs = casing_effective_section(inputs.casing, inputs.corrosion_allowance_in)
    bar_area = bar_area_at_depth(inputs, depth_ft)
    bar_area_fy = bar_area_fy_sum_at_depth(inputs, depth_ft, cap_87=True)
    if cs["area_in2"] <= 0:
        return {"capacity_kips": 0.0, "bar_area_in2": bar_area, "grout_area_in2": 0.0, "casing_component_kips": 0.0, "grout_component_kips": 0.0, "bar_component_kips": 0.0, "bar_area_fy_kip_per_in2": bar_area_fy, **cs}
    fc_ksi = inputs.grout_fc_psi / 1000.0
    grout_area = max(area_circle(cs["id_eff_in"]) - bar_area, 0.0)
    casing_fy = min(inputs.casing.fy_ksi if inputs.casing else 0.0, 87.0)
    casing_component = inputs.csc * inputs.cja * cs["area_in2"] * casing_fy
    grout_component = inputs.cgc * grout_area * fc_ksi
    bar_component = inputs.csb * bar_area_fy
    capacity = casing_component + grout_component + bar_component
    return {"capacity_kips": capacity, "bar_area_in2": bar_area, "grout_area_in2": grout_area, "casing_component_kips": casing_component, "grout_component_kips": grout_component, "bar_component_kips": bar_component, "casing_fy_used_ksi": casing_fy, "bar_area_fy_kip_per_in2": bar_area_fy, **cs}


def cased_tension_at_depth(inputs: MicropileInputs, depth_ft: float) -> dict[str, float]:
    cs = casing_effective_section(inputs.casing, inputs.corrosion_allowance_in)
    casing_area = cs["area_in2"] if inputs.count_casing_in_tension else 0.0
    bar_area = bar_area_at_depth(inputs, depth_ft)
    bar_area_fy = bar_area_fy_sum_at_depth(inputs, depth_ft, cap_87=False)
    casing_area_fy = casing_area * (inputs.casing.fy_ksi if inputs.casing else 0.0)
    bar_component = inputs.cbt * bar_area_fy
    casing_component = inputs.cbt * casing_area_fy
    capacity = bar_component + casing_component
    fy = bar_min_fy_at_depth(inputs, depth_ft, cap_87=False)
    return {"capacity_kips": capacity, "bar_area_in2": bar_area, "casing_area_counted_in2": casing_area, "steel_fy_ksi": fy, "bar_component_kips": bar_component, "casing_component_kips": casing_component, "bar_area_fy_kip_per_in2": bar_area_fy, **cs}


def uncased_compression_at_depth(inputs: MicropileInputs, depth_ft: float) -> dict[str, float]:
    bar_area = bar_area_at_depth(inputs, depth_ft)
    bar_area_fy = bar_area_fy_sum_at_depth(inputs, depth_ft, cap_87=True)
    fc_ksi = inputs.grout_fc_psi / 1000.0
    grout_area = max(area_circle(inputs.bond_diameter_in) - bar_area, 0.0)
    grout_component = inputs.cgb * grout_area * fc_ksi
    bar_component = inputs.csb * bar_area_fy
    capacity = grout_component + bar_component
    fy = bar_min_fy_at_depth(inputs, depth_ft, cap_87=True)
    return {"capacity_kips": capacity, "bar_area_in2": bar_area, "grout_area_in2": grout_area, "steel_fy_ksi": fy, "grout_component_kips": grout_component, "bar_component_kips": bar_component, "bar_area_fy_kip_per_in2": bar_area_fy}


def uncased_tension_at_depth(inputs: MicropileInputs, depth_ft: float) -> dict[str, float]:
    bar_area = bar_area_at_depth(inputs, depth_ft)
    bar_area_fy = bar_area_fy_sum_at_depth(inputs, depth_ft, cap_87=False)
    capacity = inputs.cbt * bar_area_fy
    fy = bar_min_fy_at_depth(inputs, depth_ft, cap_87=False)
    return {"capacity_kips": capacity, "bar_area_in2": bar_area, "steel_fy_ksi": fy, "bar_component_kips": capacity, "bar_area_fy_kip_per_in2": bar_area_fy}


def partial_bar_development_checks(inputs: MicropileInputs) -> list[dict[str, Any]]:
    """Simplified development-length check for partial bars using the uploaded example format.

    For partial bar scenarios, the report calculates a reference tension development length:
    ld1 = 0.05 db fy / sqrt(fc) and ld2 = 0.075 db fy / sqrt(fc), with fc in psi and fy in psi.
    The available length is conservatively taken as the length of the partial bar above the casing end.
    This is a planning check only; final development and connection detailing must be verified by EOR.
    """
    rows: list[dict[str, Any]] = []
    sqrt_fc = sqrt(max(inputs.grout_fc_psi, 1.0))
    for g in inputs.bar_groups:
        if g.quantity <= 0:
            continue
        if g.length_ft >= inputs.total_pile_length_ft - 1e-6:
            continue
        db = g.nominal_diameter_in
        fy_psi = g.bar.fy_ksi * 1000.0
        ld1 = 0.05 * db * fy_psi / sqrt_fc
        ld2 = 0.075 * db * fy_psi / sqrt_fc
        ld_req = max(ld1, ld2)
        avail_above_casing = max(g.length_ft - inputs.casing_end_ft, 0.0) * 12.0
        rows.append({
            "group": g.name,
            "bar": g.bar.name,
            "qty": g.quantity,
            "bar_diameter_in": db,
            "fy_ksi": g.bar.fy_ksi,
            "length_ft": g.length_ft,
            "ld1_in": ld1,
            "ld2_in": ld2,
            "ld_required_in": ld_req,
            "available_above_casing_in": avail_above_casing,
            "status": "OK" if avail_above_casing >= ld_req else "REVIEW",
            "note": "For partial bar scenario. Verify final development length/detailing by EOR."
        })
    return rows


def structural_capacities(inputs: MicropileInputs) -> dict[str, Any]:
    casing_end = min(max(inputs.casing_end_ft, 0.0), max(inputs.total_pile_length_ft, 0.0))
    tip = max(inputs.total_pile_length_ft, 0.0)
    has_casing = inputs.casing is not None and inputs.casing.od_in > 0 and inputs.casing.wall_in > 0
    config = inputs.pile_configuration.lower()

    cased_depth = casing_end if has_casing else 0.0
    uncased_start = casing_end
    uncased_tip = tip

    cased_comp = cased_compression_at_depth(inputs, cased_depth) if has_casing else {"capacity_kips": 0.0}
    cased_tens = cased_tension_at_depth(inputs, cased_depth) if has_casing else {"capacity_kips": 0.0}
    uncased_comp_start = uncased_compression_at_depth(inputs, uncased_start)
    uncased_comp_tip = uncased_compression_at_depth(inputs, uncased_tip)
    uncased_tens_start = uncased_tension_at_depth(inputs, uncased_start)
    uncased_tens_tip = uncased_tension_at_depth(inputs, uncased_tip)

    if "casing only" in config:
        comp_control = cased_comp["capacity_kips"]
        tens_control = cased_tens["capacity_kips"]
        comp_section = "casing-only / cased section"
        tens_section = "casing-only / cased section; verify threaded joints in tension"
    elif not has_casing or "bar only" in config or "hollow bar only" in config:
        comp_control = min(uncased_comp_start["capacity_kips"], uncased_comp_tip["capacity_kips"])
        tens_control = min(uncased_tens_start["capacity_kips"], uncased_tens_tip["capacity_kips"])
        comp_section = "bar + grout; checked at top and tip of bond"
        tens_section = "bar steel only; checked at top and tip of bond"
    elif inputs.casing_extends_full_length:
        cased_comp_tip = cased_compression_at_depth(inputs, tip)
        cased_tens_tip = cased_tension_at_depth(inputs, tip)
        comp_control = min(cased_comp["capacity_kips"], cased_comp_tip["capacity_kips"])
        tens_control = min(cased_tens["capacity_kips"], cased_tens_tip["capacity_kips"])
        comp_section = "full-depth cased section; checked at casing end and tip"
        tens_section = "full-depth cased section; checked at casing end and tip"
    else:
        comp_control = min(cased_comp["capacity_kips"], uncased_comp_start["capacity_kips"], uncased_comp_tip["capacity_kips"])
        tens_control = min(cased_tens["capacity_kips"], uncased_tens_start["capacity_kips"], uncased_tens_tip["capacity_kips"])
        comp_section = "minimum of cased section and uncased bond-zone section"
        tens_section = "minimum of cased section and uncased bond-zone section"

    return {
        "cased_compression": cased_comp,
        "cased_tension": cased_tens,
        "uncased_compression_start": uncased_comp_start,
        "uncased_compression_tip": uncased_comp_tip,
        "uncased_tension_start": uncased_tens_start,
        "uncased_tension_tip": uncased_tens_tip,
        "controlling_compression_capacity_kips": comp_control,
        "controlling_tension_capacity_kips": tens_control,
        "controlling_compression_section": comp_section,
        "controlling_tension_section": tens_section,
        "partial_bar_development": partial_bar_development_checks(inputs),
    }


def layer_overlap_below_casing(layer: SoilLayer, casing_end_ft: float, total_pile_length_ft: float) -> float:
    top = max(layer.top_ft, casing_end_ft)
    bottom = min(layer.bottom_ft, total_pile_length_ft)
    return max(bottom - top, 0.0)


def layer_bond_rows(inputs: MicropileInputs) -> list[dict[str, Any]]:
    rows = []
    for layer in sorted(inputs.soil_layers, key=lambda x: (x.top_ft, x.bottom_ft, x.index)):
        overlap = layer_overlap_below_casing(layer, inputs.casing_end_ft, inputs.total_pile_length_ft)
        rows.append({
            "layer_index": layer.index,
            "label": layer.label,
            "top_ft": layer.top_ft,
            "bottom_ft": layer.bottom_ft,
            "soil_type": layer.soil_type,
            "grout_type": layer.grout_type,
            "thickness_ft": layer.thickness_ft,
            "bond_overlap_ft": overlap,
            "allowable_comp_psi": layer.allowable_comp_psi,
            "allowable_tension_psi": layer.allowable_tension_psi,
            "comp_capacity_kips": bond_capacity_kips(inputs.bond_diameter_in, overlap, layer.allowable_comp_psi),
            "tension_capacity_kips": bond_capacity_kips(inputs.bond_diameter_in, overlap, layer.allowable_tension_psi),
            "basis": layer.basis,
            "source": layer.source,
        })
    return rows


def multilayer_bond_capacity(inputs: MicropileInputs) -> dict[str, Any]:
    rows = layer_bond_rows(inputs)
    total_comp = sum(r["comp_capacity_kips"] for r in rows)
    total_tension = sum(r["tension_capacity_kips"] for r in rows)
    return {"rows": rows, "provided_comp_capacity_kips": total_comp, "provided_tension_capacity_kips": total_tension}


def required_length_multilayer(inputs: MicropileInputs, direction: str, load_kips: float) -> dict[str, Any]:
    if load_kips <= 0:
        return {"required_length_ft": 0.0, "rounded_required_length_ft": max(inputs.min_bond_length_ft, 0.0), "segments": [], "satisfied": True, "target_kips": load_kips}
    target = load_kips * 1000.0
    accumulated = 0.0
    required_length = 0.0
    segments = []
    for layer in sorted(inputs.soil_layers, key=lambda x: (x.top_ft, x.bottom_ft, x.index)):
        overlap = layer_overlap_below_casing(layer, inputs.casing_end_ft, inputs.total_pile_length_ft)
        if overlap <= 0:
            continue
        allow = layer.allowable_comp_psi if direction == "compression" else layer.allowable_tension_psi
        capacity_per_ft_lbs = pi * inputs.bond_diameter_in * 12.0 * allow
        max_capacity_lbs = capacity_per_ft_lbs * overlap
        if capacity_per_ft_lbs <= 0:
            segments.append({"layer_index": layer.index, "used_length_ft": 0.0, "capacity_kips": 0.0, "note": "zero bond"})
            continue
        if accumulated + max_capacity_lbs >= target:
            need_lbs = target - accumulated
            used = need_lbs / capacity_per_ft_lbs
            required_length += used
            segments.append({"layer_index": layer.index, "used_length_ft": used, "capacity_kips": need_lbs / 1000.0, "note": "controls"})
            accumulated = target
            break
        else:
            required_length += overlap
            accumulated += max_capacity_lbs
            segments.append({"layer_index": layer.index, "used_length_ft": overlap, "capacity_kips": max_capacity_lbs / 1000.0, "note": "full layer"})
    satisfied = accumulated >= target - 1e-6
    if not satisfied:
        req = float("inf")
        rounded = float("inf")
    else:
        req = max(required_length, inputs.min_bond_length_ft)
        rounded = round_up(req, inputs.round_bond_up_to_ft)
    return {"required_length_ft": req, "rounded_required_length_ft": rounded, "segments": segments, "satisfied": satisfied, "target_kips": load_kips}


def calculate(inputs: MicropileInputs) -> dict[str, Any]:
    structural = structural_capacities(inputs)
    bond = multilayer_bond_capacity(inputs)
    comp_target = inputs.required_compression_kips * max(inputs.proof_factor_comp, 1.0)
    tens_target = inputs.required_tension_kips * max(inputs.proof_factor_tension, 1.0)
    req_comp = required_length_multilayer(inputs, "compression", comp_target)
    req_tens = required_length_multilayer(inputs, "tension", tens_target)
    governing_req = max(
        req_comp["rounded_required_length_ft"] if isfinite(req_comp["rounded_required_length_ft"]) else float("inf"),
        req_tens["rounded_required_length_ft"] if isfinite(req_tens["rounded_required_length_ft"]) else float("inf"),
        inputs.min_bond_length_ft,
    )
    available_bond_length = max(inputs.total_pile_length_ft - inputs.casing_end_ft, 0.0)

    comp_struct_ok = structural["controlling_compression_capacity_kips"] >= inputs.required_compression_kips - 1e-6
    tens_struct_ok = True if inputs.required_tension_kips <= 0 else structural["controlling_tension_capacity_kips"] >= inputs.required_tension_kips - 1e-6
    comp_geo_ok = bond["provided_comp_capacity_kips"] >= comp_target - 1e-6
    tens_geo_ok = True if tens_target <= 0 else bond["provided_tension_capacity_kips"] >= tens_target - 1e-6
    length_ok = available_bond_length >= governing_req - 1e-6 if isfinite(governing_req) else False

    warnings = []
    if inputs.total_pile_length_ft <= inputs.casing_end_ft:
        warnings.append("Total pile length is not below casing end; no bond length is available below casing.")
    if not req_comp["satisfied"] and comp_target > 0:
        warnings.append("Compression bond target cannot be developed within the entered layers below the casing end.")
    if not req_tens["satisfied"] and tens_target > 0:
        warnings.append("Tension/uplift bond target cannot be developed within the entered layers below the casing end.")
    if inputs.required_tension_kips > 0 and inputs.proof_factor_tension > 1.0:
        warnings.append("Tension proof testing can control bond length. Confirm test load and acceptance criteria with EOR/geotechnical engineer.")
    if inputs.count_casing_in_tension:
        warnings.append("Casing is counted in tension. Verify threaded casing joint/coupler tension capacity and corrosion requirements.")
    for g in inputs.bar_groups:
        if g.quantity > 0 and g.length_ft < inputs.total_pile_length_ft:
            warnings.append(f"Partial bar group '{g.name}' stops at {g.length_ft:.1f} ft; it is not counted below that depth.")
    if structural["partial_bar_development"]:
        warnings.append("Partial-length bar development checks are preliminary. Confirm final bar development/anchorage and couplers by EOR.")
    if not (comp_struct_ok and tens_struct_ok and comp_geo_ok and tens_geo_ok and length_ok):
        warnings.append("One or more checks fail. Increase bar/casing size, bond diameter, bond length, or revise loads/assumptions.")

    return {
        "inputs": asdict(inputs),
        "structural": structural,
        "bond": bond,
        "required_lengths": {"compression": req_comp, "tension": req_tens, "governing_rounded_ft": governing_req},
        "checks": {
            "compression_structural_ok": comp_struct_ok,
            "tension_structural_ok": tens_struct_ok,
            "compression_geotechnical_ok": comp_geo_ok,
            "tension_geotechnical_ok": tens_geo_ok,
            "provided_length_ok": length_ok,
            "final_ok": comp_struct_ok and tens_struct_ok and comp_geo_ok and tens_geo_ok and length_ok,
        },
        "warnings": warnings,
    }


def flat_summary(results: dict[str, Any]) -> dict[str, Any]:
    return {
        "Final OK": "OK" if results["checks"]["final_ok"] else "NG",
        "Controlling compression structural capacity (kips)": round(results["structural"]["controlling_compression_capacity_kips"], 1),
        "Controlling tension structural capacity (kips)": round(results["structural"]["controlling_tension_capacity_kips"], 1),
        "Provided compression bond capacity (kips)": round(results["bond"]["provided_comp_capacity_kips"], 1),
        "Provided tension bond capacity (kips)": round(results["bond"]["provided_tension_capacity_kips"], 1),
        "Required compression bond length (ft)": results["required_lengths"]["compression"]["rounded_required_length_ft"],
        "Required tension bond length (ft)": results["required_lengths"]["tension"]["rounded_required_length_ft"],
        "Governing required bond length (ft)": results["required_lengths"]["governing_rounded_ft"],
        "Compression structural OK": results["checks"]["compression_structural_ok"],
        "Tension structural OK": results["checks"]["tension_structural_ok"],
        "Compression geotechnical OK": results["checks"]["compression_geotechnical_ok"],
        "Tension geotechnical OK": results["checks"]["tension_geotechnical_ok"],
        "Provided length OK": results["checks"]["provided_length_ok"],
    }
