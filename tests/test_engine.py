from micropile_calc_engine import Bar, Casing, MicropileInputs, calculate


def test_generic_150_kip_socket_math():
    bar = Bar("No.20 Grade 60 Rebar", 4.91, 2.5, 0, 60)
    casing = Casing("9.625 x 0.5", 9.625, 0.5, 50)
    inputs = MicropileInputs(
        pile_configuration="Casing + hollow/core bar",
        required_compression_kips=150,
        required_tension_kips=60,
        bar=bar,
        casing=casing,
        grout_fc_psi=6000,
        bond_diameter_in=8,
        provided_bond_length_ft=8,
        corrosion_allowance_in=0.0,
        use_user_allowable_bond=True,
        allowable_bond_comp_psi=75,
        allowable_bond_tension_psi=25,
        min_socket_ft=0,
    )
    r = calculate(inputs)
    assert r["geotechnical"]["provided_compression_bond_capacity_kips"] > 180
    assert 60 <= r["geotechnical"]["provided_tension_bond_capacity_kips"] <= 61
    assert r["checks"]["final_ok"]


def test_150_kip_tension_with_25psi_requires_about_20ft():
    bar = Bar("TB103/75", 4.78, 4.06, 2.95, 75)
    inputs = MicropileInputs(
        pile_configuration="Hollow bar only / bar only",
        required_compression_kips=0,
        required_tension_kips=150,
        bar=bar,
        casing=None,
        grout_fc_psi=6000,
        bond_diameter_in=8,
        provided_bond_length_ft=8,
        use_user_allowable_bond=True,
        allowable_bond_comp_psi=75,
        allowable_bond_tension_psi=25,
    )
    r = calculate(inputs)
    assert 19.8 <= r["geotechnical"]["required_length_tension_ft"] <= 20.0
    assert not r["checks"]["provided_length_ok"]
