from dataclasses import dataclass

from app.catalog.models import ValueType


@dataclass(frozen=True)
class SpecDefinitionSeed:
    key: str
    display_name: str
    canonical_unit: str
    value_type: ValueType
    category: str
    is_core: bool


# Bootstrap definition of the spec registry. The spec_definitions table is the
# runtime source of truth; seeding writes these rows and tests build from them.
SPEC_DEFINITIONS: tuple[SpecDefinitionSeed, ...] = (
    SpecDefinitionSeed("engine_type", "Engine type", "", ValueType.text, "engine", True),
    SpecDefinitionSeed("displacement", "Displacement", "cc", ValueType.number, "engine", True),
    SpecDefinitionSeed("power_peak", "Peak power", "kW", ValueType.number, "engine", True),
    SpecDefinitionSeed("torque_peak", "Peak torque", "Nm", ValueType.number, "engine", True),
    SpecDefinitionSeed(
        "compression_ratio", "Compression ratio", "", ValueType.number, "engine", False
    ),
    SpecDefinitionSeed("wet_weight", "Wet weight", "kg", ValueType.number, "chassis", True),
    SpecDefinitionSeed("dry_weight", "Dry weight", "kg", ValueType.number, "chassis", False),
    SpecDefinitionSeed("seat_height", "Seat height", "mm", ValueType.number, "dimensions", True),
    SpecDefinitionSeed("wheelbase", "Wheelbase", "mm", ValueType.number, "dimensions", False),
    SpecDefinitionSeed("fuel_capacity", "Fuel capacity", "L", ValueType.number, "dimensions", True),
    SpecDefinitionSeed("top_speed", "Top speed", "km/h", ValueType.number, "performance", True),
    SpecDefinitionSeed(
        "acceleration_0_100", "0-100 km/h", "s", ValueType.number, "performance", False
    ),
    SpecDefinitionSeed(
        "fuel_consumption", "Fuel consumption", "L/100km", ValueType.number, "performance", False
    ),
)

CORE_SPEC_KEYS: tuple[str, ...] = tuple(
    definition.key for definition in SPEC_DEFINITIONS if definition.is_core
)

# All topics are core: data_coverage treats every topic as required for a complete bike page.
INSIGHT_TOPICS: tuple[str, ...] = (
    "heat",
    "comfort",
    "maintenance",
    "electronics",
    "reliability",
    "real_world_performance",
)
