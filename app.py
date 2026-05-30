from __future__ import annotations

import json
import os
import hmac
from pathlib import Path

import pandas as pd
import streamlit as st

from micropile_calc_engine import (
    Bar,
    Casing,
    MicropileInputs,
    calculate,
    flat_summary,
)

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"

st.set_page_config(page_title="Micropile ASD Design Calculator", layout="wide")


def check_password() -> bool:
    """Optional simple password protection for cloud deployment.

    Set environment variable APP_PASSWORD in your cloud host.
    If APP_PASSWORD is not set, the app is public.
    """
    expected_password = os.environ.get("APP_PASSWORD", "")
    if not expected_password:
        return True

    if st.session_state.get("password_correct", False):
        return True

    st.title("Micropile ASD Design Calculator")
    st.caption("Enter the app password to continue.")
    entered_password = st.text_input("Password", type="password")

    if entered_password:
        if hmac.compare_digest(entered_password, expected_password):
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    st.stop()


check_password()


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    bars = pd.read_csv(DATA_DIR / "bars.csv")
    casings = pd.read_csv(DATA_DIR / "casings.csv")
    bonds = pd.read_csv(DATA_DIR / "bond_library.csv")
    return bars, casings, bonds


def status_badge(ok: bool) -> str:
    return "OK" if ok else "NG"


def render_table(df: pd.DataFrame) -> None:
    """Render tables as plain HTML to avoid Streamlit DataFrame JS chunk loading issues on cloud."""
    html = df.to_html(index=False, escape=False, border=0)
    st.markdown(
        """
<style>
.micropile-table { width: 100%; border-collapse: collapse; font-size: 0.95rem; }
.micropile-table th { text-align: left; background: #f4f6f8; padding: 8px; border: 1px solid #ddd; }
.micropile-table td { padding: 8px; border: 1px solid #ddd; vertical-align: top; }
.micropile-table tr:nth-child(even) { background: #fafafa; }
</style>
        """,
        unsafe_allow_html=True,
    )
    html = html.replace('<table border="0" class="dataframe">', '<table class="micropile-table">')
    st.markdown(html, unsafe_allow_html=True)


def _soil_color(name: str) -> str:
    """Return a simple stable color based on layer name for schematic SVG only."""
    n = (name or "").lower()
    if "rock" in n or "shale" in n or "limestone" in n or "sandstone" in n or "granite" in n or "basalt" in n:
        return "#b9b9b9"
    if "fill" in n:
        return "#c9a36a"
    if "clay" in n or "silt" in n:
        return "#d7c4a3"
    if "sand" in n:
        return "#f2d98d"
    if "gravel" in n or "till" in n:
        return "#cfcfcf"
    return "#e6e2d3"


def _svg_text(x: float, y: float, text: str, size: int = 12, weight: str = "normal", anchor: str = "start") -> str:
    safe = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<text x="{x}" y="{y}" font-size="{size}" font-family="Arial" font-weight="{weight}" text-anchor="{anchor}" fill="#1f2937">{safe}</text>'


def make_profile_svg(layers: list[dict], total_length_ft: float, cased_length_ft: float, bond_length_ft: float, bond_diameter_in: float, casing_label: str, bar_label: str, groundwater_ft: float | None = None) -> str:
    """Schematic micropile + soil profile SVG. Not to scale horizontally; vertical depths are proportional."""
    max_depth = max([float(layer["bottom_ft"]) for layer in layers] + [total_length_ft, cased_length_ft + bond_length_ft, 10.0])
    width, height = 760, 620
    top, bottom = 55, 565
    scale = (bottom - top) / max_depth

    def y(depth_ft: float) -> float:
        return top + depth_ft * scale

    casing_depth = min(max(cased_length_ft, 0), max_depth)
    pile_tip = min(max(total_length_ft, cased_length_ft + bond_length_ft), max_depth)
    bond_top = max(cased_length_ft, 0)
    bond_bottom = min(bond_top + max(bond_length_ft, 0), pile_tip)

    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="auto" xmlns="http://www.w3.org/2000/svg">']
    parts.append('<rect x="0" y="0" width="760" height="620" fill="white"/>')
    parts.append(_svg_text(20, 28, "Micropile and Soil Profile Schematic", 18, "bold"))
    parts.append(_svg_text(20, 46, "Conceptual drawing generated from inputs - not a sealed/shop drawing", 11))

    # Soil profile panel
    sx, sw = 395, 230
    parts.append('<rect x="390" y="50" width="245" height="520" fill="#f9fafb" stroke="#d1d5db"/>')
    for layer in layers:
        yt, yb = y(float(layer["top_ft"])), y(float(layer["bottom_ft"]))
        col = _soil_color(layer["name"])
        parts.append(f'<rect x="{sx}" y="{yt}" width="{sw}" height="{max(yb-yt, 2)}" fill="{col}" stroke="#8a8a8a"/>')
        label_y = (yt + yb) / 2
        parts.append(_svg_text(sx + 8, label_y - 2, f'{layer["name"]}', 12, "bold"))
        parts.append(_svg_text(sx + 8, label_y + 14, f'{layer["top_ft"]:.1f} to {layer["bottom_ft"]:.1f} ft', 11))
    parts.append(_svg_text(sx, top - 10, "Soil / Rock Layers", 13, "bold"))

    # Ground line and depth axis
    parts.append(f'<line x1="55" y1="{top}" x2="650" y2="{top}" stroke="#111827" stroke-width="2"/>')
    parts.append(_svg_text(55, top - 8, "Existing grade / top of pile", 12, "bold"))
    axis_x = 665
    parts.append(f'<line x1="{axis_x}" y1="{top}" x2="{axis_x}" y2="{bottom}" stroke="#374151"/>')
    tick_step = 5 if max_depth <= 60 else 10
    d = 0
    while d <= max_depth + 0.001:
        yy = y(d)
        parts.append(f'<line x1="{axis_x-5}" y1="{yy}" x2="{axis_x+5}" y2="{yy}" stroke="#374151"/>')
        parts.append(_svg_text(axis_x + 10, yy + 4, f'{d:.0f} ft', 10))
        d += tick_step

    # Groundwater
    if groundwater_ft is not None and groundwater_ft >= 0 and groundwater_ft <= max_depth:
        yg = y(groundwater_ft)
        parts.append(f'<line x1="55" y1="{yg}" x2="635" y2="{yg}" stroke="#2563eb" stroke-width="2" stroke-dasharray="6 4"/>')
        parts.append(_svg_text(57, yg - 5, f'Groundwater ~ {groundwater_ft:.1f} ft', 11, "bold"))

    # Pile drawing panel
    px = 210
    pile_w = max(22, min(60, bond_diameter_in * 4.0))
    # Drill/grout column
    parts.append(f'<rect x="{px-pile_w/2}" y="{top}" width="{pile_w}" height="{y(pile_tip)-top}" fill="#dbeafe" stroke="#1d4ed8" stroke-width="2" rx="4"/>')
    # Casing
    casing_w = pile_w * 0.80
    parts.append(f'<rect x="{px-casing_w/2}" y="{top}" width="{casing_w}" height="{max(y(casing_depth)-top,0)}" fill="none" stroke="#111827" stroke-width="6"/>')
    # Bar
    parts.append(f'<line x1="{px}" y1="{top}" x2="{px}" y2="{y(pile_tip)}" stroke="#7c2d12" stroke-width="8"/>')
    # Bond zone highlight
    if bond_bottom > bond_top:
        parts.append(f'<rect x="{px-pile_w/2-8}" y="{y(bond_top)}" width="{pile_w+16}" height="{y(bond_bottom)-y(bond_top)}" fill="none" stroke="#16a34a" stroke-width="4" stroke-dasharray="8 5"/>')
        parts.append(_svg_text(px + pile_w/2 + 16, y(bond_top) + 18, "Bond / socket zone", 12, "bold"))
        parts.append(_svg_text(px + pile_w/2 + 16, y(bond_top) + 34, f'{bond_length_ft:.1f} ft', 11))
    # Pile cap
    parts.append(f'<rect x="{px-80}" y="{top-28}" width="160" height="22" fill="#e5e7eb" stroke="#6b7280"/>')
    parts.append(_svg_text(px, top - 13, "Pile cap", 11, "bold", "middle"))

    # Dimension lines
    dim_x = 95
    parts.append(f'<line x1="{dim_x}" y1="{top}" x2="{dim_x}" y2="{y(pile_tip)}" stroke="#111827"/>')
    parts.append(f'<line x1="{dim_x-8}" y1="{top}" x2="{dim_x+8}" y2="{top}" stroke="#111827"/>')
    parts.append(f'<line x1="{dim_x-8}" y1="{y(pile_tip)}" x2="{dim_x+8}" y2="{y(pile_tip)}" stroke="#111827"/>')
    parts.append(_svg_text(dim_x - 12, (top + y(pile_tip))/2, f'Total length {total_length_ft:.1f} ft', 12, "bold", "end"))

    parts.append(_svg_text(30, 590, f'Casing: {casing_label}', 11))
    parts.append(_svg_text(30, 606, f'Reinforcement: {bar_label}', 11))
    parts.append(_svg_text(395, 590, f'Bond diameter: {bond_diameter_in:.1f} in', 11))
    parts.append(_svg_text(395, 606, f'Cased length: {cased_length_ft:.1f} ft | Bond length: {bond_length_ft:.1f} ft', 11))
    parts.append('</svg>')
    return "".join(parts)


def make_bar(row: pd.Series, custom: dict | None = None) -> Bar:
    if custom:
        return Bar(
            name="Custom Bar",
            area_in2=float(custom["area_in2"]),
            od_in=float(custom["od_in"]),
            id_in=float(custom["id_in"]),
            fy_ksi=float(custom["fy_ksi"]),
            source="User input",
        )
    return Bar(
        name=str(row["name"]),
        area_in2=float(row["area_in2"]),
        od_in=float(row["od_in"]),
        id_in=float(row["id_in"]),
        fy_ksi=float(row["fy_ksi"]),
        source=str(row.get("source", "")),
    )


def make_casing(row: pd.Series, custom: dict | None = None) -> Casing | None:
    if custom:
        return Casing(
            name="Custom Casing",
            od_in=float(custom["od_in"]),
            wall_in=float(custom["wall_in"]),
            fy_ksi=float(custom["fy_ksi"]),
            source="User input",
        )
    if float(row["od_in"]) <= 0:
        return None
    return Casing(
        name=str(row["name"]),
        od_in=float(row["od_in"]),
        wall_in=float(row["wall_in"]),
        fy_ksi=float(row["fy_ksi"]),
        source=str(row.get("source", "")),
    )


bars_df, casings_df, bonds_df = load_data()

st.title("Micropile ASD Design Calculator")
st.caption("General preliminary axial compression/tension, casing/bar/grout, and grout-to-ground bond checks based on FHWA NHI-05-039 workflow.")

with st.sidebar:
    st.header("Quick Start")
    template = st.selectbox(
        "Template",
        ["Custom", "Generic 75 kip compression example", "Generic 150 kip compression example"],
        index=0,
        help="Templates only fill common starting values. Revise all inputs for the actual design criteria.",
    )

    if template == "Generic 75 kip compression example":
        default_comp = 75.0
        default_tension = 0.0
        default_casing_name = "7.625 in OD x 0.500 in wall"
        default_bar_name = "No.18 Grade 60 Rebar"
        default_dia = 6.0
        default_len = 6.0
        default_fc = 5000.0
        default_min_socket = 0.0
        default_corrosion = 0.0
    elif template == "Generic 150 kip compression example":
        default_comp = 150.0
        default_tension = 0.0
        default_casing_name = "9.625 in OD x 0.500 in wall"
        default_bar_name = "No.20 Grade 60 Rebar"
        default_dia = 8.0
        default_len = 8.0
        default_fc = 5000.0
        default_min_socket = 0.0
        default_corrosion = 0.0
    else:
        default_comp = 150.0
        default_tension = 0.0
        default_casing_name = "9.625 in OD x 0.500 in wall"
        default_bar_name = "SSSI HC10375B / TB103/75"
        default_dia = 8.0
        default_len = 8.0
        default_fc = 5000.0
        default_min_socket = 0.0
        default_corrosion = 0.0

    st.header("Design Inputs")
    pile_configuration = st.selectbox(
        "Pile configuration",
        ["Casing + hollow/core bar", "Hollow bar only / bar only", "Casing only - casing extends full bond"],
        index=0,
    )
    required_compression_kips = st.number_input("Required allowable compression per pile (kips)", min_value=0.0, value=default_comp, step=5.0)
    required_tension_kips = st.number_input("Required allowable uplift/tension per pile (kips)", min_value=0.0, value=default_tension, step=5.0)
    grout_fc_psi = st.number_input("Grout/concrete f'c (psi)", min_value=1000.0, value=default_fc, step=500.0)

    st.header("Reinforcement")
    bar_names = bars_df["name"].tolist()
    bar_index = bar_names.index(default_bar_name) if default_bar_name in bar_names else 0
    selected_bar_name = st.selectbox("Select bar/reinforcement", bar_names, index=bar_index)
    selected_bar_row = bars_df[bars_df["name"] == selected_bar_name].iloc[0]

    custom_bar = None
    if selected_bar_name == "Custom Bar":
        c1, c2 = st.columns(2)
        custom_bar = {
            "area_in2": c1.number_input("Custom bar area (in²)", min_value=0.0, value=4.90, step=0.10),
            "fy_ksi": c2.number_input("Custom bar Fy (ksi)", min_value=0.0, value=60.0, step=5.0),
            "od_in": c1.number_input("Custom bar OD (in)", min_value=0.0, value=2.50, step=0.10),
            "id_in": c2.number_input("Custom bar ID (in)", min_value=0.0, value=0.0, step=0.10),
        }
    bar = make_bar(selected_bar_row, custom_bar)

    st.header("Casing")
    casing_names = casings_df["name"].tolist()
    casing_index = casing_names.index(default_casing_name) if default_casing_name in casing_names else 0
    if "Hollow bar only" in pile_configuration:
        casing_index = casing_names.index("No casing")
    selected_casing_name = st.selectbox("Select casing", casing_names, index=casing_index)
    selected_casing_row = casings_df[casings_df["name"] == selected_casing_name].iloc[0]

    custom_casing = None
    if selected_casing_name == "Custom Casing":
        c1, c2 = st.columns(2)
        custom_casing = {
            "od_in": c1.number_input("Custom casing OD (in)", min_value=0.0, value=9.625, step=0.125),
            "wall_in": c2.number_input("Custom casing wall (in)", min_value=0.0, value=0.500, step=0.025),
            "fy_ksi": c1.number_input("Custom casing Fy (ksi)", min_value=0.0, value=50.0, step=5.0),
        }
    casing = make_casing(selected_casing_row, custom_casing)
    corrosion_allowance_in = st.number_input("Casing corrosion wall deduction (in)", min_value=0.0, value=default_corrosion, step=0.015625, format="%.5f")
    count_casing_in_tension = st.checkbox("Count casing in tension capacity", value=False, help="Keep off unless casing threaded joints/couplers are verified for tension.")
    casing_extends_full_bond = "Casing only" in pile_configuration or st.checkbox("Casing extends through full bond zone", value=False)

    st.header("Bond / Socket")
    bond_diameter_in = st.number_input("Bond/socket diameter (in)", min_value=0.1, value=default_dia, step=0.5)
    provided_bond_length_ft = st.number_input("Provided bond/socket length (ft)", min_value=0.0, value=default_len, step=0.5)
    min_socket_ft = st.number_input("Minimum specified socket/bond length (ft)", min_value=0.0, value=default_min_socket, step=0.5)
    round_socket_up_to_ft = st.selectbox("Round required length up to", [0.5, 1.0, 2.0, 5.0], index=0)

    bond_mode = st.radio("Bond basis", ["FHWA Table 5-3 ultimate bond / FS", "User-specified allowable bond values"], index=0)
    use_user_allowable_bond = bond_mode == "User-specified allowable bond values"

    if use_user_allowable_bond:
        allowable_bond_comp_psi = st.number_input("Allowable compression bond/peripheral shear (psi)", min_value=0.0, value=75.0, step=5.0)
        allowable_bond_tension_psi = st.number_input("Allowable tension/uplift bond/peripheral shear (psi)", min_value=0.0, value=25.0, step=5.0)
        alpha_ultimate_comp_psi = allowable_bond_comp_psi
        alpha_ultimate_tension_psi = allowable_bond_tension_psi
        fs_comp = 1.0
        fs_tension = 1.0
    else:
        soil_options = sorted(bonds_df["soil_rock_description"].unique().tolist())
        selected_soil = st.selectbox("Soil/rock description", soil_options, index=0)
        possible_types = bonds_df[bonds_df["soil_rock_description"] == selected_soil]["grout_type"].tolist()
        grout_type = st.selectbox("FHWA grout type", possible_types, index=0)
        bond_row = bonds_df[(bonds_df["soil_rock_description"] == selected_soil) & (bonds_df["grout_type"] == grout_type)].iloc[0]
        alpha_choice = st.radio("Use which FHWA αbond value?", ["low", "mid", "high"], index=1, horizontal=True)
        alpha_ultimate_comp_psi = float(bond_row[f"alpha_{alpha_choice}_psi"])
        alpha_ultimate_tension_psi = alpha_ultimate_comp_psi
        fs_comp = st.number_input("FS on compression bond", min_value=1.0, value=2.0, step=0.25)
        fs_tension = st.number_input("FS on tension bond", min_value=1.0, value=2.0, step=0.25)
        allowable_bond_comp_psi = alpha_ultimate_comp_psi / fs_comp
        allowable_bond_tension_psi = alpha_ultimate_tension_psi / fs_tension

    st.header("Drawing / Soil Profile")
    cased_length_ft = st.number_input("Cased length shown on drawing (ft)", min_value=0.0, value=max(0.0, default_len), step=1.0)
    total_length_ft = st.number_input("Total pile length shown on drawing (ft)", min_value=0.0, value=max(default_len, default_len + cased_length_ft), step=1.0)
    show_groundwater = st.checkbox("Show groundwater line", value=False)
    groundwater_ft = None
    if show_groundwater:
        groundwater_ft = st.number_input("Groundwater depth below grade (ft)", min_value=0.0, value=10.0, step=0.5)

    number_of_layers = st.number_input("Number of soil/rock layers to show", min_value=1, max_value=8, value=3, step=1)
    soil_layers = []
    previous_bottom = 0.0
    default_layer_names = ["Fill", "Soil / overburden", "Bond stratum / rock"]
    for i in range(int(number_of_layers)):
        st.markdown(f"**Layer {i + 1}**")
        c1, c2, c3 = st.columns([1.3, 1, 1])
        default_name = default_layer_names[i] if i < len(default_layer_names) else f"Layer {i + 1}"
        layer_name = c1.text_input(f"Layer {i + 1} name", value=default_name, key=f"layer_name_{i}")
        top_ft = c2.number_input(f"Top ft L{i+1}", min_value=0.0, value=float(previous_bottom), step=0.5, key=f"layer_top_{i}")
        bottom_default = max(top_ft + 5.0, total_length_ft if i == int(number_of_layers) - 1 else top_ft + 10.0)
        bottom_ft = c3.number_input(f"Bottom ft L{i+1}", min_value=top_ft + 0.1, value=float(bottom_default), step=0.5, key=f"layer_bottom_{i}")
        soil_layers.append({"name": layer_name, "top_ft": float(top_ft), "bottom_ft": float(bottom_ft)})
        previous_bottom = float(bottom_ft)

    st.header("Testing / Load Factor for Bond Check")
    proof_factor_comp = st.number_input("Compression test/proof factor for bond length check", min_value=1.0, value=1.0, step=0.1)
    proof_factor_tension = st.number_input("Tension test/proof factor for bond length check", min_value=1.0, value=1.0, step=0.1)

inputs = MicropileInputs(
    pile_configuration=pile_configuration,
    required_compression_kips=required_compression_kips,
    required_tension_kips=required_tension_kips,
    bar=bar,
    casing=casing,
    grout_fc_psi=grout_fc_psi,
    bond_diameter_in=bond_diameter_in,
    provided_bond_length_ft=provided_bond_length_ft,
    corrosion_allowance_in=corrosion_allowance_in,
    use_user_allowable_bond=use_user_allowable_bond,
    alpha_ultimate_comp_psi=alpha_ultimate_comp_psi,
    alpha_ultimate_tension_psi=alpha_ultimate_tension_psi,
    fs_bond_comp=fs_comp,
    fs_bond_tension=fs_tension,
    allowable_bond_comp_psi=allowable_bond_comp_psi,
    allowable_bond_tension_psi=allowable_bond_tension_psi,
    count_casing_in_tension=count_casing_in_tension,
    casing_extends_full_bond=casing_extends_full_bond,
    proof_factor_comp=proof_factor_comp,
    proof_factor_tension=proof_factor_tension,
    min_socket_ft=min_socket_ft,
    round_socket_up_to_ft=float(round_socket_up_to_ft),
)

results = calculate(inputs)
summary = flat_summary(results)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Final Status", summary["Final OK"])
col2.metric("Required Comp.", f"{required_compression_kips:.0f} kips")
col3.metric("Provided Comp. Bond", f"{summary['Provided compression bond capacity (kips)']:.1f} kips")
col4.metric("Req'd Bond Length", f"{summary['Governing required bond length rounded (ft)']} ft")


st.subheader("Schematic Drawing")
try:
    drawing_svg = make_profile_svg(
        soil_layers,
        total_length_ft=total_length_ft,
        cased_length_ft=cased_length_ft,
        bond_length_ft=provided_bond_length_ft,
        bond_diameter_in=bond_diameter_in,
        casing_label=casing.name if casing else "No casing",
        bar_label=bar.name,
        groundwater_ft=groundwater_ft,
    )
    st.markdown(drawing_svg, unsafe_allow_html=True)
except Exception as exc:
    st.info(f"Drawing could not be generated from the current inputs: {exc}")

st.subheader("Summary Checks")
summary_rows = [
    ["Compression structural", status_badge(results["checks"]["compression_structural_ok"]), f"{results['structural']['controlling_compression_capacity_kips']:.1f} kips", f">= {required_compression_kips:.1f} kips"],
    ["Tension structural", status_badge(results["checks"]["tension_structural_ok"]), f"{results['structural']['controlling_tension_capacity_kips']:.1f} kips", f">= {required_tension_kips:.1f} kips"],
    ["Compression bond", status_badge(results["checks"]["compression_geotechnical_ok"]), f"{results['geotechnical']['provided_compression_bond_capacity_kips']:.1f} kips", f">= {required_compression_kips:.1f} kips"],
    ["Tension bond", status_badge(results["checks"]["tension_geotechnical_ok"]), f"{results['geotechnical']['provided_tension_bond_capacity_kips']:.1f} kips", f">= {required_tension_kips:.1f} kips"],
    ["Provided bond/socket length", status_badge(results["checks"]["provided_length_ok"]), f"{provided_bond_length_ft:.1f} ft", f">= {results['geotechnical']['required_length_governing_ft']:.2f} ft"],
]
render_table(pd.DataFrame(summary_rows, columns=["Check", "Status", "Calculated / Provided", "Requirement"]))

left, right = st.columns(2)
with left:
    st.subheader("Structural Capacities")
    structural_rows = [
        ["Cased compression", results["structural"]["cased_compression"]["capacity_kips"], "FHWA Eq. 5-1"],
        ["Cased tension", results["structural"]["cased_tension"]["capacity_kips"], "FHWA Eq. 5-2"],
        ["Uncased compression", results["structural"]["uncased_compression"]["capacity_kips"], "FHWA Eq. 5-7"],
        ["Uncased tension", results["structural"]["uncased_tension"]["capacity_kips"], "FHWA Eq. 5-8"],
        ["Controlling compression", results["structural"]["controlling_compression_capacity_kips"], results["structural"]["controlling_compression_section"]],
        ["Controlling tension", results["structural"]["controlling_tension_capacity_kips"], results["structural"]["controlling_tension_section"]],
    ]
    df_struct = pd.DataFrame(structural_rows, columns=["Item", "Capacity (kips)", "Basis"])
    df_struct["Capacity (kips)"] = df_struct["Capacity (kips)"].map(lambda x: round(x, 1))
    render_table(df_struct)

with right:
    st.subheader("Bond / Socket")
    bond_rows = [
        ["Allowable compression bond", results["bond"]["compression_allowable_psi"], "psi"],
        ["Allowable tension/uplift bond", results["bond"]["tension_allowable_psi"], "psi"],
        ["Provided compression bond capacity", results["geotechnical"]["provided_compression_bond_capacity_kips"], "kips"],
        ["Provided tension bond capacity", results["geotechnical"]["provided_tension_bond_capacity_kips"], "kips"],
        ["Required length - compression", results["geotechnical"]["required_length_compression_ft"], "ft"],
        ["Required length - tension", results["geotechnical"]["required_length_tension_ft"], "ft"],
        ["Governing required length rounded", results["geotechnical"]["required_length_governing_rounded_ft"], "ft"],
    ]
    df_bond = pd.DataFrame(bond_rows, columns=["Item", "Value", "Unit"])
    df_bond["Value"] = df_bond["Value"].map(lambda x: round(x, 2) if isinstance(x, (float, int)) else x)
    render_table(df_bond)

if results["warnings"]:
    st.warning("\n".join([f"• {w}" for w in results["warnings"]]))

with st.expander("Detailed assumptions and equations"):
    st.markdown(
        """
**Key equations implemented**

- Cased compression: `Pc_allow = 0.4 f'c Agrout + 0.47 Fy_steel (Abar + Acasing)`
- Cased tension: `Pt_allow = 0.55 Fy_steel (Abar + Acasing)`; casing may be ignored in tension unless verified.
- Uncased compression: `Pc_allow = 0.4 f'c Agrout + 0.47 Fy_bar Abar`
- Uncased tension: `Pt_allow = 0.55 Fy_bar Abar`
- Bond capacity: `P_allow = π × Db × Lb × α_allow`
- If using FHWA Table 5-3, `α_allow = α_ultimate / FS`.
- If using user-specified allowable bond values, the entered bond values are used directly without another FS.

**Not included in this MVP**: lateral load/bending with p-y analysis, buckling, group settlement, group block failure, pile cap connection design, eccentricity design, downdrag, seismic, detailed corrosion classification, and load test acceptance criteria.
        """
    )

st.subheader("Selected Materials")
mat_rows = [
    ["Bar", bar.name, bar.area_in2, bar.fy_ksi, bar.source],
    ["Casing", casing.name if casing else "No casing", results["structural"]["cased_compression"].get("area_in2", 0.0), casing.fy_ksi if casing else 0.0, casing.source if casing else ""],
]
render_table(pd.DataFrame(mat_rows, columns=["Item", "Selection", "Area (in²)", "Fy (ksi)", "Source"]))

report = {
    "summary": summary,
    "results": results,
}
report_json = json.dumps(report, indent=2)
st.download_button("Download JSON calculation report", report_json, file_name="micropile_calculation_report.json", mime="application/json")

report_txt = "Micropile ASD Design Calculator Report\n\n" + "\n".join([f"{k}: {v}" for k, v in summary.items()]) + "\n\nWarnings:\n" + "\n".join(results["warnings"] or ["None"])
st.download_button("Download text summary", report_txt, file_name="micropile_calculation_summary.txt", mime="text/plain")

st.caption("Use for preliminary estimating/design checks only. Final calculations require engineer review and applicable specifications.")
