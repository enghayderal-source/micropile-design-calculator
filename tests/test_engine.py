from micropile_calc_engine import Bar, Casing, BarGroup, SoilLayer, MicropileInputs, calculate


def test_multilayer_bond_accumulates_after_casing_end():
    bar = Bar('Nucor #20', 'Solid threaded bar', 4.91, 2.5, 0, 80)
    casing = Casing('9 5/8 x 0.5', 9.625, 0.5, 80)
    layers = [
        SoilLayer(0, 'Fill', 0, 20, 'Fill', 'A', 10, 10, 2, 2, 5, 5),
        SoilLayer(1, 'Weak rock', 20, 25, 'Soft shale', 'A', 80, 80, 2, 2, 40, 40),
        SoilLayer(2, 'Rock', 25, 40, 'Hard shale', 'A', 200, 200, 2, 2, 100, 100),
    ]
    inputs = MicropileInputs(150, 0, 5000, 8, casing, 20, 35, 0, 'Casing + bar', [BarGroup('primary', bar, 1, 35, True)], layers)
    res = calculate(inputs)
    assert res['bond']['rows'][0]['bond_overlap_ft'] == 0
    assert res['bond']['rows'][1]['bond_overlap_ft'] == 5
    assert res['bond']['rows'][2]['bond_overlap_ft'] == 10
    assert res['bond']['provided_comp_capacity_kips'] > 150


def test_partial_bar_not_counted_at_tip():
    full = Bar('small', 'Solid threaded bar', 1.0, 1.0, 0, 80)
    part = Bar('big partial', 'Solid threaded bar', 4.0, 2.0, 0, 80)
    casing = Casing('pipe', 9.625, 0.5, 80)
    layers = [SoilLayer(0, 'Rock', 0, 50, 'Rock', 'A', 100, 100, 2, 2, 50, 50)]
    inputs = MicropileInputs(50, 0, 5000, 8, casing, 10, 30, 0, 'Casing + bar', [BarGroup('full', full, 1, 30, True), BarGroup('partial', part, 1, 10, False)], layers)
    res = calculate(inputs)
    assert res['structural']['uncased_compression_tip']['bar_area_in2'] == 1.0
    assert res['structural']['uncased_compression_start']['bar_area_in2'] == 5.0
