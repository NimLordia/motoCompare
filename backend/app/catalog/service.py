import re
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from difflib import SequenceMatcher

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.catalog import units
from app.catalog.models import (
    SOURCE_TIER_PRIORITY,
    Insight,
    Manufacturer,
    Model,
    Motorcycle,
    SourceType,
    SpecDefinition,
    SpecValue,
    ValueType,
)
from app.catalog.registry import CORE_SPEC_KEYS, INSIGHT_TOPICS, SPEC_DEFINITIONS
from app.catalog.schemas import (
    BikeCandidate,
    BikeDetail,
    ComparisonCell,
    ComparisonMatrix,
    ComparisonRow,
    Coverage,
    Fact,
    InsightOut,
    ManufacturerOut,
    ModelOut,
    VariantOut,
)


class CatalogNotFoundError(LookupError):
    pass


class CatalogValidationError(ValueError):
    pass


_REGISTRY_DISPLAY_ORDER = {
    definition.key: index for index, definition in enumerate(SPEC_DEFINITIONS)
}

_MINIMUM_RESOLVE_CONFIDENCE = 0.35


def list_manufacturers(db: Session) -> list[ManufacturerOut]:
    manufacturers = db.scalars(select(Manufacturer).order_by(Manufacturer.name)).all()
    return [ManufacturerOut.model_validate(manufacturer) for manufacturer in manufacturers]


def list_models(db: Session, manufacturer_id: int) -> list[ModelOut]:
    if db.get(Manufacturer, manufacturer_id) is None:
        raise CatalogNotFoundError(f"manufacturer {manufacturer_id} not found")
    models = db.scalars(
        select(Model).where(Model.manufacturer_id == manufacturer_id).order_by(Model.name)
    ).all()
    return [ModelOut.model_validate(model) for model in models]


def list_variants(db: Session, model_id: int) -> list[VariantOut]:
    if db.get(Model, model_id) is None:
        raise CatalogNotFoundError(f"model {model_id} not found")
    variants = db.scalars(
        select(Motorcycle)
        .where(Motorcycle.model_id == model_id)
        .options(joinedload(Motorcycle.model).joinedload(Model.manufacturer))
        .order_by(Motorcycle.year.desc(), Motorcycle.trim, Motorcycle.market)
    ).all()
    return [_variant_out(variant) for variant in variants]


def get_variant(db: Session, bike_id: int) -> VariantOut:
    return _variant_out(_get_bike(db, bike_id))


def resolve_bike(
    db: Session, query: str, market: str | None = None, limit: int = 5
) -> list[BikeCandidate]:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []
    statement = select(Motorcycle).options(
        joinedload(Motorcycle.model).joinedload(Model.manufacturer)
    )
    if market:
        # Bikes with no market recorded ("") stay eligible in every market.
        statement = statement.where(or_(Motorcycle.market == market, Motorcycle.market == ""))
    # Application-side scoring over the full candidate set: the catalog stays
    # small (thousands of variants at most) and short queries like "R7" defeat
    # trigram similarity. Supersede with pg_trgm if scale ever demands it.
    candidates = db.scalars(statement).all()
    scored = [
        (confidence, candidate)
        for candidate in candidates
        if (confidence := _match_confidence(query_tokens, candidate))
        >= _MINIMUM_RESOLVE_CONFIDENCE
    ]
    scored.sort(key=lambda pair: (-pair[0], -pair[1].year, pair[1].id))
    return [
        BikeCandidate(bike=_variant_out(candidate), confidence=round(confidence, 3))
        for confidence, candidate in scored[:limit]
    ]


PendingResearch = tuple[set[str], set[str]]


def _no_pending_research(db: Session, bike_id: int) -> PendingResearch:
    return set(), set()


# The research module registers its provider here at startup so coverage can
# report in-flight research without catalog importing research code.
_pending_research_provider: Callable[[Session, int], PendingResearch] = _no_pending_research


def register_pending_research_provider(
    provider: Callable[[Session, int], PendingResearch],
) -> None:
    global _pending_research_provider
    _pending_research_provider = provider


def data_coverage(db: Session, bike_id: int) -> Coverage:
    _get_bike(db, bike_id)
    present_spec_keys = set(
        db.scalars(
            select(SpecValue.spec_key).where(SpecValue.motorcycle_id == bike_id).distinct()
        )
    )
    present_topics = set(
        db.scalars(select(Insight.topic).where(Insight.motorcycle_id == bike_id).distinct())
    )
    pending_specs, pending_topics = _pending_research_provider(db, bike_id)
    core_specs_missing = [key for key in CORE_SPEC_KEYS if key not in present_spec_keys]
    insight_topics_missing = [
        topic for topic in INSIGHT_TOPICS if topic not in present_topics
    ]
    return Coverage(
        bike_id=bike_id,
        core_specs_present=[key for key in CORE_SPEC_KEYS if key in present_spec_keys],
        core_specs_missing=core_specs_missing,
        insight_topics_present=[
            topic for topic in INSIGHT_TOPICS if topic in present_topics
        ],
        insight_topics_missing=insight_topics_missing,
        research_pending_specs=sorted(pending_specs),
        research_pending_topics=sorted(pending_topics),
        complete=not core_specs_missing and not insight_topics_missing,
    )


def get_specs(
    db: Session,
    bike_id: int,
    keys: Sequence[str] | None = None,
    unit_system: str = "metric",
) -> list[Fact]:
    _validate_unit_system(unit_system)
    _get_bike(db, bike_id)
    if keys is not None:
        _validate_spec_keys(db, keys)
    statement = (
        select(SpecValue)
        .where(SpecValue.motorcycle_id == bike_id)
        .options(joinedload(SpecValue.definition))
    )
    if keys is not None:
        statement = statement.where(SpecValue.spec_key.in_(keys))
    spec_values = db.scalars(statement).all()
    facts = [_fact_from_spec_value(spec_value, unit_system) for spec_value in spec_values]
    facts.sort(key=_fact_display_order)
    return facts


def compare(
    db: Session,
    bike_ids: Sequence[int],
    keys: Sequence[str] | None = None,
    unit_system: str = "metric",
) -> ComparisonMatrix:
    _validate_unit_system(unit_system)
    if len(bike_ids) < 2:
        raise CatalogValidationError("comparison requires at least two bikes")
    if len(set(bike_ids)) != len(bike_ids):
        raise CatalogValidationError("comparison bike ids must be distinct")
    bikes = [_get_bike(db, bike_id) for bike_id in bike_ids]
    facts_per_bike = [get_specs(db, bike_id, keys, unit_system) for bike_id in bike_ids]

    if keys is not None:
        row_keys = list(dict.fromkeys(keys))
    else:
        present_keys = {fact.spec_key for facts in facts_per_bike for fact in facts}
        row_keys = sorted(
            present_keys,
            key=lambda key: (_REGISTRY_DISPLAY_ORDER.get(key, len(SPEC_DEFINITIONS)), key),
        )

    definitions = {
        definition.key: definition
        for definition in db.scalars(
            select(SpecDefinition).where(SpecDefinition.key.in_(row_keys))
        )
    }
    rows = []
    for spec_key in row_keys:
        definition = definitions[spec_key]
        cells = []
        for facts in facts_per_bike:
            cell_facts = [fact for fact in facts if fact.spec_key == spec_key]
            cells.append(ComparisonCell(facts=cell_facts, missing=not cell_facts))
        rows.append(
            ComparisonRow(
                spec_key=spec_key,
                display_name=definition.display_name,
                category=definition.category,
                unit=units.display_unit(definition.canonical_unit, unit_system),
                cells=cells,
            )
        )
    return ComparisonMatrix(bikes=[_variant_out(bike) for bike in bikes], rows=rows)


def get_insights(
    db: Session, bike_id: int, topics: Sequence[str] | None = None
) -> list[InsightOut]:
    _get_bike(db, bike_id)
    if topics is not None:
        unknown_topics = set(topics) - set(INSIGHT_TOPICS)
        if unknown_topics:
            raise CatalogValidationError(f"unknown insight topics: {sorted(unknown_topics)}")
    statement = select(Insight).where(Insight.motorcycle_id == bike_id)
    if topics is not None:
        statement = statement.where(Insight.topic.in_(topics))
    insights = db.scalars(statement).all()
    insights = sorted(insights, key=lambda insight: INSIGHT_TOPICS.index(insight.topic))
    return [InsightOut.model_validate(insight) for insight in insights]


def get_bike_detail(db: Session, bike_id: int, unit_system: str = "metric") -> BikeDetail:
    bike = _get_bike(db, bike_id)
    return BikeDetail(
        bike=_variant_out(bike),
        specs=get_specs(db, bike_id, unit_system=unit_system),
        insights=get_insights(db, bike_id),
        coverage=data_coverage(db, bike_id),
    )


def upsert_spec_value(
    db: Session,
    bike_id: int,
    spec_key: str,
    value: float | str,
    unit: str | None,
    source_type: SourceType | str,
    source_url: str | None = None,
    source_note: str | None = None,
    retrieved_at: datetime | None = None,
) -> SpecValue:
    _get_bike(db, bike_id)
    definition = db.get(SpecDefinition, spec_key)
    if definition is None:
        raise CatalogValidationError(f"spec key {spec_key!r} is not in the registry")
    source_type = _coerce_source_type(source_type)

    value_num: float | None = None
    value_text: str | None = None
    if definition.value_type == ValueType.number:
        if isinstance(value, str):
            raise CatalogValidationError(
                f"spec {spec_key!r} expects a numeric value, got {value!r}"
            )
        source_unit = unit if unit is not None else definition.canonical_unit
        try:
            value_num = units.convert(float(value), source_unit, definition.canonical_unit)
        except units.UnknownConversionError as error:
            raise CatalogValidationError(str(error)) from error
    else:
        if not isinstance(value, str) or not value.strip():
            raise CatalogValidationError(
                f"spec {spec_key!r} expects a non-empty text value, got {value!r}"
            )
        if unit:
            raise CatalogValidationError(f"text spec {spec_key!r} does not take a unit")
        value_text = value.strip()

    existing = db.scalars(
        select(SpecValue).where(
            SpecValue.motorcycle_id == bike_id,
            SpecValue.spec_key == spec_key,
            SpecValue.source_type == source_type,
        )
    ).one_or_none()
    if existing is None:
        existing = SpecValue(motorcycle_id=bike_id, spec_key=spec_key, source_type=source_type)
        db.add(existing)
    existing.value_num = value_num
    existing.value_text = value_text
    existing.source_url = source_url
    existing.source_note = source_note
    existing.retrieved_at = retrieved_at or datetime.now(UTC)
    db.flush()
    return existing


def upsert_insight(
    db: Session,
    bike_id: int,
    topic: str,
    summary: str,
    source_type: SourceType | str,
    source_urls: Sequence[str],
    retrieved_at: datetime | None = None,
) -> Insight:
    _get_bike(db, bike_id)
    if topic not in INSIGHT_TOPICS:
        raise CatalogValidationError(f"unknown insight topic {topic!r}")
    source_type = _coerce_source_type(source_type)
    if source_type not in (SourceType.community, SourceType.tested):
        raise CatalogValidationError("insights only accept community or tested sources")
    if not summary.strip():
        raise CatalogValidationError("insight summary must not be empty")
    if not source_urls:
        raise CatalogValidationError("an insight requires at least one source URL")

    existing = db.scalars(
        select(Insight).where(Insight.motorcycle_id == bike_id, Insight.topic == topic)
    ).one_or_none()
    if existing is None:
        existing = Insight(motorcycle_id=bike_id, topic=topic)
        db.add(existing)
    existing.summary = summary.strip()
    existing.source_type = source_type
    existing.source_urls = list(source_urls)
    existing.retrieved_at = retrieved_at or datetime.now(UTC)
    db.flush()
    return existing


def _get_bike(db: Session, bike_id: int) -> Motorcycle:
    bike = db.get(
        Motorcycle,
        bike_id,
        options=[joinedload(Motorcycle.model).joinedload(Model.manufacturer)],
    )
    if bike is None:
        raise CatalogNotFoundError(f"bike {bike_id} not found")
    return bike


def _variant_out(motorcycle: Motorcycle) -> VariantOut:
    return VariantOut(
        id=motorcycle.id,
        model_id=motorcycle.model_id,
        year=motorcycle.year,
        trim=motorcycle.trim,
        market=motorcycle.market,
        display_name=_display_name(motorcycle),
    )


def _display_name(motorcycle: Motorcycle) -> str:
    parts = [
        motorcycle.model.manufacturer.name,
        motorcycle.model.name,
        str(motorcycle.year),
    ]
    if motorcycle.trim:
        parts.append(motorcycle.trim)
    name = " ".join(parts)
    if motorcycle.market:
        name = f"{name} ({motorcycle.market})"
    return name


def _tokenize(text: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", text.lower()) if token]


def _match_confidence(query_tokens: list[str], motorcycle: Motorcycle) -> float:
    candidate_tokens = _tokenize(
        " ".join(
            (
                motorcycle.model.manufacturer.name,
                motorcycle.model.name,
                str(motorcycle.year),
                motorcycle.trim,
                motorcycle.market,
            )
        )
    )
    token_scores = []
    for query_token in query_tokens:
        best = 0.0
        for candidate_token in candidate_tokens:
            if query_token == candidate_token:
                score = 1.0
            elif query_token in candidate_token or candidate_token in query_token:
                containment = min(len(query_token), len(candidate_token)) / max(
                    len(query_token), len(candidate_token)
                )
                # A tiny token buried in a longer one ("zx" inside "qzxwv") is
                # accidental; containment only counts when it covers half the token.
                score = containment if containment >= 0.5 else 0.0
            else:
                ratio = SequenceMatcher(None, query_token, candidate_token).ratio()
                # Short tokens produce accidental mid ratios ("r7" vs "6r" = 0.5);
                # below difflib's conventional 0.6 cutoff a match means nothing.
                score = ratio if ratio >= 0.6 else 0.0
            best = max(best, score)
            if best == 1.0:
                break
        token_scores.append(best)
    return sum(token_scores) / len(token_scores)


def _validate_unit_system(unit_system: str) -> None:
    if unit_system not in units.UNIT_SYSTEMS:
        raise CatalogValidationError(
            f"unknown unit system {unit_system!r}; expected one of {units.UNIT_SYSTEMS}"
        )


def _validate_spec_keys(db: Session, keys: Sequence[str]) -> None:
    known_keys = set(
        db.scalars(select(SpecDefinition.key).where(SpecDefinition.key.in_(keys)))
    )
    unknown_keys = set(keys) - known_keys
    if unknown_keys:
        raise CatalogValidationError(f"unknown spec keys: {sorted(unknown_keys)}")


def _coerce_source_type(source_type: SourceType | str) -> SourceType:
    try:
        return SourceType(source_type)
    except ValueError as error:
        raise CatalogValidationError(f"unknown source type {source_type!r}") from error


def _fact_from_spec_value(spec_value: SpecValue, unit_system: str) -> Fact:
    definition = spec_value.definition
    target_unit = units.display_unit(definition.canonical_unit, unit_system)
    if definition.value_type == ValueType.number and spec_value.value_num is not None:
        value: float | str = round(
            units.convert(spec_value.value_num, definition.canonical_unit, target_unit), 2
        )
    else:
        value = spec_value.value_text or ""
    return Fact(
        spec_key=spec_value.spec_key,
        display_name=definition.display_name,
        category=definition.category,
        value=value,
        unit=target_unit,
        source_type=spec_value.source_type,
        source_url=spec_value.source_url,
        source_note=spec_value.source_note,
        retrieved_at=spec_value.retrieved_at,
    )


def _fact_display_order(fact: Fact) -> tuple[int, str, int]:
    return (
        _REGISTRY_DISPLAY_ORDER.get(fact.spec_key, len(SPEC_DEFINITIONS)),
        fact.spec_key,
        SOURCE_TIER_PRIORITY[fact.source_type],
    )
