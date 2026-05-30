"""Command-line version of the micropile calculator.

Run default generic example:
    python cli.py

Run with JSON input:
    python cli.py sample_general_config.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from micropile_calc_engine import Bar, Casing, MicropileInputs, calculate, flat_summary

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"


def get_bar(name: str) -> Bar:
    df = pd.read_csv(DATA_DIR / "bars.csv")
    row = df[df["name"] == name].iloc[0]
    return Bar(row["name"], float(row["area_in2"]), float(row["od_in"]), float(row["id_in"]), float(row["fy_ksi"]), row.get("source", ""))


def get_casing(name: str) -> Casing | None:
    df = pd.read_csv(DATA_DIR / "casings.csv")
    row = df[df["name"] == name].iloc[0]
    if float(row["od_in"]) <= 0:
        return None
    return Casing(row["name"], float(row["od_in"]), float(row["wall_in"]), float(row["fy_ksi"]), row.get("source", ""))


def default_config() -> dict:
    return {
        "pile_configuration": "Casing + hollow/core bar",
        "required_compression_kips": 150,
        "required_tension_kips": 0,
        "bar_name": "No.20 Grade 60 Rebar",
        "casing_name": "9.625 in OD x 0.500 in wall",
        "grout_fc_psi": 5000,
        "bond_diameter_in": 8,
        "provided_bond_length_ft": 8,
        "corrosion_allowance_in": 0.0,
        "use_user_allowable_bond": False,
        "allowable_bond_comp_psi": 75,
        "allowable_bond_tension_psi": 25,
        "min_socket_ft": 0,
    }


def build_inputs(cfg: dict) -> MicropileInputs:
    bar = get_bar(cfg.get("bar_name", "No.20 Grade 60 Rebar"))
    casing = get_casing(cfg.get("casing_name", "9.625 in OD x 0.500 in wall"))
    return MicropileInputs(
        pile_configuration=cfg.get("pile_configuration", "Casing + hollow/core bar"),
        required_compression_kips=float(cfg.get("required_compression_kips", 150)),
        required_tension_kips=float(cfg.get("required_tension_kips", 60)),
        bar=bar,
        casing=casing,
        grout_fc_psi=float(cfg.get("grout_fc_psi", 6000)),
        bond_diameter_in=float(cfg.get("bond_diameter_in", 8)),
        provided_bond_length_ft=float(cfg.get("provided_bond_length_ft", 8)),
        corrosion_allowance_in=float(cfg.get("corrosion_allowance_in", 0)),
        use_user_allowable_bond=bool(cfg.get("use_user_allowable_bond", True)),
        alpha_ultimate_comp_psi=float(cfg.get("alpha_ultimate_comp_psi", 150)),
        alpha_ultimate_tension_psi=float(cfg.get("alpha_ultimate_tension_psi", 75)),
        fs_bond_comp=float(cfg.get("fs_bond_comp", 2)),
        fs_bond_tension=float(cfg.get("fs_bond_tension", 2)),
        allowable_bond_comp_psi=float(cfg.get("allowable_bond_comp_psi", 75)),
        allowable_bond_tension_psi=float(cfg.get("allowable_bond_tension_psi", 25)),
        count_casing_in_tension=bool(cfg.get("count_casing_in_tension", False)),
        casing_extends_full_bond=bool(cfg.get("casing_extends_full_bond", False)),
        proof_factor_comp=float(cfg.get("proof_factor_comp", 1)),
        proof_factor_tension=float(cfg.get("proof_factor_tension", 1)),
        min_socket_ft=float(cfg.get("min_socket_ft", 0)),
        round_socket_up_to_ft=float(cfg.get("round_socket_up_to_ft", 0.5)),
    )


def main() -> None:
    if len(sys.argv) > 1:
        cfg = json.loads(Path(sys.argv[1]).read_text())
    else:
        cfg = default_config()
    results = calculate(build_inputs(cfg))
    print("Micropile ASD Design Calculator")
    print("=" * 34)
    for k, v in flat_summary(results).items():
        print(f"{k}: {v}")
    if results["warnings"]:
        print("\nWarnings:")
        for w in results["warnings"]:
            print(f"- {w}")


if __name__ == "__main__":
    main()
