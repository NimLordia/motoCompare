import json
from datetime import date
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors

from app.research.provider import (
    GeminiSearchProvider,
    ResearchExecutionError,
    SpecRequest,
    findings_from_payload,
)

SPEC_REQUESTS = [
    SpecRequest("power_peak", "Peak power", "kW", "number"),
    SpecRequest("engine_type", "Engine type", "", "text"),
]
TOPICS = ["heat"]

OFFICIAL_URL = "https://www.yamaha-motor.eu/gb/en/products/motorcycles/yzf-r7/"
REDIRECT_URL = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc123"

EXTRACTION_PAYLOAD = {
    "spec_findings": [
        {
            "spec_key": "power_peak",
            "value_number": 54.0,
            "value_text": None,
            "unit": "kW",
            "source_url": OFFICIAL_URL,
            "source_note": None,
        },
        {
            "spec_key": "engine_type",
            "value_number": None,
            "value_text": "Parallel twin",
            "unit": None,
            "source_url": OFFICIAL_URL,
            "source_note": None,
        },
    ],
    "insight_findings": [
        {
            "topic": "heat",
            "summary": "Owners report mild heat.",
            "source_urls": ["https://www.r7forum.com/threads/1/"],
        }
    ],
    "not_applicable_spec_keys": ["top_speed"],
    "not_applicable_topics": [],
    "expected_release_date": None,
}


def _web_chunk(uri, title="Source"):
    return SimpleNamespace(web=SimpleNamespace(uri=uri, title=title))


def _support(end_index, chunk_indices):
    return SimpleNamespace(
        segment=SimpleNamespace(end_index=end_index),
        grounding_chunk_indices=chunk_indices,
    )


def _grounded_response(text, chunks=(), supports=()):
    metadata = SimpleNamespace(
        grounding_chunks=list(chunks), grounding_supports=list(supports)
    )
    return SimpleNamespace(
        text=text, candidates=[SimpleNamespace(grounding_metadata=metadata)]
    )


def _plain_response(text):
    return SimpleNamespace(text=text, candidates=[])


class FakeModels:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeHttp:
    """Stub httpx client: head() returns a Location header per redirect URL."""

    def __init__(self, locations=None, error=None):
        self._locations = locations or {}
        self._error = error
        self.requested: list[str] = []

    def head(self, url):
        self.requested.append(url)
        if self._error is not None:
            raise self._error
        return SimpleNamespace(headers={"location": self._locations.get(url, "")})


def _provider_with(responses, http=None):
    provider = GeminiSearchProvider(api_key="test-key")
    models = FakeModels(responses)
    provider._client = SimpleNamespace(models=models)
    provider._http = http or FakeHttp()
    return provider, models


def test_two_phase_research_returns_parsed_findings():
    notes = "The R7 makes 54 kW according to the official page."
    provider, models = _provider_with(
        [
            _grounded_response(
                notes,
                chunks=[_web_chunk(OFFICIAL_URL, "Yamaha YZF-R7")],
                supports=[_support(len(notes), [0])],
            ),
            _plain_response(json.dumps(EXTRACTION_PAYLOAD)),
        ]
    )

    findings = provider.research("Yamaha YZF-R7 2023", SPEC_REQUESTS, TOPICS)

    assert {finding.spec_key for finding in findings.spec_findings} == {
        "power_peak",
        "engine_type",
    }
    assert findings.insight_findings[0].topic == "heat"
    assert findings.not_applicable_spec_keys == frozenset({"top_speed"})

    search_call, extract_call = models.calls
    assert search_call["config"].tools[0].google_search is not None
    assert extract_call["config"].response_mime_type == "application/json"
    assert extract_call["config"].response_schema is not None
    # Phase two sees the notes with citation markers plus the verified source list.
    extract_contents = extract_call["contents"]
    assert "54 kW" in extract_contents
    assert "[1]" in extract_contents
    assert f"[1] Yamaha YZF-R7 — {OFFICIAL_URL}" in extract_contents


def test_grounding_redirects_are_resolved_without_visiting_the_site():
    notes = "Peak power is 54 kW."
    http = FakeHttp(locations={REDIRECT_URL: OFFICIAL_URL})
    provider, models = _provider_with(
        [
            _grounded_response(notes, chunks=[_web_chunk(REDIRECT_URL)]),
            _plain_response(json.dumps(EXTRACTION_PAYLOAD)),
        ],
        http=http,
    )

    provider.research("Yamaha YZF-R7 2023", SPEC_REQUESTS, TOPICS)

    assert http.requested == [REDIRECT_URL]
    assert OFFICIAL_URL in models.calls[1]["contents"]
    assert REDIRECT_URL not in models.calls[1]["contents"]


def test_direct_source_urls_skip_resolution():
    http = FakeHttp()
    provider, _ = _provider_with(
        [
            _grounded_response("notes", chunks=[_web_chunk(OFFICIAL_URL)]),
            _plain_response(json.dumps(EXTRACTION_PAYLOAD)),
        ],
        http=http,
    )

    provider.research("Yamaha YZF-R7 2023", SPEC_REQUESTS, TOPICS)

    assert http.requested == []


def test_unresolvable_sources_are_an_execution_error():
    import httpx

    http = FakeHttp(error=httpx.ConnectError("no network"))
    provider, _ = _provider_with(
        [_grounded_response("notes", chunks=[_web_chunk(REDIRECT_URL)])], http=http
    )

    with pytest.raises(ResearchExecutionError):
        provider.research("Yamaha YZF-R7 2023", SPEC_REQUESTS, TOPICS)


def test_ungrounded_notes_pass_through_without_source_list():
    provider, models = _provider_with(
        [
            _plain_response("NOT FOUND: everything"),
            _plain_response(json.dumps(EXTRACTION_PAYLOAD)),
        ]
    )

    provider.research("Yamaha YZF-R7 2023", SPEC_REQUESTS, TOPICS)

    # The rules text mentions the list by name; only the appendix header itself
    # must be absent.
    assert "Sources consulted:" not in models.calls[1]["contents"]


def test_citation_markers_land_after_their_segments():
    notes = "Power is 54 kW. Weight is 188 kg."
    provider, models = _provider_with(
        [
            _grounded_response(
                notes,
                chunks=[_web_chunk(OFFICIAL_URL), _web_chunk("https://www.cycleworld.com/r7/")],
                supports=[_support(15, [0]), _support(len(notes), [1])],
            ),
            _plain_response(json.dumps(EXTRACTION_PAYLOAD)),
        ]
    )

    provider.research("Yamaha YZF-R7 2023", SPEC_REQUESTS, TOPICS)

    assert "Power is 54 kW.[1] Weight is 188 kg.[2]" in models.calls[1]["contents"]


def test_api_errors_map_to_execution_error():
    provider, _ = _provider_with(
        [genai_errors.APIError(429, {"error": {"message": "quota exceeded"}})]
    )

    with pytest.raises(ResearchExecutionError):
        provider.research("Yamaha YZF-R7 2023", SPEC_REQUESTS, TOPICS)


def test_empty_search_notes_are_an_execution_error():
    provider, _ = _provider_with([_plain_response("   ")])

    with pytest.raises(ResearchExecutionError):
        provider.research("Yamaha YZF-R7 2023", SPEC_REQUESTS, TOPICS)


def test_invalid_extraction_json_is_an_execution_error():
    provider, _ = _provider_with(
        [_plain_response("notes"), _plain_response("not json at all")]
    )

    with pytest.raises(ResearchExecutionError):
        provider.research("Yamaha YZF-R7 2023", SPEC_REQUESTS, TOPICS)


def test_findings_from_payload_drops_malformed_items():
    findings = findings_from_payload(
        {
            "spec_findings": [
                {"spec_key": "power_peak", "value_number": 54.0, "source_url": ""},
                {"spec_key": "power_peak", "value_number": True, "source_url": "https://x.com"},
                {"spec_key": "", "value_number": 54.0, "source_url": "https://x.com"},
                "not a dict",
                {"spec_key": "power_peak", "value_number": 54.0, "source_url": "https://x.com"},
            ],
            "insight_findings": [
                {"topic": "heat", "summary": "", "source_urls": ["https://x.com"]},
                {"topic": "heat", "summary": "ok", "source_urls": "https://x.com"},
            ],
            "not_applicable_spec_keys": ["top_speed", 42, "  "],
            "not_applicable_topics": None,
            "expected_release_date": "2027-03-01",
        }
    )

    assert len(findings.spec_findings) == 1
    assert findings.spec_findings[0].value == 54.0
    # An insight with a malformed source list survives with no URLs; the runner
    # then refuses to store it.
    assert findings.insight_findings[0].source_urls == ()
    assert findings.not_applicable_spec_keys == frozenset({"top_speed"})
    assert findings.expected_release_date == date(2027, 3, 1)


def test_findings_from_payload_tolerates_missing_sections():
    findings = findings_from_payload({})

    assert findings.spec_findings == ()
    assert findings.insight_findings == ()
    assert findings.expected_release_date is None
