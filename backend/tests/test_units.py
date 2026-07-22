import pytest

from app.catalog import units


def test_same_unit_is_identity():
    assert units.convert(54.0, "kW", "kW") == 54.0


@pytest.mark.parametrize(
    ("value", "from_unit", "to_unit", "expected"),
    [
        (54.0, "kW", "hp", 72.42),
        (67.0, "Nm", "lb-ft", 49.42),
        (188.0, "kg", "lb", 414.47),
        (100.0, "km/h", "mph", 62.14),
        (835.0, "mm", "in", 32.87),
        (13.0, "L", "gal", 3.43),
    ],
)
def test_linear_conversions(value: float, from_unit: str, to_unit: str, expected: float):
    assert units.convert(value, from_unit, to_unit) == pytest.approx(expected, abs=0.01)


def test_linear_conversions_are_reversible():
    converted = units.convert(54.0, "kW", "hp")
    assert units.convert(converted, "hp", "kW") == pytest.approx(54.0)


def test_fuel_consumption_is_reciprocal():
    mpg = units.convert(4.5, "L/100km", "mpg")
    assert mpg == pytest.approx(52.27, abs=0.01)
    assert units.convert(mpg, "mpg", "L/100km") == pytest.approx(4.5)


def test_fuel_consumption_zero_rejected():
    with pytest.raises(ValueError, match="cannot convert 0"):
        units.convert(0, "L/100km", "mpg")


def test_unknown_conversion_raises():
    with pytest.raises(units.UnknownConversionError):
        units.convert(1.0, "kW", "mph")


def test_display_unit_metric_passthrough():
    assert units.display_unit("kW", "metric") == "kW"


@pytest.mark.parametrize(
    ("canonical", "expected"),
    [("kW", "hp"), ("Nm", "lb-ft"), ("kg", "lb"), ("km/h", "mph"), ("mm", "in"), ("L", "gal")],
)
def test_display_unit_imperial(canonical: str, expected: str):
    assert units.display_unit(canonical, "imperial") == expected


def test_display_unit_imperial_keeps_industry_metric_units():
    assert units.display_unit("cc", "imperial") == "cc"
    assert units.display_unit("s", "imperial") == "s"
    assert units.display_unit("", "imperial") == ""


def test_display_unit_mixed_shows_power_in_hp():
    assert units.display_unit("kW", "mixed") == "hp"


@pytest.mark.parametrize(
    "canonical", ["Nm", "kg", "km/h", "mm", "L", "L/100km", "cc", "s", ""]
)
def test_display_unit_mixed_keeps_everything_else_metric(canonical: str):
    assert units.display_unit(canonical, "mixed") == canonical
