import pytest

from app.catalog.models import SourceType
from app.catalog.registry import MANUFACTURER_OFFICIAL_DOMAINS
from app.research.tiering import classify_source_tier, is_valid_source_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.yamaha-motor.eu/gb/en/products/yzf-r7/", SourceType.official),
        ("https://global.honda.com/motorcycles/", SourceType.official),
        ("https://www.cycleworld.com/yamaha-r7-dyno/", SourceType.tested),
        ("https://www.reddit.com/r/YamahaR7/", SourceType.community),
        ("https://r7forum.com/threads/heat.1/", SourceType.community),
    ],
)
def test_classify_source_tier(url, expected):
    assert classify_source_tier(url) == expected


@pytest.mark.parametrize(
    ("manufacturer", "domains"),
    sorted(MANUFACTURER_OFFICIAL_DOMAINS.items()),
)
def test_every_roster_domain_classifies_as_official(manufacturer, domains):
    assert domains, f"{manufacturer} has no official domains"
    for domain in domains:
        assert classify_source_tier(f"https://www.{domain}/models") == SourceType.official


def test_lookalike_domain_is_not_official():
    assert classify_source_tier("https://fake-yamaha-motor.eu/specs") == SourceType.community
    assert classify_source_tier("https://yamaha-motor.eu.evil.com/specs") == SourceType.community


def test_port_and_case_are_normalized():
    assert classify_source_tier("HTTPS://WWW.KTM.COM:443/models") == SourceType.official


@pytest.mark.parametrize(
    ("url", "valid"),
    [
        ("https://example.com/page", True),
        ("http://example.com", True),
        ("ftp://example.com/file", False),
        ("example.com/no-scheme", False),
        ("not a url", False),
        ("", False),
    ],
)
def test_is_valid_source_url(url, valid):
    assert is_valid_source_url(url) is valid
