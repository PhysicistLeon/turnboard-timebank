from timebank_app.ui.formatting import format_mm_ss


def test_format_mm_ss_positive_values():
    assert format_mm_ss(0) == "00:00"
    assert format_mm_ss(59.9) == "00:59"
    assert format_mm_ss(60) == "01:00"
    assert format_mm_ss(6012) == "100:12"


def test_format_mm_ss_negative_values():
    assert format_mm_ss(-1) == "-00:01"
    assert format_mm_ss(-61) == "-01:01"
    assert format_mm_ss(-6012) == "-100:12"
