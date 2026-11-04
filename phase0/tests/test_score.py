from srt_phase0.score import verdict, wilson


def test_wilson_known_value():
    # 85/100: Wilson 95% interval is approximately [0.767, 0.907]
    p = wilson(85, 100)
    assert abs(p.lo - 0.767) < 0.002 and abs(p.hi - 0.907) < 0.002


def test_verdicts():
    assert verdict(wilson(198, 200), 0.90) == "pass"
    assert verdict(wilson(10, 11), 0.90) == "inconclusive"
    assert verdict(wilson(50, 100), 0.85) == "fail"
    assert verdict(wilson(0, 0), 0.85) == "no data"
