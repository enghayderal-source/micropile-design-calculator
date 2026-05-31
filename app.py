from __future__ import annotations

import json
import os
import hmac
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from micropile_calc_engine import (
    Bar, Casing, BarGroup, SoilLayer, MicropileInputs,
    calculate, flat_summary, bond_capacity_kips
)

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"

st.set_page_config(page_title="Micropile ASD Design Calculator", layout="wide")


def check_password() -> None:
    password = os.environ.get("APP_PASSWORD", "")
    if not password:
        return
    if st.session_state.get("password_ok"):
        return
    st.title("Micropile ASD Design Calculator")
    entered = st.text_input("Password", type="password")
    if st.button("Enter"):
        if hmac.compare_digest(entered, password):
            st.session_state["password_ok"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()


check_password()


@st.cache_data
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    bars = pd.read_csv(DATA_DIR / "bars.csv")
    casings = pd.read_csv(DATA_DIR / "casings.csv")
    bonds = pd.read_csv(DATA_DIR / "bond_library.csv")
    # Defensive no-duplicate cleanup by display names / dimensions.
    bars = bars.drop_duplicates(subset=["name"], keep="first").reset_index(drop=True)
    casings = casings.drop_duplicates(subset=["name"], keep="first").reset_index(drop=True)
    return bars, casings, bonds


def render_table(df: pd.DataFrame) -> None:
    html = df.to_html(index=False, escape=False, border=0)
    st.markdown(
        """
<style>
.mp-table { width:100%; border-collapse:collapse; font-size:0.89rem; }
.mp-table th { text-align:left; background:#f3f4f6; padding:7px; border:1px solid #ddd; }
.mp-table td { padding:7px; border:1px solid #ddd; vertical-align:top; }
.mp-table tr:nth-child(even) { background:#fafafa; }
.small-note { color:#4b5563; font-size:0.90rem; }
</style>
""",
        unsafe_allow_html=True,
    )
    html = html.replace('<table border="0" class="dataframe">', '<table class="mp-table">')
    st.markdown(html, unsafe_allow_html=True)


def make_bar(row: pd.Series, override: dict[str, float] | None = None) -> Bar:
    if override:
        return Bar("Custom Bar", "Custom", override["area_in2"], override["od_in"], override["id_in"], override["fy_ksi"], "User input")
    return Bar(str(row["name"]), str(row["bar_type"]), float(row["area_in2"]), float(row["od_in"]), float(row["id_in"]), float(row["fy_ksi"]), str(row.get("source", "")))


def make_casing(row: pd.Series, override: dict[str, float] | None = None) -> Casing | None:
    if override:
        od, wall = override["od_in"], override["wall_in"]
        return Casing("Custom Casing", od, wall, override["fy_ksi"])
    if float(row["od_in"]) <= 0:
        return None
    return Casing(
        str(row["name"]), float(row["od_in"]), float(row["wall_in"]), float(row["fy_ksi"]),
        float(row.get("area_in2", 0.0)), float(row.get("id_in", 0.0)), float(row.get("I_in4", 0.0)),
        float(row.get("S_in3", 0.0)), float(row.get("r_in", 0.0)), str(row.get("source", ""))
    )


def get_bond_row(bonds_df: pd.DataFrame, soil_type: str, grout_type: str) -> pd.Series:
    rows = bonds_df[(bonds_df["soil_rock_description"] == soil_type) & (bonds_df["grout_type"] == grout_type)]
    if rows.empty:
        rows = bonds_df[bonds_df["soil_rock_description"] == soil_type]
    return rows.iloc[0]


def build_layer(index: int, label: str, top_ft: float, bottom_ft: float, soil_type: str, grout_type: str,
                alpha_choice: str, fs_comp: float, fs_tension: float, custom_allowable: bool,
                custom_comp_psi: float, custom_tension_psi: float, bonds_df: pd.DataFrame) -> SoilLayer:
    row = get_bond_row(bonds_df, soil_type, grout_type)
    alpha = float(row[f"alpha_{alpha_choice}_psi"])
    if custom_allowable:
        return SoilLayer(index, label, top_ft, bottom_ft, soil_type, grout_type, custom_comp_psi, custom_tension_psi, 1.0, 1.0, custom_comp_psi, custom_tension_psi, "User allowable bond", "User input")
    return SoilLayer(index, label, top_ft, bottom_ft, soil_type, grout_type, alpha, alpha, fs_comp, fs_tension, alpha / fs_comp if fs_comp else 0.0, alpha / fs_tension if fs_tension else 0.0, "FHWA ultimate bond / FS", str(row.get("source", "")))


def soil_color(name: str) -> str:
    n = (name or "").lower()
    if any(x in n for x in ["rock", "shale", "limestone", "sandstone", "granite", "basalt"]): return "#b8b8b8"
    if "fill" in n: return "#c8a15b"
    if "clay" in n or "silt" in n: return "#d8c6a4"
    if "sand" in n: return "#f1d890"
    if "gravel" in n or "till" in n: return "#cfcfcf"
    return "#e8e2d0"


def txt(x: float, y: float, t: str, size: int = 11, weight: str = "normal", anchor: str = "start") -> str:
    s = str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<text x="{x}" y="{y}" font-size="{size}" font-family="Arial" font-weight="{weight}" text-anchor="{anchor}" fill="#1f2937">{s}</text>'


def make_svg(layers: list[SoilLayer], inputs: MicropileInputs, results: dict[str, Any], casing_label: str, bar_labels: str, groundwater_ft: float | None) -> str:
    max_depth = max([l.bottom_ft for l in layers] + [inputs.total_pile_length_ft, 20.0])
    width, height = 920, 680
    top, bottom = 70, 610
    scale = (bottom - top) / max_depth
    def y(d: float) -> float: return top + d * scale

    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" xmlns="http://www.w3.org/2000/svg">']
    parts.append('<rect width="100%" height="100%" fill="white"/>')
    parts.append(txt(20, 30, "Micropile / Multilayer Bond Schematic", 18, "bold"))
    parts.append(txt(20, 50, "Bond is accumulated through all layers below the casing end until pile tip.", 11))
    # soil layers
    sx, sw = 520, 270
    parts.append(f'<rect x="{sx-8}" y="{top-8}" width="{sw+16}" height="{bottom-top+16}" fill="#f9fafb" stroke="#d1d5db"/>')
    bond_rows = {r["layer_index"]: r for r in results["bond"]["rows"]}
    for layer in layers:
        yt, yb = y(layer.top_ft), y(layer.bottom_ft)
        used = bond_rows.get(layer.index, {}).get("bond_overlap_ft", 0) > 0
        stroke = "#16a34a" if used else "#777"
        swidth = 4 if used else 1
        parts.append(f'<rect x="{sx}" y="{yt}" width="{sw}" height="{max(yb-yt,2)}" fill="{soil_color(layer.soil_type)}" stroke="{stroke}" stroke-width="{swidth}"/>')
        mid = (yt+yb)/2
        parts.append(txt(sx+8, mid-10, f'L{layer.index+1}: {layer.label}', 11, "bold"))
        parts.append(txt(sx+8, mid+5, f'{layer.soil_type}', 10))
        parts.append(txt(sx+8, mid+20, f'{layer.top_ft:.1f}–{layer.bottom_ft:.1f} ft | αallow C/T {layer.allowable_comp_psi:.1f}/{layer.allowable_tension_psi:.1f} psi', 10))
    # pile
    px = 250
    pile_w = max(24, min(75, inputs.bond_diameter_in * 4.5))
    parts.append(f'<line x1="55" y1="{top}" x2="820" y2="{top}" stroke="#111827" stroke-width="2"/>')
    parts.append(txt(55, top-10, "Existing grade", 12, "bold"))
    parts.append(f'<rect x="{px-pile_w/2}" y="{top}" width="{pile_w}" height="{max(y(inputs.total_pile_length_ft)-top,0)}" fill="#dbeafe" stroke="#1d4ed8" stroke-width="2" rx="4"/>')
    cased_len = min(inputs.casing_end_ft if not inputs.casing_extends_full_length else inputs.total_pile_length_ft, inputs.total_pile_length_ft)
    if inputs.casing and inputs.casing.od_in > 0:
        parts.append(f'<rect x="{px-pile_w*0.40}" y="{top}" width="{pile_w*0.8}" height="{max(y(cased_len)-top,0)}" fill="none" stroke="#111827" stroke-width="6"/>')
    # center bars: full and partial
    colors = ["#7c2d12", "#be123c", "#6d28d9"]
    for idx, g in enumerate(inputs.bar_groups[:3]):
        if g.quantity <= 0: continue
        off = (idx-1)*8
        dash = "" if g.length_ft >= inputs.total_pile_length_ft else "7 5"
        parts.append(f'<line x1="{px+off}" y1="{top}" x2="{px+off}" y2="{y(min(g.length_ft, inputs.total_pile_length_ft))}" stroke="{colors[idx%len(colors)]}" stroke-width="6" stroke-dasharray="{dash}"/>')
    # casing end and bond interval
    parts.append(f'<line x1="{px-95}" y1="{y(inputs.casing_end_ft)}" x2="{px+190}" y2="{y(inputs.casing_end_ft)}" stroke="#111827" stroke-dasharray="6 4"/>')
    parts.append(txt(px+100, y(inputs.casing_end_ft)-6, f'Casing end / bond start = {inputs.casing_end_ft:.1f} ft', 11, "bold"))
    parts.append(f'<rect x="{px-pile_w/2-10}" y="{y(inputs.casing_end_ft)}" width="{pile_w+20}" height="{max(y(inputs.total_pile_length_ft)-y(inputs.casing_end_ft),0)}" fill="none" stroke="#16a34a" stroke-width="4" stroke-dasharray="8 5"/>')
    parts.append(txt(px+pile_w/2+16, y(inputs.casing_end_ft)+22, f'Available bond length = {max(inputs.total_pile_length_ft-inputs.casing_end_ft,0):.1f} ft', 11, "bold"))
    parts.append(txt(px+pile_w/2+16, y(inputs.casing_end_ft)+40, f'Governing required = {results["required_lengths"]["governing_rounded_ft"]} ft', 11))
    # cap and dimensions
    parts.append(f'<rect x="{px-85}" y="{top-30}" width="170" height="22" fill="#e5e7eb" stroke="#6b7280"/>')
    parts.append(txt(px, top-15, "Pile cap", 11, "bold", "middle"))
    axis_x = 840
    parts.append(f'<line x1="{axis_x}" y1="{top}" x2="{axis_x}" y2="{bottom}" stroke="#374151"/>')
    step = 5 if max_depth <= 60 else 10
    d = 0
    while d <= max_depth + 0.01:
        parts.append(f'<line x1="{axis_x-5}" y1="{y(d)}" x2="{axis_x+5}" y2="{y(d)}" stroke="#374151"/>')
        parts.append(txt(axis_x+10, y(d)+4, f'{d:.0f} ft', 10))
        d += step
    if groundwater_ft is not None and 0 <= groundwater_ft <= max_depth:
        parts.append(f'<line x1="55" y1="{y(groundwater_ft)}" x2="820" y2="{y(groundwater_ft)}" stroke="#2563eb" stroke-width="2" stroke-dasharray="7 4"/>')
        parts.append(txt(60, y(groundwater_ft)-5, f'Groundwater ~ {groundwater_ft:.1f} ft', 11, "bold"))
    parts.append(txt(20, 645, f'Casing: {casing_label}', 11))
    parts.append(txt(20, 662, f'Reinforcement: {bar_labels}', 11))
    parts.append(txt(520, 645, f'Bond diameter: {inputs.bond_diameter_in:.1f} in', 11))
    parts.append('</svg>')
    return ''.join(parts)


bars_df, casings_df, bonds_df = load_data()

st.title("Micropile ASD Design Calculator")
st.caption("General preliminary axial compression/tension, casing/bar/grout, and multilayer grout-to-ground bond checks based on the FHWA NHI-05-039 workflow.")

with st.sidebar:
    st.header("Design Loads")
    required_compression_kips = st.number_input("Required allowable compression per pile (kips)", min_value=0.0, value=150.0, step=5.0)
    required_tension_kips = st.number_input("Required allowable uplift/tension per pile (kips)", min_value=0.0, value=0.0, step=5.0)
    grout_fc_psi = st.number_input("Grout/concrete f'c (psi)", min_value=1000.0, value=5000.0, step=500.0)

    st.header("Pile Geometry")
    pile_configuration = st.selectbox("Pile configuration", ["Casing + bar", "Bar only / hollow bar only", "Casing only - casing extends full length"], index=0)
    casing_end_ft = st.number_input("Casing end depth / bond start (ft)", min_value=0.0, value=20.0, step=0.5)
    total_pile_length_ft = st.number_input("Total pile length / pile tip depth (ft)", min_value=0.1, value=35.0, step=0.5)
    bond_diameter_in = st.number_input("Bond/drill hole diameter (in)", min_value=0.1, value=8.0, step=0.5)
    min_bond_length_ft = st.number_input("Minimum specified bond/socket length (ft)", min_value=0.0, value=0.0, step=0.5)
    round_bond_up_to_ft = st.selectbox("Round required bond length up to", [0.5, 1.0, 2.0, 5.0], index=0)

    st.header("Casing")
    casing_names = casings_df["name"].tolist()
    default_casing = "Nucor A252 Pipe 9 5/8 in OD x 0.500 in wall"
    if "Bar only" in pile_configuration:
        default_casing = "No casing"
    casing_idx = casing_names.index(default_casing) if default_casing in casing_names else 0
    selected_casing_name = st.selectbox("Select casing", casing_names, index=casing_idx)
    selected_casing_row = casings_df[casings_df["name"] == selected_casing_name].iloc[0]
    custom_casing = None
    if selected_casing_name == "Custom Casing":
        c1, c2 = st.columns(2)
        custom_casing = {
            "od_in": c1.number_input("Casing OD (in)", min_value=0.0, value=9.625, step=0.125),
            "wall_in": c2.number_input("Wall (in)", min_value=0.0, value=0.500, step=0.025),
            "fy_ksi": c1.number_input("Fy (ksi)", min_value=0.0, value=50.0, step=5.0),
        }
    casing = make_casing(selected_casing_row, custom_casing)
    corrosion_allowance_in = st.number_input("Casing corrosion wall deduction (in)", min_value=0.0, value=0.0, step=0.015625, format="%.5f")
    count_casing_in_tension = st.checkbox("Count casing in tension capacity", value=False)
    casing_extends_full_length = "Casing only" in pile_configuration or st.checkbox("Casing extends to pile tip", value=False)

    st.header("Testing Factors")
    proof_factor_comp = st.number_input("Compression proof/test factor for bond", min_value=1.0, value=1.0, step=0.1)
    proof_factor_tension = st.number_input("Tension proof/test factor for bond", min_value=1.0, value=1.0, step=0.1)

    st.header("Drawing")
    show_groundwater = st.checkbox("Show groundwater line", value=False)
    groundwater_ft = st.number_input("Groundwater depth (ft)", min_value=0.0, value=10.0, step=0.5) if show_groundwater else None

st.subheader("Reinforcement Groups")
st.markdown("<div class='small-note'>Use one or more full-length or partial-length bar groups. Partial bars are counted only down to their entered length.</div>", unsafe_allow_html=True)
bar_types = ["All"] + sorted(bars_df["bar_type"].dropna().unique().tolist())


def select_bar_group(group_name: str, default_type: str, default_bar_contains: str, default_qty: int, default_len: float, allow_disable: bool = False) -> BarGroup:
    enabled = True
    if allow_disable:
        enabled = st.checkbox(f"Enable {group_name}", value=False, key=f"enable_{group_name}")
    if not enabled:
        dummy = make_bar(bars_df.iloc[0])
        return BarGroup(group_name, dummy, 0, 0.0)
    c1, c2, c3, c4 = st.columns([1.1, 2.4, 0.8, 1.0])
    typ_idx = bar_types.index(default_type) if default_type in bar_types else 0
    typ = c1.selectbox(f"{group_name} type", bar_types, index=typ_idx, key=f"type_{group_name}")
    filtered = bars_df if typ == "All" else bars_df[bars_df["bar_type"] == typ]
    names = filtered["name"].tolist()
    default_name = next((n for n in names if default_bar_contains in n), names[0])
    name = c2.selectbox(f"{group_name} bar", names, index=names.index(default_name), key=f"bar_{group_name}")
    qty = c3.number_input(f"{group_name} qty", min_value=0, max_value=20, value=default_qty, step=1, key=f"qty_{group_name}")
    length = c4.number_input(f"{group_name} length from top (ft)", min_value=0.0, value=default_len, step=0.5, key=f"len_{group_name}")
    row = bars_df[bars_df["name"] == name].iloc[0]
    return BarGroup(group_name, make_bar(row), int(qty), float(length), length >= total_pile_length_ft)

primary = select_bar_group("Primary", "Solid threaded bar", "#20", 1, total_pile_length_ft)
partial1 = select_bar_group("Additional / partial group 1", "Solid threaded bar", "#18", 0, casing_end_ft, allow_disable=True)
partial2 = select_bar_group("Additional / partial group 2", "Hollow core bar", "TB103/75", 0, casing_end_ft, allow_disable=True)
bar_groups = [g for g in [primary, partial1, partial2] if g.quantity > 0]
if not bar_groups and "casing only" not in pile_configuration.lower():
    st.warning("No reinforcing bars selected. Add at least one bar group unless this is intentionally casing-only.")

st.subheader("Stratigraphy / Multilayer Bond Inputs")
st.markdown("<div class='small-note'>Each layer is pulled from the bond table. Bond capacity is accumulated only for the portion of each layer below the casing end and above the pile tip.</div>", unsafe_allow_html=True)
soil_options = sorted(bonds_df["soil_rock_description"].unique().tolist())
num_layers = st.number_input("Number of soil/rock layers", min_value=1, max_value=8, value=4, step=1)
soil_layers: list[SoilLayer] = []
prev_bottom = 0.0
for i in range(int(num_layers)):
    with st.expander(f"Layer L{i+1}", expanded=True if i < 4 else False):
        c1, c2, c3 = st.columns([1.2, 0.8, 0.8])
        default_label = ["Fill/overburden", "Bearing soil", "Weathered rock", "Competent rock"][i] if i < 4 else f"Layer {i+1}"
        label = c1.text_input("Layer label", value=default_label, key=f"layer_label_{i}")
        top = c2.number_input("Top depth (ft)", min_value=0.0, value=float(prev_bottom), step=0.5, key=f"top_{i}")
        bottom_default = max(top + 5.0, casing_end_ft + 15.0 if i == 3 else top + 8.0)
        bottom = c3.number_input("Bottom depth (ft)", min_value=top + 0.1, value=float(bottom_default), step=0.5, key=f"bottom_{i}")
        c4, c5, c6 = st.columns([2.1, 0.8, 0.8])
        default_soil = "Sandstone - fresh/moderate fracture" if i >= 2 and "Sandstone - fresh/moderate fracture" in soil_options else soil_options[min(i, len(soil_options)-1)]
        soil_type = c4.selectbox("Soil / rock type", soil_options, index=soil_options.index(default_soil), key=f"soil_{i}")
        grout_types = bonds_df[bonds_df["soil_rock_description"] == soil_type]["grout_type"].tolist()
        grout_type = c5.selectbox("Grout type", grout_types, index=0, key=f"grout_{i}")
        alpha_choice = c6.radio("αbond", ["low", "mid", "high"], index=1, horizontal=True, key=f"alpha_{i}")
        c7, c8, c9 = st.columns([0.8, 0.8, 1.4])
        fs_comp = c7.number_input("FS comp", min_value=1.0, value=2.0, step=0.25, key=f"fscomp_{i}")
        fs_tens = c8.number_input("FS tension", min_value=1.0, value=2.0, step=0.25, key=f"fstens_{i}")
        custom = c9.checkbox("Use user allowable bond for this layer", value=False, key=f"custbond_{i}")
        custom_c = custom_t = 0.0
        if custom:
            c10, c11 = st.columns(2)
            custom_c = c10.number_input("Allowable comp bond (psi)", min_value=0.0, value=75.0, step=5.0, key=f"custc_{i}")
            custom_t = c11.number_input("Allowable tension bond (psi)", min_value=0.0, value=25.0, step=5.0, key=f"custt_{i}")
        soil_layers.append(build_layer(i, label, float(top), float(bottom), soil_type, grout_type, alpha_choice, float(fs_comp), float(fs_tens), bool(custom), float(custom_c), float(custom_t), bonds_df))
        prev_bottom = float(bottom)

if total_pile_length_ft <= casing_end_ft:
    st.error("Total pile length must be deeper than casing end to develop bond below casing.")

inputs = MicropileInputs(
    required_compression_kips=float(required_compression_kips),
    required_tension_kips=float(required_tension_kips),
    grout_fc_psi=float(grout_fc_psi),
    bond_diameter_in=float(bond_diameter_in),
    casing=casing,
    casing_end_ft=float(casing_end_ft),
    total_pile_length_ft=float(total_pile_length_ft),
    corrosion_allowance_in=float(corrosion_allowance_in),
    pile_configuration=pile_configuration,
    bar_groups=bar_groups,
    soil_layers=soil_layers,
    count_casing_in_tension=bool(count_casing_in_tension),
    casing_extends_full_length=bool(casing_extends_full_length),
    proof_factor_comp=float(proof_factor_comp),
    proof_factor_tension=float(proof_factor_tension),
    min_bond_length_ft=float(min_bond_length_ft),
    round_bond_up_to_ft=float(round_bond_up_to_ft),
)

results = calculate(inputs)
summary = flat_summary(results)

st.subheader("Summary")
cols = st.columns(6)
cols[0].metric("Final Status", summary["Final OK"])
cols[1].metric("Req. Comp.", f"{required_compression_kips:.0f} kips")
cols[2].metric("Provided Comp. Bond", f"{summary['Provided compression bond capacity (kips)']:.1f} kips")
cols[3].metric("Req. Bond Length", f"{summary['Governing required bond length (ft)']} ft")
cols[4].metric("Available Bond Length", f"{max(total_pile_length_ft-casing_end_ft,0):.1f} ft")
cols[5].metric("Struct. Comp. Cap.", f"{summary['Controlling compression structural capacity (kips)']:.1f} kips")

check_rows = [
    {"Check": "Compression structural", "Result": "OK" if summary["Compression structural OK"] else "NG"},
    {"Check": "Tension structural", "Result": "OK" if summary["Tension structural OK"] else "NG"},
    {"Check": "Compression multilayer bond", "Result": "OK" if summary["Compression geotechnical OK"] else "NG"},
    {"Check": "Tension multilayer bond", "Result": "OK" if summary["Tension geotechnical OK"] else "NG"},
    {"Check": "Available bond length", "Result": "OK" if summary["Provided length OK"] else "NG"},
]
render_table(pd.DataFrame(check_rows))

st.subheader("Multilayer Bond Capacity Below Casing")
layer_rows = []
for r in results["bond"]["rows"]:
    layer_rows.append({
        "Used Below Casing?": "YES" if r["bond_overlap_ft"] > 0 else "No",
        "Layer": f"L{r['layer_index']+1}",
        "Label": r["label"],
        "Depth (ft)": f"{r['top_ft']:.1f}–{r['bottom_ft']:.1f}",
        "Soil/Rock": r["soil_type"],
        "Grout": r["grout_type"],
        "Bond Length Used (ft)": round(r["bond_overlap_ft"], 2),
        "αallow C/T (psi)": f"{r['allowable_comp_psi']:.1f}/{r['allowable_tension_psi']:.1f}",
        "Comp Cap. (kip)": round(r["comp_capacity_kips"], 1),
        "Tens Cap. (kip)": round(r["tension_capacity_kips"], 1),
        "Basis": r["basis"],
    })
render_table(pd.DataFrame(layer_rows))

st.subheader("Structural Capacity Details")
struct = results["structural"]
struct_rows = [
    {"Section": "Cased compression at casing end", "Capacity (kips)": round(struct["cased_compression"].get("capacity_kips", 0), 1), "Bar Area (in²)": round(struct["cased_compression"].get("bar_area_in2", 0), 2)},
    {"Section": "Cased tension at casing end", "Capacity (kips)": round(struct["cased_tension"].get("capacity_kips", 0), 1), "Bar Area (in²)": round(struct["cased_tension"].get("bar_area_in2", 0), 2)},
    {"Section": "Uncased compression at bond start", "Capacity (kips)": round(struct["uncased_compression_start"].get("capacity_kips", 0), 1), "Bar Area (in²)": round(struct["uncased_compression_start"].get("bar_area_in2", 0), 2)},
    {"Section": "Uncased compression at pile tip", "Capacity (kips)": round(struct["uncased_compression_tip"].get("capacity_kips", 0), 1), "Bar Area (in²)": round(struct["uncased_compression_tip"].get("bar_area_in2", 0), 2)},
    {"Section": "Uncased tension at bond start", "Capacity (kips)": round(struct["uncased_tension_start"].get("capacity_kips", 0), 1), "Bar Area (in²)": round(struct["uncased_tension_start"].get("bar_area_in2", 0), 2)},
    {"Section": "Uncased tension at pile tip", "Capacity (kips)": round(struct["uncased_tension_tip"].get("capacity_kips", 0), 1), "Bar Area (in²)": round(struct["uncased_tension_tip"].get("bar_area_in2", 0), 2)},
]
render_table(pd.DataFrame(struct_rows))

st.subheader("Required Bond Length by Layer")
seg_rows = []
for direction in ["compression", "tension"]:
    req = results["required_lengths"][direction]
    for s in req["segments"]:
        seg_rows.append({"Direction": direction.title(), "Layer": f"L{s['layer_index']+1}", "Used Length (ft)": round(s["used_length_ft"], 2), "Capacity (kip)": round(s["capacity_kips"], 1), "Note": s["note"]})
render_table(pd.DataFrame(seg_rows if seg_rows else [{"Direction":"—", "Layer":"—", "Used Length (ft)":0, "Capacity (kip)":0, "Note":"No bond demand"}]))

if results["warnings"]:
    for w in results["warnings"]:
        st.warning(w)

st.subheader("Schematic Drawing")
bar_label = "; ".join([f"{g.quantity}x {g.bar.name} to {g.length_ft:.1f} ft" for g in bar_groups]) or "None"
casing_label = casing.name if casing else "No casing"
st.markdown(make_svg(soil_layers, inputs, results, casing_label, bar_label, groundwater_ft), unsafe_allow_html=True)

with st.expander("Database preview / no duplicate check"):
    st.markdown("**Bars:** unique names by bar type and grade. **Casings:** unique OD x wall rows from the pipe database plus No casing and Custom Casing.")
    c1, c2 = st.columns(2)
    c1.metric("Bar rows", len(bars_df))
    c2.metric("Casing rows", len(casings_df))

with st.expander("Detailed assumptions and equations"):
    st.markdown(
        """
- Cased compression follows FHWA Eq. 5-1 using grout plus casing/bar steel. For mixed steel grades, the app uses the minimum applicable steel Fy capped at 87 ksi for compression strain compatibility.
- Cased tension follows FHWA Eq. 5-2. Casing is not counted in tension unless you turn on the casing-tension option.
- Uncased compression follows FHWA Eq. 5-7. Uncased tension follows Eq. 5-8.
- Multilayer bond capacity follows FHWA Eq. 5-9. For each layer below the casing end, the app calculates overlap length × π × bond diameter × allowable bond.
- FHWA Table 5-3 bond values are ultimate values; the app divides them by the layer FS unless you enter user allowable bond values.
- Partial bars are counted only at depths where the entered bar length reaches that depth.
"""
    )

report = {
    "summary": summary,
    "bar_groups": [{"name": g.name, "bar": g.bar.name, "quantity": g.quantity, "length_ft": g.length_ft, "area_total_in2": g.area_total_in2} for g in bar_groups],
    "casing": casing_label,
    "results": results,
}
st.download_button("Download JSON report", data=json.dumps(report, indent=2, default=str), file_name="micropile_design_report.json", mime="application/json")
