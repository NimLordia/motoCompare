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

# Manufacturer roster with each brand's official web domains. Single source of
# truth for both the seeded manufacturer catalog and research's official-tier
# domain matching (app.research.tiering derives OFFICIAL_DOMAINS from it), so
# the two lists cannot drift apart.
MANUFACTURER_OFFICIAL_DOMAINS: dict[str, frozenset[str]] = {
    "Aprilia": frozenset({"aprilia.com"}),
    "BMW": frozenset({"bmw-motorrad.com", "bmw-motorrad.de"}),
    "CFMoto": frozenset({"cfmoto.com"}),
    "Ducati": frozenset({"ducati.com"}),
    "Harley-Davidson": frozenset({"harley-davidson.com"}),
    "Honda": frozenset({"honda.co.uk", "honda.com"}),
    "Husqvarna": frozenset({"husqvarna-motorcycles.com"}),
    "Indian": frozenset({"indianmotorcycle.com"}),
    "Kawasaki": frozenset({"kawasaki.com", "kawasaki.eu"}),
    "KTM": frozenset({"ktm.com"}),
    "Moto Guzzi": frozenset({"motoguzzi.com"}),
    "MV Agusta": frozenset({"mvagusta.com"}),
    "Piaggio": frozenset({"piaggio.com"}),
    "Royal Enfield": frozenset({"royalenfield.com"}),
    "Suzuki": frozenset({"suzuki.com", "suzukicycles.com"}),
    "Triumph": frozenset({"triumphmotorcycles.co.uk", "triumphmotorcycles.com"}),
    "Vespa": frozenset({"vespa.com"}),
    "Yamaha": frozenset({"yamaha-motor.com", "yamaha-motor.eu", "yamahamotorsports.com"}),
    "Zero": frozenset({"zeromotorcycles.com"}),
}

# All topics are core: data_coverage treats every topic as required for a complete bike page.
INSIGHT_TOPICS: tuple[str, ...] = (
    "heat",
    "comfort",
    "maintenance",
    "electronics",
    "reliability",
    "real_world_performance",
)
