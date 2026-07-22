from urllib.parse import urlparse

from app.catalog.models import SourceType

# Domain → tier map (code config, per docs/modules/research.md). Matching is by
# registrable domain: "www.yamaha-motor.eu" and "yamaha-motor.eu" both count.
# Anything with a valid URL that matches neither list is community-tier.

OFFICIAL_DOMAINS: frozenset[str] = frozenset({
    "aprilia.com",
    "bmw-motorrad.com",
    "bmw-motorrad.de",
    "cfmoto.com",
    "ducati.com",
    "harley-davidson.com",
    "honda.co.uk",
    "honda.com",
    "husqvarna-motorcycles.com",
    "indianmotorcycle.com",
    "kawasaki.com",
    "kawasaki.eu",
    "ktm.com",
    "motoguzzi.com",
    "mvagusta.com",
    "piaggio.com",
    "royalenfield.com",
    "suzuki.com",
    "suzukicycles.com",
    "triumphmotorcycles.co.uk",
    "triumphmotorcycles.com",
    "vespa.com",
    "yamaha-motor.com",
    "yamaha-motor.eu",
    "yamahamotorsports.com",
    "zeromotorcycles.com",
})

TESTED_DOMAINS: frozenset[str] = frozenset({
    "asphaltandrubber.com",
    "bennetts.co.uk",
    "cycleworld.com",
    "mcnews.com.au",
    "motociclismo.es",
    "motorcycle.com",
    "motorcyclenews.com",
    "motorcyclistonline.com",
    "motorrad-online.de",
    "rideapart.com",
    "roadracingworld.com",
    "visordown.com",
})


def is_valid_source_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def classify_source_tier(url: str) -> SourceType:
    domain = _registrable_domain(url)
    if domain is None:
        return SourceType.community
    if _matches_any(domain, OFFICIAL_DOMAINS):
        return SourceType.official
    if _matches_any(domain, TESTED_DOMAINS):
        return SourceType.tested
    return SourceType.community


def _registrable_domain(url: str) -> str | None:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().rsplit("@", 1)[-1].split(":", 1)[0]
    return host or None


def _matches_any(host: str, domains: frozenset[str]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)
