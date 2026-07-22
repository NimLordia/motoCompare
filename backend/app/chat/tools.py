import functools
import json
from collections.abc import Callable

from langchain_core.tools import BaseTool, tool
from sqlalchemy.orm import Session

from app.catalog import service as catalog_service
from app.catalog.registry import INSIGHT_TOPICS, SPEC_DEFINITIONS
from app.catalog.schemas import Fact, InsightOut
from app.catalog.service import CatalogNotFoundError, CatalogValidationError
from app.chat.schemas import (
    ChatBlock,
    ComparisonTableBlock,
    DisambiguationBlock,
    InsightCardBlock,
    ResearchPendingBlock,
    SpecCardBlock,
)
from app.profile import service as profile_service
from app.research import service as research_service
from app.research.models import ResearchKind, ResearchTaskState
from app.research.service import ResearchNotFoundError, ResearchValidationError

ToolResult = tuple[str, list[ChatBlock] | None]

# resolve_bike auto-picks the top candidate only when it leads the runner-up by
# at least this much; anything closer is surfaced as a disambiguation block.
AUTO_RESOLVE_CONFIDENCE_GAP = 0.15

_SPEC_KEYS_HELP = ", ".join(definition.key for definition in SPEC_DEFINITIONS)
_TOPICS_HELP = ", ".join(INSIGHT_TOPICS)

_PENDING_RESEARCH_STATES = (ResearchTaskState.queued, ResearchTaskState.searching)


def _service_errors_as_content(fn: Callable[..., ToolResult]) -> Callable[..., ToolResult]:
    """Expected service errors become tool content the LLM can react to;
    anything unexpected propagates and fails the stream."""

    @functools.wraps(fn)
    def wrapped(*args, **kwargs) -> ToolResult:
        try:
            return fn(*args, **kwargs)
        except (
            CatalogNotFoundError,
            CatalogValidationError,
            ResearchNotFoundError,
            ResearchValidationError,
        ) as error:
            return f"Error: {error}", None

    return wrapped


def build_toolbox(
    db: Session, *, user_id: int, unit_system: str, inline_budget_seconds: float
) -> list[BaseTool]:
    """The agent's tools, bound to this request's session, user, and units."""

    @tool(
        response_format="content_and_artifact",
        description=(
            "Find catalog bikes matching a free-text reference like 'R7' or "
            "'mt-07 2024'. Returns bike ids for the other tools. If the match is "
            "ambiguous, the user is shown the candidate list — ask them to pick. "
            "Optional market filter (e.g. 'EU', 'US')."
        ),
    )
    @_service_errors_as_content
    def resolve_bike(query: str, market: str | None = None) -> ToolResult:
        candidates = catalog_service.resolve_bike(db, query, market=market)
        if not candidates:
            return (
                f'No bike matching "{query}" found in the catalog. '
                "Tell the user the bike is not in the catalog yet.",
                None,
            )
        lines = [
            f"- bike_id {candidate.bike.id}: {candidate.bike.display_name} "
            f"(confidence {candidate.confidence:.2f})"
            for candidate in candidates
        ]
        top = candidates[0]
        clear_winner = (
            len(candidates) == 1
            or top.confidence - candidates[1].confidence >= AUTO_RESOLVE_CONFIDENCE_GAP
        )
        if clear_winner:
            content = f"Resolved to bike_id {top.bike.id}: {top.bike.display_name}."
            if len(candidates) > 1:
                content += "\nOther, weaker matches:\n" + "\n".join(lines[1:])
            return content, None
        content = (
            f'"{query}" is ambiguous (the user sees the candidate list — '
            "ask them which one they mean):\n" + "\n".join(lines)
        )
        return content, [DisambiguationBlock(query=query, candidates=candidates)]

    @tool(
        response_format="content_and_artifact",
        description=(
            "Stored spec facts for one bike, in the user's units, with source "
            f"tiers. Optional keys filter; known spec keys: {_SPEC_KEYS_HELP}. "
            "Missing facts are listed — research them with trigger_research."
        ),
    )
    @_service_errors_as_content
    def get_specs(bike_id: int, keys: list[str] | None = None) -> ToolResult:
        bike = catalog_service.get_variant(db, bike_id)
        facts = catalog_service.get_specs(db, bike_id, keys=keys, unit_system=unit_system)
        present_keys = {fact.spec_key for fact in facts}
        if keys is None:
            missing = catalog_service.data_coverage(db, bike_id).core_specs_missing
        else:
            missing = [key for key in keys if key not in present_keys]
        lines = [f"Specs for {bike.display_name}:"]
        lines += [_fact_line(fact) for fact in facts]
        if not facts:
            lines.append("- no stored facts yet")
        if missing:
            lines.append(
                "Missing (call trigger_research to fill them): " + ", ".join(missing)
            )
        blocks: list[ChatBlock] | None = None
        if facts:
            blocks = [SpecCardBlock(bike=bike, facts=facts)]
            lines.append("(The user sees these as a spec card.)")
        return "\n".join(lines), blocks

    @tool(
        response_format="content_and_artifact",
        description=(
            "Side-by-side spec comparison of two or more bikes (by bike_id), in "
            "the user's units, with source tiers. Optional keys filter; the user "
            "is shown the full table."
        ),
    )
    @_service_errors_as_content
    def compare_bikes(bike_ids: list[int], keys: list[str] | None = None) -> ToolResult:
        matrix = catalog_service.compare(db, bike_ids, keys=keys, unit_system=unit_system)
        names = [bike.display_name for bike in matrix.bikes]
        lines = ["Comparison of " + " vs ".join(names) + ":"]
        gaps: list[str] = []
        for row in matrix.rows:
            cells = []
            for bike, cell in zip(matrix.bikes, row.cells, strict=True):
                if cell.missing:
                    cells.append(f"{bike.display_name}: ?")
                    gaps.append(f"{row.spec_key} for bike_id {bike.id}")
                else:
                    values = " / ".join(
                        f"{fact.value} [{fact.source_type.value}]" for fact in cell.facts
                    )
                    cells.append(f"{bike.display_name}: {values}")
            unit_note = f" ({row.unit})" if row.unit else ""
            lines.append(f"- {row.spec_key}{unit_note}: " + " | ".join(cells))
        if gaps:
            lines.append(
                "Missing (call trigger_research to fill them): " + ", ".join(gaps)
            )
        lines.append("(The user sees the full comparison table.)")
        return "\n".join(lines), [ComparisonTableBlock(matrix=matrix)]

    @tool(
        response_format="content_and_artifact",
        description=(
            "Source-linked community/tester experience for one bike, per topic. "
            f"Known topics: {_TOPICS_HELP}. Missing topics are listed — research "
            "them with trigger_research (kind 'insight')."
        ),
    )
    @_service_errors_as_content
    def get_insights(bike_id: int, topics: list[str] | None = None) -> ToolResult:
        bike = catalog_service.get_variant(db, bike_id)
        insights = catalog_service.get_insights(db, bike_id, topics=topics)
        present_topics = {insight.topic for insight in insights}
        requested = topics if topics is not None else list(INSIGHT_TOPICS)
        missing = [topic for topic in requested if topic not in present_topics]
        lines = [f"Real-world insights for {bike.display_name}:"]
        lines += [_insight_line(insight) for insight in insights]
        if not insights:
            lines.append("- no stored insights yet")
        if missing:
            lines.append(
                "Missing topics (call trigger_research with kind 'insight'): "
                + ", ".join(missing)
            )
        blocks: list[ChatBlock] | None = None
        if insights:
            blocks = [InsightCardBlock(bike=bike, insights=insights)]
            lines.append("(The user sees these as insight cards with source links.)")
        return "\n".join(lines), blocks

    @tool(
        response_format="content_and_artifact",
        description=(
            "The user's profile: preferred units, market, riding style, priorities, "
            "and their current bike (use its id when they say 'my bike')."
        ),
    )
    @_service_errors_as_content
    def get_user_profile() -> ToolResult:
        profile = profile_service.get_profile(db, user_id)
        return json.dumps(profile.model_dump(mode="json"), ensure_ascii=False), None

    @tool(
        response_format="content_and_artifact",
        description=(
            "Research missing facts for one bike: kind 'spec' with spec keys, or "
            "kind 'insight' with topics. Waits briefly for results; slower research "
            "continues in the background and the user is told where it will appear. "
            "Already-failed research is reported with its reason instead of re-run."
        ),
    )
    @_service_errors_as_content
    def trigger_research(bike_id: int, kind: str, fact_keys: list[str]) -> ToolResult:
        bike = catalog_service.get_variant(db, bike_id)
        try:
            research_kind = ResearchKind(kind)
        except ValueError:
            return f'Error: unknown research kind "{kind}" (expected "spec" or "insight").', None
        if not fact_keys:
            return "Error: fact_keys must not be empty.", None

        requested: list[str] = []
        invalid_lines: list[str] = []
        for key in fact_keys:
            try:
                research_service.request_research(db, bike_id, research_kind, key)
                requested.append(key)
            except ResearchValidationError as error:
                invalid_lines.append(f"- {key}: {error}")
        if requested:
            research_service.wait_for_research(bike_id, inline_budget_seconds)
            # Research runs on its own sessions; drop cached rows before re-reading.
            db.expire_all()

        tasks = {
            task.fact_key: task
            for task in research_service.get_tasks_for_bike(db, bike_id)
            if task.kind == research_kind
        }
        found = [key for key in requested if tasks[key].state == ResearchTaskState.found]
        pending = [key for key in requested if tasks[key].state in _PENDING_RESEARCH_STATES]
        failed = [key for key in requested if key not in found and key not in pending]

        lines: list[str] = []
        blocks: list[ChatBlock] = []
        if found:
            if research_kind is ResearchKind.spec:
                facts = catalog_service.get_specs(
                    db, bike_id, keys=found, unit_system=unit_system
                )
                blocks.append(SpecCardBlock(bike=bike, facts=facts))
                lines.append("Research finished — new values (shown to the user as a spec card):")
                lines += [_fact_line(fact) for fact in facts]
            else:
                insights = catalog_service.get_insights(db, bike_id, topics=found)
                blocks.append(InsightCardBlock(bike=bike, insights=insights))
                lines.append(
                    "Research finished — new insights (shown to the user as insight cards):"
                )
                lines += [_insight_line(insight) for insight in insights]
        if pending:
            blocks.append(
                ResearchPendingBlock(bike=bike, kind=research_kind, fact_keys=pending)
            )
            lines.append(
                "Still researching in the background (the user sees a research-pending "
                "card): " + ", ".join(pending) + ". Tell the user the results will "
                "appear on the bike's page when ready."
            )
        if failed:
            lines.append("Research found nothing usable:")
            lines += [_failure_line(key, tasks[key]) for key in failed]
            if research_kind is ResearchKind.insight:
                lines.append(
                    "You may answer these topics from general knowledge only if you "
                    'label it "(general knowledge — not yet backed by stored sources)".'
                )
        if invalid_lines:
            lines.append("Invalid keys:")
            lines += invalid_lines
        return "\n".join(lines), blocks or None

    return [
        resolve_bike,
        get_specs,
        compare_bikes,
        get_insights,
        get_user_profile,
        trigger_research,
    ]


def status_line(tool_name: str, args: dict) -> str:
    """One short progress line per tool call, streamed as a `status` event."""
    if tool_name == "resolve_bike":
        query = args.get("query", "")
        return f'Looking up "{query}"…' if query else "Resolving bikes…"
    if tool_name == "get_specs":
        return "Fetching specs…"
    if tool_name == "compare_bikes":
        return "Building the comparison…"
    if tool_name == "get_insights":
        return "Gathering owner and tester experience…"
    if tool_name == "get_user_profile":
        return "Checking your profile…"
    if tool_name == "trigger_research":
        keys = [str(key).replace("_", " ") for key in args.get("fact_keys", [])]
        return f"Researching {', '.join(keys)}…" if keys else "Researching…"
    return f"Running {tool_name}…"


def _fact_line(fact: Fact) -> str:
    unit = f" {fact.unit}" if fact.unit else ""
    return f"- {fact.spec_key}: {fact.value}{unit} [{fact.source_type.value}]"


def _insight_line(insight: InsightOut) -> str:
    source_count = len(insight.source_urls)
    plural = "s" if source_count != 1 else ""
    return (
        f"- {insight.topic} [{insight.source_type.value}, {source_count} source{plural}]: "
        f"{insight.summary}"
    )


def _failure_line(key: str, task) -> str:
    reason = task.failure_reason.value if task.failure_reason else "unknown"
    recheck = ""
    if task.recheck_after is not None:
        recheck = f"; retry possible after {task.recheck_after.date()}"
    return f"- {key}: {reason}{recheck}"
