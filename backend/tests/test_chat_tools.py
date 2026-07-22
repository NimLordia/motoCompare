import pytest

from app.catalog import service as catalog_service
from app.chat.tools import build_toolbox
from app.profile import service as profile_service
from app.profile.models import DEFAULT_USER_ID
from app.research import service as research_service
from app.research.provider import InsightFinding, ResearchFindings, SpecFinding
from app.research.runner import run_bike_research

YAMAHA_URL = "https://www.yamaha-motor.eu/r7"
FORUM_URL = "https://www.r7forum.example/heat-thread"


@pytest.fixture()
def toolbox(db):
    def _build(unit_system: str = "metric", inline_budget: float = 0.0):
        tools = build_toolbox(
            db,
            user_id=DEFAULT_USER_ID,
            unit_system=unit_system,
            inline_budget_seconds=inline_budget,
        )
        return {tool.name: tool for tool in tools}

    return _build


@pytest.fixture()
def inline_research(db, fake_provider):
    """Research dispatcher that runs the real pipeline synchronously on await."""

    class InlineDispatcher:
        def submit_bike(self, bike_id: int) -> None:
            pass

        def wait_for_bike(self, bike_id: int, timeout: float) -> bool:
            run_bike_research(db, fake_provider, bike_id)
            return True

    research_service.configure_dispatcher(InlineDispatcher())
    yield fake_provider
    research_service.configure_dispatcher(None)


def call_tool(tool, args: dict):
    message = tool.invoke({"name": tool.name, "args": args, "id": "call_1", "type": "tool_call"})
    return message.content, message.artifact


def seed_power(db, bike, value_kw: float = 54.0) -> None:
    catalog_service.upsert_spec_value(
        db, bike.id, "power_peak", value_kw, "kW", "official", source_url=YAMAHA_URL
    )


def test_resolve_bike_clear_winner_has_no_block(toolbox, make_bike):
    make_bike(model="YZF-R7", year=2023)
    make_bike(model="MT-07", year=2023)

    content, artifact = call_tool(toolbox()["resolve_bike"], {"query": "r7"})

    assert "Resolved to bike_id" in content
    assert "YZF-R7" in content
    assert artifact is None


def test_resolve_bike_ambiguous_years_emit_disambiguation(toolbox, make_bike):
    make_bike(model="YZF-R7", year=2022)
    make_bike(model="YZF-R7", year=2023)

    content, artifact = call_tool(toolbox()["resolve_bike"], {"query": "yamaha r7"})

    assert "ambiguous" in content
    assert artifact is not None and len(artifact) == 1
    block = artifact[0]
    assert block.type == "disambiguation"
    assert block.query == "yamaha r7"
    assert len(block.candidates) == 2


def test_resolve_bike_no_match(toolbox, make_bike):
    make_bike()

    content, artifact = call_tool(toolbox()["resolve_bike"], {"query": "goldwing"})

    assert "not in the catalog" in content
    assert artifact is None


def test_get_specs_returns_facts_and_spec_card(db, toolbox, make_bike):
    bike = make_bike()
    seed_power(db, bike)

    content, artifact = call_tool(toolbox()["get_specs"], {"bike_id": bike.id})

    assert "power_peak: 54.0 kW [official]" in content
    assert "Missing" in content and "top_speed" in content  # core gaps are surfaced
    block = artifact[0]
    assert block.type == "spec_card"
    assert block.bike.id == bike.id
    assert block.facts[0].spec_key == "power_peak"


def test_get_specs_converts_units_for_the_user(db, toolbox, make_bike):
    bike = make_bike()
    seed_power(db, bike)

    content, _ = call_tool(
        toolbox(unit_system="mixed")["get_specs"],
        {"bike_id": bike.id, "keys": ["power_peak"]},
    )

    assert "hp [official]" in content
    assert "kW" not in content


def test_get_specs_requested_missing_key_is_reported(db, toolbox, make_bike):
    bike = make_bike()
    seed_power(db, bike)

    content, artifact = call_tool(
        toolbox()["get_specs"], {"bike_id": bike.id, "keys": ["power_peak", "top_speed"]}
    )

    assert "power_peak: 54.0" in content
    assert "Missing" in content and "top_speed" in content
    assert artifact[0].type == "spec_card"


def test_get_specs_service_errors_become_content(toolbox, make_bike):
    bike = make_bike()

    unknown_bike, artifact = call_tool(toolbox()["get_specs"], {"bike_id": 9999})
    unknown_key, _ = call_tool(
        toolbox()["get_specs"], {"bike_id": bike.id, "keys": ["warp_drive"]}
    )

    assert unknown_bike.startswith("Error:") and "not found" in unknown_bike
    assert artifact is None
    assert unknown_key.startswith("Error:") and "warp_drive" in unknown_key


def test_compare_bikes_builds_table_and_reports_gaps(db, toolbox, make_bike):
    r7 = make_bike(model="YZF-R7", year=2023)
    mt = make_bike(model="MT-07", year=2023)
    seed_power(db, r7)
    seed_power(db, mt, value_kw=54.5)
    catalog_service.upsert_spec_value(
        db, r7.id, "wet_weight", 188, "kg", "official", source_url=YAMAHA_URL
    )

    content, artifact = call_tool(
        toolbox()["compare_bikes"], {"bike_ids": [r7.id, mt.id]}
    )

    assert "Yamaha YZF-R7 2023" in content and "Yamaha MT-07 2023" in content
    assert "power_peak" in content
    assert f"wet_weight for bike_id {mt.id}" in content  # the gap is called out
    assert artifact[0].type == "comparison_table"
    assert [bike.id for bike in artifact[0].matrix.bikes] == [r7.id, mt.id]


def test_compare_bikes_needs_two(toolbox, make_bike):
    bike = make_bike()

    content, artifact = call_tool(toolbox()["compare_bikes"], {"bike_ids": [bike.id]})

    assert content.startswith("Error:")
    assert artifact is None


def test_get_insights_returns_insight_card_and_missing_topics(db, toolbox, make_bike):
    bike = make_bike()
    catalog_service.upsert_insight(
        db, bike.id, "heat", "Runs warm in traffic.", "community", [FORUM_URL]
    )

    content, artifact = call_tool(toolbox()["get_insights"], {"bike_id": bike.id})

    assert "heat [community, 1 source]: Runs warm in traffic." in content
    assert "Missing topics" in content and "comfort" in content
    block = artifact[0]
    assert block.type == "insight_card"
    assert block.insights[0].source_urls == [FORUM_URL]


def test_get_user_profile_includes_current_bike(db, toolbox, make_bike):
    bike = make_bike()
    profile_service.add_garage_bike(db, DEFAULT_USER_ID, bike.id)

    content, artifact = call_tool(toolbox()["get_user_profile"], {})

    assert '"unit_system": "metric"' in content
    assert f'"id": {bike.id}' in content
    assert artifact is None


def test_trigger_research_inline_success_returns_fresh_facts(
    db, toolbox, make_bike, inline_research
):
    bike = make_bike()
    inline_research.findings = ResearchFindings(
        spec_findings=(SpecFinding("top_speed", 225.0, "km/h", "https://www.mcnews.com.au/r7"),)
    )

    content, artifact = call_tool(
        toolbox()["trigger_research"],
        {"bike_id": bike.id, "kind": "spec", "fact_keys": ["top_speed"]},
    )

    assert "Research finished" in content
    assert "top_speed: 225.0 km/h [tested]" in content
    assert artifact[0].type == "spec_card"
    assert artifact[0].facts[0].value == 225.0


def test_trigger_research_insight_success(db, toolbox, make_bike, inline_research):
    bike = make_bike()
    inline_research.findings = ResearchFindings(
        insight_findings=(InsightFinding("heat", "Barely noticeable.", (FORUM_URL,)),)
    )

    content, artifact = call_tool(
        toolbox()["trigger_research"],
        {"bike_id": bike.id, "kind": "insight", "fact_keys": ["heat"]},
    )

    assert "Research finished" in content
    assert "Barely noticeable." in content
    assert artifact[0].type == "insight_card"


def test_trigger_research_without_dispatcher_reports_background(db, toolbox, make_bike):
    bike = make_bike()

    content, artifact = call_tool(
        toolbox()["trigger_research"],
        {"bike_id": bike.id, "kind": "spec", "fact_keys": ["top_speed", "wet_weight"]},
    )

    assert "Still researching in the background" in content
    block = artifact[0]
    assert block.type == "research_pending"
    assert block.fact_keys == ["top_speed", "wet_weight"]
    assert block.kind == "spec"


def test_trigger_research_failure_is_reported_with_reason(
    db, toolbox, make_bike, inline_research
):
    bike = make_bike()
    inline_research.findings = ResearchFindings()  # provider finds nothing

    content, artifact = call_tool(
        toolbox()["trigger_research"],
        {"bike_id": bike.id, "kind": "insight", "fact_keys": ["heat"]},
    )

    assert "no_reliable_source" in content
    assert "general knowledge" in content  # the labeled-fallback permission
    assert artifact is None


def test_trigger_research_invalid_inputs(db, toolbox, make_bike):
    bike = make_bike()
    tool = toolbox()["trigger_research"]

    bad_kind, _ = call_tool(tool, {"bike_id": bike.id, "kind": "vibes", "fact_keys": ["heat"]})
    bad_key, _ = call_tool(
        tool, {"bike_id": bike.id, "kind": "spec", "fact_keys": ["warp_drive"]}
    )
    empty, _ = call_tool(tool, {"bike_id": bike.id, "kind": "spec", "fact_keys": []})

    assert bad_kind.startswith("Error:") and "vibes" in bad_kind
    assert "Invalid keys" in bad_key and "warp_drive" in bad_key
    assert empty.startswith("Error:")
