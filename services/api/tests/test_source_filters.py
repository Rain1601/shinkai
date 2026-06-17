from __future__ import annotations

from shinkai_api.tools.source_filters import (
    AGGREGATOR_DOMAINS,
    NOISE_DOMAINS,
    is_aggregator_source,
    is_noise_source,
)


def test_noise_domains_recognized() -> None:
    assert is_noise_source("https://holdingschannel.com/risk-factors/nvda-risk-factors/")
    assert is_noise_source("https://www.intellectia.ai/blog/x")
    assert is_noise_source("https://www.kucoin.com/news/x")
    assert is_noise_source("https://sphericalinsights.com/reports/x")
    # press-release wires
    assert is_noise_source("https://www.prnewswire.com/news-releases/x")
    assert is_noise_source("https://www.globenewswire.com/x")


def test_noise_negatives_pass_through() -> None:
    assert not is_noise_source("https://www.sec.gov/Archives/edgar/data/x")
    assert not is_noise_source("https://www.bloomberg.com/news/x", "Bloomberg")
    assert not is_noise_source("https://news.skhynix.com/x")
    assert not is_noise_source("https://semianalysis.com/p/hbm")
    assert not is_noise_source("")


def test_aggregator_flag() -> None:
    assert is_aggregator_source("https://stocktitan.com/nasdaq/CAMT/sec-filings/")
    assert is_aggregator_source("https://www.marketbeat.com/stocks/NASDAQ/CAMT/sec-filings/")
    assert is_aggregator_source("https://seekingalpha.com/news/x")
    assert is_aggregator_source("https://www.fool.com/investing/x")
    # not aggregators
    assert not is_aggregator_source("https://www.sec.gov/Archives/edgar/data/x")
    assert not is_aggregator_source("https://semianalysis.com/p/hbm")


def test_noise_via_publisher_string() -> None:
    # Some search backends return only `source=` without a clean URL host.
    assert is_noise_source("https://example.com/x", "holdingschannel.com")
    assert is_aggregator_source("https://example.com/x", "Seeking Alpha (seekingalpha.com)")


def test_blocklist_and_aggregator_sets_disjoint() -> None:
    # A domain should not be both hard-blocked and aggregator-flagged — they
    # encode different intents (drop vs flag).
    assert not (NOISE_DOMAINS & AGGREGATOR_DOMAINS)
