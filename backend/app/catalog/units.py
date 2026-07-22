UnitSystem = str  # "metric" | "imperial" | "mixed"

UNIT_SYSTEMS: tuple[str, ...] = ("metric", "imperial", "mixed")

_LINEAR_FACTORS: dict[tuple[str, str], float] = {
    ("kW", "hp"): 1.34102209,
    ("Nm", "lb-ft"): 0.73756215,
    ("kg", "lb"): 2.20462262,
    ("km/h", "mph"): 0.62137119,
    ("mm", "in"): 0.03937008,
    ("L", "gal"): 0.26417205,
}

# L/100km <-> mpg (US) is reciprocal, not linear: mpg = 235.2146 / (L/100km).
_RECIPROCAL_PAIRS: dict[frozenset[str], float] = {
    frozenset(("L/100km", "mpg")): 235.2145833,
}

# Canonical units are metric, so "metric" needs no mapping. Displacement (cc)
# and time (s) stay as-is in imperial by industry convention.
_IMPERIAL_DISPLAY_UNITS: dict[str, str] = {
    "kW": "hp",
    "Nm": "lb-ft",
    "kg": "lb",
    "km/h": "mph",
    "mm": "in",
    "L": "gal",
    "L/100km": "mpg",
}

# "mixed" is the motorcycle-press convention in metric markets: everything
# metric except power, which riders and reviews quote in hp.
_MIXED_DISPLAY_UNITS: dict[str, str] = {
    "kW": "hp",
}


class UnknownConversionError(ValueError):
    def __init__(self, from_unit: str, to_unit: str):
        super().__init__(f"no known conversion from {from_unit!r} to {to_unit!r}")
        self.from_unit = from_unit
        self.to_unit = to_unit


def convert(value: float, from_unit: str, to_unit: str) -> float:
    if from_unit == to_unit:
        return value
    if (from_unit, to_unit) in _LINEAR_FACTORS:
        return value * _LINEAR_FACTORS[(from_unit, to_unit)]
    if (to_unit, from_unit) in _LINEAR_FACTORS:
        return value / _LINEAR_FACTORS[(to_unit, from_unit)]
    reciprocal_constant = _RECIPROCAL_PAIRS.get(frozenset((from_unit, to_unit)))
    if reciprocal_constant is not None:
        if value == 0:
            raise ValueError(f"cannot convert 0 between {from_unit!r} and {to_unit!r}")
        return reciprocal_constant / value
    raise UnknownConversionError(from_unit, to_unit)


def display_unit(canonical_unit: str, unit_system: UnitSystem) -> str:
    if unit_system == "imperial":
        return _IMPERIAL_DISPLAY_UNITS.get(canonical_unit, canonical_unit)
    if unit_system == "mixed":
        return _MIXED_DISPLAY_UNITS.get(canonical_unit, canonical_unit)
    return canonical_unit
