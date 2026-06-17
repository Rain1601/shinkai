"""Source-quality filters applied to raw web_search results.

Vertex AI Grounding (Gemini + google_search) cannot natively restrict its
result domains. The 2026-06-17 quality eval surfaced a long tail of SEO
farms, opinion blogs, and pure crypto/affiliate noise that pollute the
evidence stream and cost the harness tokens to score. This module is the
single place where we hard-block those domains before they ever reach the
harness, and where we tag obvious aggregators so downstream scoring can
penalize them.

Keep the lists tight and conservative: false positives here mean we drop
legitimate evidence. Add a domain only after confirming via the eval that
it consistently returns SEO rewrites, undisclosed-paid content, or
affiliate spam.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Hard noise blocklist — pure SEO mills / affiliate spam / paywall traps that
# regurgitate SEC filings or press releases without adding signal. Results from
# these domains are dropped entirely.
NOISE_DOMAINS: frozenset[str] = frozenset(
    {
        # SEO farm regurgitating 10-K risk factors — surfaced 5x for an NVDA
        # 10-K query in the 2026-06-17 eval, all 5 the same URL.
        "holdingschannel.com",
        # AI-generated stock commentary, no original reporting.
        "intellectia.ai",
        # Crypto exchange's "news" arm — off-topic and SEO-padded for equity queries.
        "kucoin.com",
        # Paid market-research reports site, mostly behind a paywall, no
        # primary content reachable.
        "sphericalinsights.com",
        # Press-release wire republishers with no editorial filter.
        "globenewswire.com",
        "prnewswire.com",
        "businesswire.com",
        # Investing-themed content farms.
        "wallstreetzen.com",
        "wallstreetpit.com",
    }
)

# Known aggregators — they republish SEC data or press releases without adding
# original analysis. Not dropped (they sometimes carry useful pointers), but
# downstream scoring should discount them. classify_source_tier already pushes
# Yahoo/MSN/AOL into tertiary; these are additional stock-data aggregators.
AGGREGATOR_DOMAINS: frozenset[str] = frozenset(
    {
        "stocktitan.com",
        "marketbeat.com",
        "tradingview.com",
        "fool.com",
        "seekingalpha.com",
        "zacks.com",
        "gurufocus.com",
        "tipranks.com",
        "simplywall.st",
        "stockanalysis.com",
        "investing.com",
        "benzinga.com",
    }
)


def _host_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def is_noise_source(url: str, publisher: str = "") -> bool:
    """True if the URL or publisher matches the hard noise blocklist."""
    host = _host_of(url)
    pub_lower = publisher.lower().strip()
    for domain in NOISE_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return True
        if domain and domain in pub_lower:
            return True
    return False


def is_aggregator_source(url: str, publisher: str = "") -> bool:
    """True if the URL or publisher matches a known stock-data aggregator.

    Not used for filtering — flag-only, so downstream consumers can choose
    whether to penalize.
    """
    host = _host_of(url)
    pub_lower = publisher.lower().strip()
    for domain in AGGREGATOR_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return True
        if domain and domain in pub_lower:
            return True
    return False
