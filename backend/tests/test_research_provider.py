import json
from datetime import date
from types import SimpleNamespace

import anthropic
import pytest

from app.research.provider import (
    ClaudeSearchProvider,
    ResearchExecutionError,
    SpecRequest,
    findings_from_payload,
)

SPEC_REQUESTS = [
    SpecRequest("power_peak", "Peak power", "kW", "number"),
    SpecRequest("engine_type", "Engine type", "", "text"),
]
TOPICS = ["heat"]

EXTRACTION_PAYLOAD = {
    "spec_findings": [
        {
            "spec_key": "power_peak",
            "value_number": 54.0,
            "value_text": None,
            "unit": "kW",
            "source_url": "https://www.yamaha-motor.eu/",
            "source_note": None,
        },
        {
            "spec_key": "engine_type",
            "value_number": None,
            "value_text": "Parallel twin",
            "unit": None,
            "source_url": "https://www.yamaha-motor.eu/",
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


def _text_response(text, stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)]
    )


class FakeMessages:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _provider_with(responses):
    provider = ClaudeSearchProvider(api_key="test-key")
    messages = FakeMessages(responses)
    provider._client = SimpleNamespace(messages=messages)
    return provider, messages


def test_two_phase_research_returns_parsed_findings():
    provider, messages = _provider_with(
        [
            _text_response("power_peak: 54 kW per https://www.yamaha-motor.eu/ ..."),
            _text_response(json.dumps(EXTRACTION_PAYLOAD)),
        ]
    )

    findings = provider.research("Yamaha YZF-R7 2023", SPEC_REQUESTS, TOPICS)

    assert {finding.spec_key for finding in findings.spec_findings} == {
        "power_peak",
        "engine_type",
    }
    assert findings.insight_findings[0].topic == "heat"
    assert findings.not_applicable_spec_keys == frozenset({"top_speed"})

    search_call, extract_call = messages.calls
    assert search_call["tools"][0]["type"] == "web_search_20260209"
    assert extract_call["output_config"]["format"]["type"] == "json_schema"
    # The notes from phase one are what phase two extracts from.
    assert "54 kW" in extract_call["messages"][0]["content"]


def test_pause_turn_is_resumed():
    paused = SimpleNamespace(
        stop_reason="pause_turn", content=[SimpleNamespace(type="text", text="partial")]
    )
    provider, messages = _provider_with(
        [
            paused,
            _text_response("notes after resume"),
            _text_response(json.dumps(EXTRACTION_PAYLOAD)),
        ]
    )

    provider.research("Yamaha YZF-R7 2023", SPEC_REQUESTS, TOPICS)

    assert len(messages.calls) == 3
    resumed_messages = messages.calls[1]["messages"]
    assert resumed_messages[-1]["role"] == "assistant"


def test_api_errors_map_to_execution_error():
    provider, _ = _provider_with([anthropic.AnthropicError("provider outage")])

    with pytest.raises(ResearchExecutionError):
        provider.research("Yamaha YZF-R7 2023", SPEC_REQUESTS, TOPICS)


def test_empty_search_notes_are_an_execution_error():
    provider, _ = _provider_with([_text_response("   ")])

    with pytest.raises(ResearchExecutionError):
        provider.research("Yamaha YZF-R7 2023", SPEC_REQUESTS, TOPICS)


def test_invalid_extraction_json_is_an_execution_error():
    provider, _ = _provider_with(
        [_text_response("notes"), _text_response("not json at all")]
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
