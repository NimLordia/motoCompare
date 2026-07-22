import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

import anthropic


@dataclass(frozen=True)
class SpecRequest:
    key: str
    display_name: str
    canonical_unit: str
    value_type: str  # "number" | "text"


@dataclass(frozen=True)
class SpecFinding:
    spec_key: str
    value: float | str
    unit: str | None
    source_url: str
    source_note: str | None = None


@dataclass(frozen=True)
class InsightFinding:
    topic: str
    summary: str
    source_urls: tuple[str, ...]


@dataclass(frozen=True)
class ResearchFindings:
    spec_findings: tuple[SpecFinding, ...] = ()
    insight_findings: tuple[InsightFinding, ...] = ()
    not_applicable_spec_keys: frozenset[str] = frozenset()
    not_applicable_topics: frozenset[str] = frozenset()
    expected_release_date: date | None = None


class ResearchExecutionError(Exception):
    """Transient execution failure (rate limit, network, provider outage).

    Never memoized as a research outcome — the task stays queued and retries with
    bounded backoff (see docs/modules/research.md, failure taxonomy).
    """


class SearchProvider(Protocol):
    def research(
        self,
        bike_description: str,
        spec_requests: Sequence[SpecRequest],
        insight_topics: Sequence[str],
    ) -> ResearchFindings: ...


_MAX_PAUSE_CONTINUATIONS = 5

_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "spec_findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "spec_key": {"type": "string"},
                    "value_number": {"type": ["number", "null"]},
                    "value_text": {"type": ["string", "null"]},
                    "unit": {"type": ["string", "null"]},
                    "source_url": {"type": "string"},
                    "source_note": {"type": ["string", "null"]},
                },
                "required": [
                    "spec_key",
                    "value_number",
                    "value_text",
                    "unit",
                    "source_url",
                    "source_note",
                ],
                "additionalProperties": False,
            },
        },
        "insight_findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "summary": {"type": "string"},
                    "source_urls": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["topic", "summary", "source_urls"],
                "additionalProperties": False,
            },
        },
        "not_applicable_spec_keys": {"type": "array", "items": {"type": "string"}},
        "not_applicable_topics": {"type": "array", "items": {"type": "string"}},
        "expected_release_date": {"type": ["string", "null"]},
    },
    "required": [
        "spec_findings",
        "insight_findings",
        "not_applicable_spec_keys",
        "not_applicable_topics",
        "expected_release_date",
    ],
    "additionalProperties": False,
}


class ClaudeSearchProvider:
    """Research via the Claude API in two phases.

    Phase 1 uses the server-side web search tool to gather source-cited notes —
    one pass mines every requested fact, which is what makes populating a bike
    cost a few searches instead of one per fact. Phase 2 extracts typed findings
    from those notes with a structured-output call, so parsing never depends on
    free-form text.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-opus-4-8",
        max_web_searches: int = 8,
    ):
        self._api_key = api_key
        self._model = model
        self._max_web_searches = max_web_searches
        self._client: anthropic.Anthropic | None = None

    def research(
        self,
        bike_description: str,
        spec_requests: Sequence[SpecRequest],
        insight_topics: Sequence[str],
    ) -> ResearchFindings:
        notes = self._search(bike_description, spec_requests, insight_topics)
        payload = self._extract(bike_description, notes, spec_requests, insight_topics)
        return findings_from_payload(payload)

    def _get_client(self) -> anthropic.Anthropic:
        # Created lazily so the app can boot without credentials; without an explicit
        # key the SDK resolves ANTHROPIC_API_KEY (and friends) itself.
        if self._client is None:
            kwargs = {"api_key": self._api_key} if self._api_key else {}
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def _create_message(self, **kwargs: Any) -> Any:
        try:
            return self._get_client().messages.create(
                model=self._model, thinking={"type": "adaptive"}, **kwargs
            )
        except anthropic.AnthropicError as error:
            raise ResearchExecutionError(f"claude api call failed: {error}") from error

    def _search(
        self,
        bike_description: str,
        spec_requests: Sequence[SpecRequest],
        insight_topics: Sequence[str],
    ) -> str:
        web_search_tool = {
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": self._max_web_searches,
        }
        prompt = search_prompt(bike_description, spec_requests, insight_topics)
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        for _ in range(_MAX_PAUSE_CONTINUATIONS):
            response = self._create_message(
                max_tokens=16000, tools=[web_search_tool], messages=messages
            )
            if response.stop_reason != "pause_turn":
                break
            # The server-side search loop paused mid-turn; re-send with the partial
            # assistant turn appended and it resumes where it left off.
            messages = [*messages, {"role": "assistant", "content": response.content}]
        else:
            raise ResearchExecutionError("web search kept pausing without completing")
        if response.stop_reason == "refusal":
            raise ResearchExecutionError("search request was refused")
        notes = _joined_text(response)
        if not notes.strip():
            raise ResearchExecutionError("search produced no notes")
        return notes

    def _extract(
        self,
        bike_description: str,
        notes: str,
        spec_requests: Sequence[SpecRequest],
        insight_topics: Sequence[str],
    ) -> dict[str, Any]:
        response = self._create_message(
            max_tokens=16000,
            output_config={"format": {"type": "json_schema", "schema": _EXTRACTION_SCHEMA}},
            messages=[
                {
                    "role": "user",
                    "content": extraction_prompt(
                        bike_description, notes, spec_requests, insight_topics
                    ),
                }
            ],
        )
        if response.stop_reason == "max_tokens":
            raise ResearchExecutionError("extraction output was truncated")
        if response.stop_reason == "refusal":
            raise ResearchExecutionError("extraction request was refused")
        try:
            payload = json.loads(_joined_text(response))
        except json.JSONDecodeError as error:
            raise ResearchExecutionError(f"extraction returned invalid JSON: {error}") from error
        if not isinstance(payload, dict):
            raise ResearchExecutionError("extraction returned a non-object payload")
        return payload


def search_prompt(
    bike_description: str,
    spec_requests: Sequence[SpecRequest],
    insight_topics: Sequence[str],
) -> str:
    lines = [f"Research the motorcycle: {bike_description}.", ""]
    if spec_requests:
        lines.append(
            "Quantitative specifications to find (value + unit + exact source URL for each):"
        )
        for request in spec_requests:
            unit_note = (
                f", typically reported in {request.canonical_unit}"
                if request.canonical_unit
                else ""
            )
            lines.append(f"- {request.key}: {request.display_name}{unit_note}")
        lines.append("")
    if insight_topics:
        lines.append(
            "Qualitative topics to research from real owner and tester experience"
            " (owner forums, subreddits, owner reviews, long-term tests)."
            " For each, write a 2-4 sentence summary grounded ONLY in what the sources"
            " actually say, and list every source URL used:"
        )
        lines.extend(f"- {topic}" for topic in insight_topics)
        lines.append("")
    lines.extend(
        [
            "Rules:",
            "- Report only what a source explicitly states, with the exact page URL."
            " Never estimate or fill gaps from memory.",
            "- Prefer the manufacturer's official specification page; mine it for every"
            " listed spec it contains before searching further. Also report independently"
            " measured values (dyno or instrumented road tests) when you find them, as"
            " separate entries with their own URLs.",
            '- If you cannot find a trustworthy source for an item, write "NOT FOUND: <item>".',
            '- If an item does not exist for this motorcycle, write "NOT APPLICABLE: <item>".',
            "- If the motorcycle has been announced but not yet released, say so and give"
            " the expected release date if known.",
        ]
    )
    return "\n".join(lines)


def extraction_prompt(
    bike_description: str,
    notes: str,
    spec_requests: Sequence[SpecRequest],
    insight_topics: Sequence[str],
) -> str:
    spec_lines = [
        f"- {request.key} ({request.value_type})" for request in spec_requests
    ] or ["- (none)"]
    topic_lines = [f"- {topic}" for topic in insight_topics] or ["- (none)"]
    return "\n".join(
        [
            f"Below are research notes about {bike_description}."
            " Extract structured findings from them.",
            "",
            "Allowed spec keys:",
            *spec_lines,
            "",
            "Allowed insight topics:",
            *topic_lines,
            "",
            "Rules:",
            "- Include a spec finding only when the notes state a concrete value WITH a"
            " source URL. Emit one finding per (value, source) pair, so several sources"
            " for the same key become several findings.",
            "- Use value_number for numeric keys with unit exactly as stated in the notes;"
            " use value_text for text keys with unit null.",
            "- Include an insight finding only when the notes contain a grounded summary"
            " with at least one source URL.",
            "- Put keys or topics the notes mark NOT APPLICABLE in the corresponding"
            " lists. NOT FOUND items are simply omitted.",
            "- Set expected_release_date (YYYY-MM-DD) only if the notes say the bike is"
            " not yet released; otherwise null.",
            "- Never add facts from your own knowledge; only extract from the notes.",
            "",
            "Research notes:",
            '"""',
            notes,
            '"""',
        ]
    )


def findings_from_payload(payload: dict[str, Any]) -> ResearchFindings:
    spec_findings = tuple(
        finding
        for item in _list_of(payload, "spec_findings")
        if (finding := _spec_finding_from_item(item)) is not None
    )
    insight_findings = tuple(
        finding
        for item in _list_of(payload, "insight_findings")
        if (finding := _insight_finding_from_item(item)) is not None
    )
    return ResearchFindings(
        spec_findings=spec_findings,
        insight_findings=insight_findings,
        not_applicable_spec_keys=_string_set(payload, "not_applicable_spec_keys"),
        not_applicable_topics=_string_set(payload, "not_applicable_topics"),
        expected_release_date=_parse_date(payload.get("expected_release_date")),
    )


def _spec_finding_from_item(item: Any) -> SpecFinding | None:
    if not isinstance(item, dict):
        return None
    spec_key = item.get("spec_key")
    source_url = item.get("source_url")
    if not isinstance(spec_key, str) or not spec_key.strip():
        return None
    if not isinstance(source_url, str) or not source_url.strip():
        return None
    value_number = item.get("value_number")
    value_text = item.get("value_text")
    value: float | str
    if isinstance(value_number, int | float) and not isinstance(value_number, bool):
        value = float(value_number)
    elif isinstance(value_text, str) and value_text.strip():
        value = value_text.strip()
    else:
        return None
    return SpecFinding(
        spec_key=spec_key.strip(),
        value=value,
        unit=_clean_string(item.get("unit")),
        source_url=source_url.strip(),
        source_note=_clean_string(item.get("source_note")),
    )


def _insight_finding_from_item(item: Any) -> InsightFinding | None:
    if not isinstance(item, dict):
        return None
    topic = item.get("topic")
    summary = item.get("summary")
    if not isinstance(topic, str) or not topic.strip():
        return None
    if not isinstance(summary, str) or not summary.strip():
        return None
    raw_urls = item.get("source_urls")
    urls = tuple(
        url.strip()
        for url in (raw_urls if isinstance(raw_urls, list) else [])
        if isinstance(url, str) and url.strip()
    )
    return InsightFinding(topic=topic.strip(), summary=summary.strip(), source_urls=urls)


def _joined_text(response: Any) -> str:
    return "".join(block.text for block in response.content if block.type == "text")


def _list_of(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _string_set(payload: dict[str, Any], key: str) -> frozenset[str]:
    return frozenset(
        item.strip()
        for item in _list_of(payload, key)
        if isinstance(item, str) and item.strip()
    )


def _clean_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None
