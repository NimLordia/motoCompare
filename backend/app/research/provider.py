import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types


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


# Grounding chunks cite pages through these hosts; anything else is a direct URL.
_GROUNDING_REDIRECT_HOSTS = ("vertexaisearch.cloud.google.com",)

# Gemini's response_schema takes the OpenAPI subset: nullable flags instead of
# ["type", "null"] unions, and no additionalProperties.
_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "spec_findings": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "spec_key": {"type": "STRING"},
                    "value_number": {"type": "NUMBER", "nullable": True},
                    "value_text": {"type": "STRING", "nullable": True},
                    "unit": {"type": "STRING", "nullable": True},
                    "source_url": {"type": "STRING"},
                    "source_note": {"type": "STRING", "nullable": True},
                },
                "required": ["spec_key", "source_url"],
            },
        },
        "insight_findings": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "topic": {"type": "STRING"},
                    "summary": {"type": "STRING"},
                    "source_urls": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
                "required": ["topic", "summary", "source_urls"],
            },
        },
        "not_applicable_spec_keys": {"type": "ARRAY", "items": {"type": "STRING"}},
        "not_applicable_topics": {"type": "ARRAY", "items": {"type": "STRING"}},
        "expected_release_date": {"type": "STRING", "nullable": True},
    },
    "required": [
        "spec_findings",
        "insight_findings",
        "not_applicable_spec_keys",
        "not_applicable_topics",
    ],
}


class GeminiSearchProvider:
    """Research via the Gemini API in two phases.

    Phase 1 grounds a research pass in Google Search — one pass mines every
    requested fact, which is what makes populating a bike cost a few searches
    instead of one per fact. Grounded citations arrive as metadata with expiring
    Google redirect URLs, so the provider inserts [n] citation markers into the
    notes and resolves each redirect to the real page URL in a "Sources
    consulted" list. Phase 2 extracts typed findings from those notes with a
    JSON-schema constrained call; source URLs are copied from the verified list,
    never from model memory.
    """

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash"):
        self._api_key = api_key
        self._model = model
        self._client: genai.Client | None = None
        self._http: httpx.Client | None = None

    def research(
        self,
        bike_description: str,
        spec_requests: Sequence[SpecRequest],
        insight_topics: Sequence[str],
    ) -> ResearchFindings:
        notes = self._search(bike_description, spec_requests, insight_topics)
        payload = self._extract(bike_description, notes, spec_requests, insight_topics)
        return findings_from_payload(payload)

    def _get_client(self) -> genai.Client:
        # Created lazily so the app can boot without credentials; without an explicit
        # key the SDK resolves GEMINI_API_KEY / GOOGLE_API_KEY itself.
        if self._client is None:
            kwargs = {"api_key": self._api_key} if self._api_key else {}
            self._client = genai.Client(**kwargs)
        return self._client

    def _get_http(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=10.0)
        return self._http

    def _generate(self, contents: str, config: genai_types.GenerateContentConfig) -> Any:
        try:
            return self._get_client().models.generate_content(
                model=self._model, contents=contents, config=config
            )
        except (genai_errors.APIError, httpx.HTTPError) as error:
            raise ResearchExecutionError(f"gemini api call failed: {error}") from error

    def _search(
        self,
        bike_description: str,
        spec_requests: Sequence[SpecRequest],
        insight_topics: Sequence[str],
    ) -> str:
        response = self._generate(
            contents=search_prompt(bike_description, spec_requests, insight_topics),
            config=genai_types.GenerateContentConfig(
                tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())]
            ),
        )
        notes = response.text or ""
        if not notes.strip():
            raise ResearchExecutionError("search produced no notes")
        chunks, supports = _grounding_metadata(response)
        notes = _insert_citation_markers(notes, supports)
        sources = self._resolved_sources(chunks)
        if chunks and not sources:
            # Sources existed but none resolved — an infrastructure problem, not
            # knowledge about the bike; retry instead of memoizing not_found.
            raise ResearchExecutionError("no grounding source URL could be resolved")
        if sources:
            source_lines = [f"[{index}] {title} — {url}" for index, title, url in sources]
            notes = "\n".join([notes, "", "Sources consulted:", *source_lines])
        return notes

    def _resolved_sources(self, chunks: list[Any]) -> list[tuple[int, str, str]]:
        sources = []
        for index, chunk in enumerate(chunks, start=1):
            web = getattr(chunk, "web", None)
            if web is None or not web.uri:
                continue
            url = self._resolve_redirect(web.uri)
            if url is None:
                continue
            sources.append((index, web.title or url, url))
        return sources

    def _resolve_redirect(self, url: str) -> str | None:
        """Recover the real page URL behind a grounding redirect.

        The redirect links expire and hide the cited domain, which would break
        both provenance and tier classification. One non-following HEAD request
        to Google reads the Location header without ever hitting the cited site.
        """
        host = urlparse(url).netloc.lower()
        if not any(
            host == redirect_host or host.endswith("." + redirect_host)
            for redirect_host in _GROUNDING_REDIRECT_HOSTS
        ):
            return url
        try:
            response = self._get_http().head(url)
        except httpx.HTTPError:
            return None
        return response.headers.get("location") or None

    def _extract(
        self,
        bike_description: str,
        notes: str,
        spec_requests: Sequence[SpecRequest],
        insight_topics: Sequence[str],
    ) -> dict[str, Any]:
        response = self._generate(
            contents=extraction_prompt(bike_description, notes, spec_requests, insight_topics),
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_EXTRACTION_SCHEMA,
            ),
        )
        try:
            payload = json.loads(response.text or "")
        except json.JSONDecodeError as error:
            raise ResearchExecutionError(f"extraction returned invalid JSON: {error}") from error
        if not isinstance(payload, dict):
            raise ResearchExecutionError("extraction returned a non-object payload")
        return payload


def _grounding_metadata(response: Any) -> tuple[list[Any], list[Any]]:
    candidates = response.candidates or []
    metadata = candidates[0].grounding_metadata if candidates else None
    if metadata is None:
        return [], []
    return list(metadata.grounding_chunks or []), list(metadata.grounding_supports or [])


def _insert_citation_markers(text: str, supports: list[Any]) -> str:
    """Attach [n] markers (1-based grounding-chunk indices) to the cited segments,
    working back-to-front so earlier offsets stay valid."""
    anchored = [
        support
        for support in supports
        if support.segment is not None
        and support.segment.end_index is not None
        and support.grounding_chunk_indices
    ]
    for support in sorted(anchored, key=lambda s: s.segment.end_index, reverse=True):
        marker = "".join(f"[{index + 1}]" for index in support.grounding_chunk_indices)
        end = support.segment.end_index
        text = text[:end] + marker + text[end:]
    return text


def search_prompt(
    bike_description: str,
    spec_requests: Sequence[SpecRequest],
    insight_topics: Sequence[str],
) -> str:
    lines = [f"Research the motorcycle: {bike_description}.", ""]
    if spec_requests:
        lines.append("Quantitative specifications to find (value + unit for each):")
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
            " actually say:"
        )
        lines.extend(f"- {topic}" for topic in insight_topics)
        lines.append("")
    lines.extend(
        [
            "Rules:",
            "- Ground every statement in web search results. Report only what a source"
            " explicitly states; never estimate or fill gaps from memory.",
            "- Prefer the manufacturer's official specification page; mine it for every"
            " listed spec it contains before searching further. Also report independently"
            " measured values (dyno or instrumented road tests) when you find them, as"
            " separate entries.",
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
            "- The notes cite sources with [n] markers that refer to the numbered"
            ' "Sources consulted" list at the end. source_url must be copied exactly'
            " from that list — the entry whose marker is attached to the fact.",
            "- Include a spec finding only when the notes state a concrete value WITH a"
            " citation marker. Emit one finding per (value, source) pair, so several"
            " sources for the same key become several findings.",
            "- Use value_number for numeric keys with unit exactly as stated in the notes;"
            " use value_text for text keys with unit null.",
            "- Include an insight finding only when the notes contain a grounded summary,"
            " and list every cited source URL for it.",
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
