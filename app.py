from __future__ import annotations

import json
import os
import hmac
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from micropile_calc_engine import (
    Bar,
    Casing,
    MicropileInputs,
    calculate,
    flat_summary,
    bond_capacity_kips,
)

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"

st.set_page_config(page_title="Micropile ASD Design Calculator", layout="wide")


def check_password() -> bool:
    """Optional password protection for cloud deployment.

    Set environment variable APP_PASSWORD in your cloud host. If APP_PASSWORD is not set,
    the app is public.
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


@st.cache_data
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
.micropile-table { width: 100%; border-collapse: collapse; font-size: 0.93rem; }
.micropile-table th { text-align: left; background: #f4f6f8; padding: 8px; border: 1px solid #ddd; }
.micropile-table td { padding: 8px; border: 1px solid #ddd; vertical-align: top; }
.micropile-table tr:nth-child(even) { background: #fafafa; }
.small-note { color: #4b5563; font-size: 0.90rem; }
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


def make_profile_svg(
    layers: list[dict[str, Any]],
    total_length_ft: float,
    cased_length_ft: float,
    effective_bond_length_ft: float,
    required_bond_length_ft: float,
    bond_diameter_in: float,
    casing_label: str,
    bar_label: str,
    bond_layer_index: int | None,
    groundwater_ft: float | None = None,
) -> str:
    """Schematic micropile + soil profile SVG. Not to scale horizontally; vertical depths are proportional."""
    max_depth = max([float(layer["bottom_ft"]) for layer in layers] + [total_length_ft, cased_length_ft + effective_bond_length_ft, 10.0])
    width, height = 820, 650
    top, bottom = 65, 590
    scale = (bottom - top) / max_depth

    def y(depth_ft: float) -> float:
        return top + depth_ft * scale

    casing_depth = min(max(cased_length_ft, 0), max_depth)
    pile_tip = min(max(total_length_ft, cased_length_ft + effective_bond_length_ft), max_depth)
    bond_top = max(cased_length_ft, 0)
    bond_bottom = min(bond_top + max(effective_bond_length_ft, 0), pile_tip)
    required_bond_bottom = min(bond_top + max(required_bond_length_ft, 0), max_depth)

    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="auto" xmlns="http://www.w3.org/2000/svg">']
    parts.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="white"/>')
    parts.append(_svg_text(20, 30, "Micropile and Soil Profile Schematic", 18, "bold"))
    parts.append(_svg_text(20, 49, "Bond layer is automatically selected from the layer at the casing-end depth", 11))

    # Soil profile panel
    sx, sw = 430, 245
    parts.append('<rect x="425" y="60" width="265" height="540" fill="#f9fafb" stroke="#d1d5db"/>')
    for idx, layer in enumerate(layers):
        yt, yb = y(float(layer["top_ft"])), y(float(layer["bottom_ft"]))
        col = _soil_color(layer["soil_type"])
        stroke = "#16a34a" if idx == bond_layer_index else "#8a8a8a"
        stroke_width = 4 if idx == bond_layer_index else 1
        parts.append(f'<rect x="{sx}" y="{yt}" width="{sw}" height="{max(yb-yt, 2)}" fill="{col}" stroke="{stroke}" stroke-width="{stroke_width}"/>')
        label_y = (yt + yb) / 2
        parts.append(_svg_text(sx + 8, label_y - 4, f'L{idx + 1}: {layer["soil_type"]}', 11, "bold"))
        parts.append(_svg_text(sx + 8, label_y + 12, f'{layer["top_ft"]:.1f} to {layer["bottom_ft"]:.1f} ft', 10))
        parts.append(_svg_text(sx + 8, label_y + 27, f'αallow C/T: {layer["allowable_comp_psi"]:.1f}/{layer["allowable_tension_psi"]:.1f} psi', 10))
    parts.append(_svg_text(sx, top - 12, "Soil / Rock Layers", 13, "bold"))

    # Ground line and depth axis
    parts.append(f'<line x1="55" y1="{top}" x2="710" y2="{top}" stroke="#111827" stroke-width="2"/>')
    parts.append(_svg_text(55, top - 8, "Existing grade / top of pile", 12, "bold"))
    axis_x = 730
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
        parts.append(f'<line x1="55" y1="{yg}" x2="690" y2="{yg}" stroke="#2563eb" stroke-width="2" stroke-dasharray="6 4"/>')
        parts.append(_svg_text(57, yg - 5, f'Groundwater ~ {groundwater_ft:.1f} ft', 11, "bold"))

    # Pile drawing panel
    px = 225
    pile_w = max(22, min(65, bond_diameter_in * 4.0))
    parts.append(f'<rect x="{px-pile_w/2}" y="{top}" width="{pile_w}" height="{max(y(pile_tip)-top,0)}" fill="#dbeafe" stroke="#1d4ed8" stroke-width="2" rx="4"/>')
    casing_w = pile_w * 0.80
    parts.append(f'<rect x="{px-casing_w/2}" y="{top}" width="{casing_w}" height="{max(y(casing_depth)-top,0)}" fill="none" stroke="#111827" stroke-width="6"/>')
    parts.append(f'<line x1="{px}" y1="{top}" x2="{px}" y2="{y(pile_tip)}" stroke="#7c2d12" stroke-width="8"/>')

    # Casing end line
    yce = y(casing_depth)
    parts.append(f'<line x1="{px-80}" y1="{yce}" x2="{px+170}" y2="{yce}" stroke="#111827" stroke-dasharray="5 4"/>')
    parts.append(_svg_text(px + 90, yce - 6, f'Casing end / bond start = {cased_length_ft:.1f} ft', 11, "bold"))

    # Bond zone highlight
    if bond_bottom > bond_top:
        parts.append(f'<rect x="{px-pile_w/2-8}" y="{y(bond_top)}" width="{pile_w+16}" height="{y(bond_bottom)-y(bond_top)}" fill="none" stroke="#16a34a" stroke-width="4" stroke-dasharray="8 5"/>')
        parts.append(_svg_text(px + pile_w/2 + 18, y(bond_top) + 18, "Used bond length", 12, "bold"))
        parts.append(_svg_text(px + pile_w/2 + 18, y(bond_top) + 34, f'{effective_bond_length_ft:.1f} ft in selected layer', 11))

    if required_bond_bottom > bond_top:
        parts.append(f'<line x1="{px-pile_w/2-22}" y1="{y(required_bond_bottom)}" x2="{px+pile_w/2+22}" y2="{y(required_bond_bottom)}" stroke="#dc2626" stroke-width="3"/>')
        parts.append(_svg_text(px + pile_w/2 + 18, y(required_bond_bottom) + 4, f'Required bond length ~ {required_bond_length_ft:.1f} ft', 10, "bold"))

    # Pile cap
    parts.append(f'<rect x="{px-80}" y="{top-28}" width="160" height="22" fill="#e5e7eb" stroke="#6b7280"/>')
    parts.append(_svg_text(px, top - 13, "Pile cap", 11, "bold", "middle"))

    # Dimension line
    dim_x = 95
    parts.append(f'<line x1="{dim_x}" y1="{top}" x2="{dim_x}" y2="{y(pile_tip)}" stroke="#111827"/>')
    parts.append(f'<line x1="{dim_x-8}" y1="{top}" x2="{dim_x+8}" y2="{top}" stroke="#111827"/>')
    parts.append(f'<line x1="{dim_x-8}" y1="{y(pile_tip)}" x2="{dim_x+8}" y2="{y(pile_tip)}" stroke="#111827"/>')
    parts.append(_svg_text(dim_x - 12, (top + y(pile_tip)) / 2, f'Total length {total_length_ft:.1f} ft', 12, "bold", "end"))

    parts.append(_svg_text(25, 618, f'Casing: {casing_label}', 11))
    parts.append(_svg_text(25, 634, f'Reinforcement: {bar_label}', 11))
    parts.append(_svg_text(425, 618, f'Bond diameter: {bond_diameter_in:.1f} in', 11))
    parts.append(_svg_text(425, 634, f'Calculation uses ONLY the selected bond layer below casing end.', 11, "bold"))
    parts.append('</svg>')
    return "".join(parts)


def make_bar(row: pd.Series, custom: dict[str, float] | None = None) -> Bar:
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


def make_casing(row: pd.Series, custom: dict[str, float] | None = None) -> Casing | None:
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


def get_bond_row(bonds_df: pd.DataFrame, soil_type: str, grout_type: str) -> pd.Series:
    rows = bonds_df[(bonds_df["soil_rock_description"] == soil_type) & (bonds_df["grout_type"] == grout_type)]
    if rows.empty:
        rows = bonds_df[bonds_df["soil_rock_description"] == soil_type]
    return rows.iloc[0]


def build_layer(
    index: int,
    top_ft: float,
    bottom_ft: float,
    soil_type: str,
    grout_type: str,
    alpha_choice: str,
    fs_comp: float,
    fs_tension: float,
    custom_allowable: bool,
    custom_comp_psi: float,
    custom_tension_psi: float,
    bonds_df: pd.DataFrame,
    bond_diameter_in: float,
) -> dict[str, Any]:
    row = get_bond_row(bonds_df, soil_type, grout_type)
    alpha = float(row[f"alpha_{alpha_choice}_psi"])
    thickness = max(bottom_ft - top_ft, 0.0)
    if custom_allowable:
        allow_comp = custom_comp_psi
        allow_tension = custom_tension_psi
        basis = "User allowable bond"
        alpha_comp = custom_comp_psi
        alpha_tension = custom_tension_psi
        fs_comp_used = 1.0
        fs_tension_used = 1.0
    else:
        alpha_comp = alpha
        alpha_tension = alpha
        fs_comp_used = fs_comp
        fs_tension_used = fs_tension
        allow_comp = alpha_comp / fs_comp if fs_comp > 0 else 0.0
        allow_tension = alpha_tension / fs_tension if fs_tension > 0 else 0.0
        basis = "FHWA ultimate bond / FS"

    return {
        "index": index,
        "top_ft": float(top_ft),
        "bottom_ft": float(bottom_ft),
        "thickness_ft": float(thickness),
        "soil_type": soil_type,
        "grout_type": grout_type,
        "alpha_choice": alpha_choice,
        "alpha_comp_psi": float(alpha_comp),
        "alpha_tension_psi": float(alpha_tension),
        "fs_comp": float(fs_comp_used),
        "fs_tension": float(fs_tension_used),
        "allowable_comp_psi": float(allow_comp),
        "allowable_tension_psi": float(allow_tension),
        "basis": basis,
        "capacity_comp_full_layer_kips": bond_capacity_kips(bond_diameter_in, thickness, allow_comp),
        "capacity_tension_full_layer_kips": bond_capacity_kips(bond_diameter_in, thickness, allow_tension),
        "source": str(row.get("source", "")),
    }


def find_bond_layer(layers: list[dict[str, Any]], casing_end_ft: float) -> tuple[int | None, dict[str, Any] | None]:
    if not layers:
        return None, None
    sorted_layers = sorted(layers, key=lambda item: (item["top_ft"], item["bottom_ft"]))
    # Prefer the layer starting at the casing-end depth if the casing ends exactly at a boundary.
    for layer in sorted_layers:
        if abs(layer["top_ft"] - casing_end_ft) < 1e-6:
            return int(layer["index"]), layer
    for layer in sorted_layers:
        if layer["top_ft"] <= casing_end_ft < layer["bottom_ft"]:
            return int(layer["index"]), layer
    # Fallback: if casing end is above first layer, use the first layer. If below last layer, no layer.
    if casing_end_ft < sorted_layers[0]["top_ft"]:
        return int(sorted_layers[0]["index"]), sorted_layers[0]
    return None, None


bars_df, casings_df, bonds_df = load_data()

st.title("Micropile ASD Design Calculator")
st.caption(
    "General preliminary axial compression/tension, casing/bar/grout, and grout-to-ground bond checks based on the FHWA NHI-05-039 workflow."
)

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
        default_bond_len = 6.0
        default_cased_len = 20.0
        default_fc = 5000.0
        default_min_socket = 0.0
        default_corrosion = 0.0
    elif template == "Generic 150 kip compression example":
        default_comp = 150.0
        default_tension = 0.0
        default_casing_name = "9.625 in OD x 0.500 in wall"
        default_bar_name = "No.20 Grade 60 Rebar"
        default_dia = 8.0
        default_bond_len = 8.0
        default_cased_len = 20.0
        default_fc = 5000.0
        default_min_socket = 0.0
        default_corrosion = 0.0
    else:
        default_comp = 150.0
        default_tension = 0.0
        default_casing_name = "9.625 in OD x 0.500 in wall"
        default_bar_name = "SSSI HC10375B / TB103/75"
        default_dia = 8.0
        default_bond_len = 8.0
        default_cased_len = 20.0
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
    casing_end_ft = st.number_input(
        "Casing end depth / cased length (ft)",
        min_value=0.0,
        value=default_cased_len,
        step=0.5,
        help="The bond layer is selected automatically based on this depth. No separate bond-soil selection is used.",
    )
    count_casing_in_tension = st.checkbox("Count casing in tension capacity", value=False, help="Keep off unless casing threaded joints/couplers are verified for tension.")
    casing_extends_full_bond = "Casing only" in pile_configuration or st.checkbox("Casing extends through full bond zone", value=False)

    st.header("Bond Length / Testing")
    bond_diameter_in = st.number_input("Bond/socket diameter (in)", min_value=0.1, value=default_dia, step=0.5)
    proposed_bond_length_input_ft = st.number_input(
        "Proposed bond/socket length below casing end (ft)",
        min_value=0.0,
        value=default_bond_len,
        step=0.5,
        help="This length is applied only within the layer at the casing-end depth. It is not allowed to continue into lower layers in this version.",
    )
    min_socket_ft = st.number_input("Minimum specified socket/bond length (ft)", min_value=0.0, value=default_min_socket, step=0.5)
    round_socket_up_to_ft = st.selectbox("Round required length up to", [0.5, 1.0, 2.0, 5.0], index=0)
    proof_factor_comp = st.number_input("Compression test/proof factor for bond length check", min_value=1.0, value=1.0, step=0.1)
    proof_factor_tension = st.number_input("Tension test/proof factor for bond length check", min_value=1.0, value=1.0, step=0.1)

    st.header("Drawing")
    show_groundwater = st.checkbox("Show groundwater line", value=False)
    groundwater_ft = None
    if show_groundwater:
        groundwater_ft = st.number_input("Groundwater depth below grade (ft)", min_value=0.0, value=10.0, step=0.5)


st.subheader("Stratigraphy / Bond Layer Selection")
st.markdown(
    "<div class='small-note'>Define the subsurface layers first. Each layer is pulled from the FHWA bond table with grout type, selected αbond value, and FS. The calculation automatically selects the bond layer at the casing-end depth and uses only that layer for required/provided bond length.</div>",
    unsafe_allow_html=True,
)

soil_options = sorted(bonds_df["soil_rock_description"].unique().tolist())
default_profile = [
    ("Fill / unsuitable overburden", 0.0, 8.0, soil_options[0]),
    ("Soil / overburden", 8.0, casing_end_ft, "Sand w/silt/gravel - medium to very dense" if "Sand w/silt/gravel - medium to very dense" in soil_options else soil_options[0]),
    ("Bond stratum", casing_end_ft, casing_end_ft + max(proposed_bond_length_input_ft, 10.0), "Slate & hard shale - fresh/moderate fracture" if "Slate & hard shale - fresh/moderate fracture" in soil_options else soil_options[-1]),
]

number_of_layers = st.number_input("Number of soil/rock layers", min_value=1, max_value=10, value=3, step=1)
soil_layers: list[dict[str, Any]] = []
previous_bottom = 0.0

for i in range(int(number_of_layers)):
    with st.expander(f"Layer {i + 1}", expanded=(i < 3)):
        default_label, default_top, default_bottom, default_soil = default_profile[i] if i < len(default_profile) else (f"Layer {i + 1}", previous_bottom, previous_bottom + 10.0, soil_options[0])
        c1, c2, c3 = st.columns([1.4, 1, 1])
        layer_label = c1.text_input("Layer label", value=default_label, key=f"layer_label_{i}")
        top_default = previous_bottom if i > 0 else default_top
        top_ft = c2.number_input("Top depth (ft)", min_value=0.0, value=float(top_default), step=0.5, key=f"layer_top_{i}")
        bottom_default = max(top_ft + 0.5, default_bottom)
        bottom_ft = c3.number_input("Bottom depth (ft)", min_value=top_ft + 0.1, value=float(bottom_default), step=0.5, key=f"layer_bottom_{i}")

        c4, c5, c6 = st.columns([2, 1, 1])
        default_soil_index = soil_options.index(default_soil) if default_soil in soil_options else 0
        soil_type = c4.selectbox("Soil / rock type from bond table", soil_options, index=default_soil_index, key=f"soil_type_{i}")
        possible_grout_types = bonds_df[bonds_df["soil_rock_description"] == soil_type]["grout_type"].tolist()
        grout_type = c5.selectbox("Grout type", possible_grout_types, index=0, key=f"grout_type_{i}")
        alpha_choice = c6.radio("αbond", ["low", "mid", "high"], index=1, horizontal=True, key=f"alpha_choice_{i}")

        c7, c8, c9 = st.columns([1, 1, 1.4])
        fs_comp_layer = c7.number_input("FS comp", min_value=1.0, value=2.0, step=0.25, key=f"fs_comp_{i}")
        fs_tension_layer = c8.number_input("FS tension", min_value=1.0, value=2.0, step=0.25, key=f"fs_tension_{i}")
        custom_allowable = c9.checkbox("Use user allowable bond values for this layer", value=False, key=f"custom_layer_bond_{i}")
        custom_comp_psi = 0.0
        custom_tension_psi = 0.0
        if custom_allowable:
            c10, c11 = st.columns(2)
            custom_comp_psi = c10.number_input("Allowable comp bond (psi)", min_value=0.0, value=75.0, step=5.0, key=f"custom_comp_psi_{i}")
            custom_tension_psi = c11.number_input("Allowable tension bond (psi)", min_value=0.0, value=25.0, step=5.0, key=f"custom_tension_psi_{i}")

        layer = build_layer(
            i,
            top_ft=float(top_ft),
            bottom_ft=float(bottom_ft),
            soil_type=str(soil_type),
            grout_type=str(grout_type),
            alpha_choice=str(alpha_choice),
            fs_comp=float(fs_comp_layer),
            fs_tension=float(fs_tension_layer),
            custom_allowable=bool(custom_allowable),
            custom_comp_psi=float(custom_comp_psi),
            custom_tension_psi=float(custom_tension_psi),
            bonds_df=bonds_df,
            bond_diameter_in=float(bond_diameter_in),
        )
        layer["label"] = layer_label
        soil_layers.append(layer)
        previous_bottom = float(bottom_ft)

bond_layer_index, bond_layer = find_bond_layer(soil_layers, casing_end_ft)

if bond_layer is None:
    st.error("No bond layer found at the casing-end depth. Extend the layer table deeper than the casing end.")
    st.stop()

available_length_in_bond_layer_ft = max(bond_layer["bottom_ft"] - max(casing_end_ft, bond_layer["top_ft"]), 0.0)
effective_bond_length_ft = min(proposed_bond_length_input_ft, available_length_in_bond_layer_ft)
calculation_total_length_ft = casing_end_ft + effective_bond_length_ft
shown_total_length_ft = max(calculation_total_length_ft, max(layer["bottom_ft"] for layer in soil_layers), casing_end_ft + proposed_bond_length_input_ft)

# Set bond values from the selected layer only.
use_user_allowable_bond = bond_layer["basis"] == "User allowable bond"
allowable_bond_comp_psi = bond_layer["allowable_comp_psi"]
allowable_bond_tension_psi = bond_layer["allowable_tension_psi"]
alpha_ultimate_comp_psi = bond_layer["alpha_comp_psi"]
alpha_ultimate_tension_psi = bond_layer["alpha_tension_psi"]
fs_comp = bond_layer["fs_comp"]
fs_tension = bond_layer["fs_tension"]

inputs = MicropileInputs(
    pile_configuration=pile_configuration,
    required_compression_kips=required_compression_kips,
    required_tension_kips=required_tension_kips,
    bar=bar,
    casing=casing,
    grout_fc_psi=grout_fc_psi,
    bond_diameter_in=bond_diameter_in,
    provided_bond_length_ft=effective_bond_length_ft,
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

st.subheader("Auto-Selected Bond Layer")
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Final Status", summary["Final OK"])
col2.metric("Bond Layer", f"L{bond_layer_index + 1}")
col3.metric("Layer Depth", f"{bond_layer['top_ft']:.1f}–{bond_layer['bottom_ft']:.1f} ft")
col4.metric("Used Bond Length", f"{effective_bond_length_ft:.1f} ft")
col5.metric("Req'd Bond Length", f"{summary['Governing required bond length rounded (ft)']} ft")

if proposed_bond_length_input_ft > available_length_in_bond_layer_ft:
    st.warning(
        f"The proposed bond length ({proposed_bond_length_input_ft:.1f} ft) is longer than the available length in the selected bond layer below the casing end ({available_length_in_bond_layer_ft:.1f} ft). The calculation uses only {effective_bond_length_ft:.1f} ft in that selected layer. It does not continue the bond into the next layer."
    )

st.markdown(
    f"**Calculation bond basis:** Layer L{bond_layer_index + 1} — {bond_layer['soil_type']} / Type {bond_layer['grout_type']} / {bond_layer['basis']} / allowable C-T bond = **{allowable_bond_comp_psi:.1f} psi / {allowable_bond_tension_psi:.1f} psi**."
)

# Layer table with all details and capacities.
layer_rows = []
for layer in soil_layers:
    below_casing_in_layer = 0.0
    if layer["index"] == bond_layer_index:
        below_casing_in_layer = available_length_in_bond_layer_ft
    layer_rows.append(
        {
            "Used?": "YES - BOND" if layer["index"] == bond_layer_index else "No",
            "Layer": f"L{layer['index'] + 1}",
            "Label": layer.get("label", ""),
            "Top (ft)": round(layer["top_ft"], 2),
            "Bottom (ft)": round(layer["bottom_ft"], 2),
            "Soil/Rock Type": layer["soil_type"],
            "Grout Type": layer["grout_type"],
            "αult Used (psi)": round(layer["alpha_comp_psi"], 2),
            "FS C/T": f"{layer['fs_comp']:.2f}/{layer['fs_tension']:.2f}",
            "αallow C/T (psi)": f"{layer['allowable_comp_psi']:.1f}/{layer['allowable_tension_psi']:.1f}",
            "Full Layer Comp Cap. (kip)": round(layer["capacity_comp_full_layer_kips"], 1),
            "Full Layer Tens. Cap. (kip)": round(layer["capacity_tension_full_layer_kips"], 1),
            "Available Below Casing (ft)": round(below_casing_in_layer, 2),
            "Bond Length Used (ft)": round(effective_bond_length_ft, 2) if layer["index"] == bond_layer_index else "—",
        }
    )

st.subheader("Layer Table / Bond Capacity Library")
render_table(pd.DataFrame(layer_rows))

st.subheader("Schematic Drawing")
try:
    drawing_svg = make_profile_svg(
        soil_layers,
        total_length_ft=shown_total_length_ft,
        cased_length_ft=casing_end_ft,
        effective_bond_length_ft=effective_bond_length_ft,
        required_bond_length_ft=results["geotechnical"]["required_length_governing_rounded_ft"],
        bond_diameter_in=bond_diameter_in,
        casing_label=casing.name if casing else "No casing",
        bar_label=bar.name,
        bond_layer_index=bond_layer_index,
        groundwater_ft=groundwater_ft,
    )
    st.markdown(drawing_svg, unsafe_allow_html=True)
except Exception as exc:
    st.info(f"Drawing could not be generated from the current inputs: {exc}")

st.subheader("Summary Checks")
summary_rows = [
    ["Compression structural", status_badge(results["checks"]["compression_structural_ok"]), f"{results['structural']['controlling_compression_capacity_kips']:.1f} kips", f">= {required_compression_kips:.1f} kips"],
    ["Tension structural", status_badge(results["checks"]["tension_structural_ok"]), f"{results['structural']['controlling_tension_capacity_kips']:.1f} kips", f">= {required_tension_kips:.1f} kips"],
    ["Compression bond - selected layer only", status_badge(results["checks"]["compression_geotechnical_ok"]), f"{results['geotechnical']['provided_compression_bond_capacity_kips']:.1f} kips", f">= {required_compression_kips:.1f} kips"],
    ["Tension bond - selected layer only", status_badge(results["checks"]["tension_geotechnical_ok"]), f"{results['geotechnical']['provided_tension_bond_capacity_kips']:.1f} kips", f">= {required_tension_kips:.1f} kips"],
    ["Provided bond/socket length", status_badge(results["checks"]["provided_length_ok"]), f"{effective_bond_length_ft:.1f} ft used", f">= {results['geotechnical']['required_length_governing_ft']:.2f} ft"],
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
    st.subheader("Bond / Socket - Selected Layer Only")
    bond_rows = [
        ["Casing end / bond start depth", casing_end_ft, "ft"],
        ["Selected bond layer", f"L{bond_layer_index + 1} - {bond_layer['soil_type']}", ""],
        ["Available length in selected layer below casing end", available_length_in_bond_layer_ft, "ft"],
        ["Proposed length entered", proposed_bond_length_input_ft, "ft"],
        ["Effective length used in calculation", effective_bond_length_ft, "ft"],
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
**Layer/bond logic**

- The user defines soil/rock layers with top and bottom depths.
- The bond layer is automatically selected as the layer at the casing-end depth.
- The bond calculation uses only that selected layer.
- If the entered bond length is longer than the available thickness in the selected layer below the casing end, the calculation caps the used bond length at the available length and warns the user.

**Key equations implemented**

- Cased compression: `Pc_allow = 0.4 f'c Agrout + 0.47 Fy_steel (Abar + Acasing)`
- Cased tension: `Pt_allow = 0.55 Fy_steel (Abar + Acasing)`; casing may be ignored in tension unless verified.
- Uncased compression: `Pc_allow = 0.4 f'c Agrout + 0.47 Fy_bar Abar`
- Uncased tension: `Pt_allow = 0.55 Fy_bar Abar`
- Bond capacity: `P_allow = π × Db × Lb × α_allow`
- For FHWA Table 5-3: `α_allow = α_ultimate / FS`.
- For user-specified allowable layer bond values: the entered values are used directly without another FS.

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
    "selected_bond_layer": bond_layer,
    "layers": soil_layers,
    "results": results,
}
report_json = json.dumps(report, indent=2)
st.download_button("Download JSON calculation report", report_json, file_name="micropile_calculation_report.json", mime="application/json")

report_txt = (
    "Micropile ASD Design Calculator Report\n\n"
    + "Selected bond layer: "
    + f"L{bond_layer_index + 1} - {bond_layer['soil_type']}\n"
    + f"Casing end depth: {casing_end_ft:.2f} ft\n"
    + f"Effective bond length used: {effective_bond_length_ft:.2f} ft\n\n"
    + "\n".join([f"{k}: {v}" for k, v in summary.items()])
    + "\n\nWarnings:\n"
    + "\n".join(results["warnings"] or ["None"])
)
st.download_button("Download text summary", report_txt, file_name="micropile_calculation_summary.txt", mime="text/plain")

st.caption("Use for preliminary estimating/design checks only. Final calculations require engineer review and applicable specifications.")
