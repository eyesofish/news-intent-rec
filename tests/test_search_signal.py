from __future__ import annotations

import pytest

from backend.app.repositories.search_signal import (
    LEGACY_SEARCH_CONFIG,
    SEARCH_SIGNAL_CONFIGS,
    query_can_open_recall,
    recent_query_multiplier,
)
from backend.app.schemas.profile import ProfileRecentQuery


def test_mmr_arm_reuses_legacy_search_signal():
    assert SEARCH_SIGNAL_CONFIGS["lgb_plus_als_plus_search_mmr"] is LEGACY_SEARCH_CONFIG


def test_legacy_search_signal_does_not_decay():
    query = ProfileRecentQuery(query_key="1", query_ts=100)

    assert recent_query_multiplier(query, now_ts=100_000, config=LEGACY_SEARCH_CONFIG) == 1.0


def test_decay_search_signal_halves_and_expires():
    config = SEARCH_SIGNAL_CONFIGS["lgb_plus_als_plus_search_decay_30m"]
    query = ProfileRecentQuery(query_key="1", query_ts=100)

    assert recent_query_multiplier(query, now_ts=100 + 30 * 60, config=config) == pytest.approx(0.5)
    assert recent_query_multiplier(query, now_ts=100 + 121 * 60, config=config) == 0.0


def test_confirmed_query_uses_longer_half_life_and_multiplier():
    config = SEARCH_SIGNAL_CONFIGS["lgb_plus_als_plus_search_gated_30m_4h"]
    query = ProfileRecentQuery(query_key="1", query_ts=100, confirmed_ts=200)

    assert recent_query_multiplier(query, now_ts=200, config=config) == 2.0
    assert recent_query_multiplier(
        query,
        now_ts=200 + 4 * 60 * 60,
        config=config,
    ) == pytest.approx(1.0)


def test_gated_query_opens_recall_only_after_confirmation():
    config = SEARCH_SIGNAL_CONFIGS["lgb_plus_als_plus_search_gated_30m_4h"]

    assert not query_can_open_recall(
        ProfileRecentQuery(query_key="1", query_ts=100),
        config=config,
    )
    assert query_can_open_recall(
        ProfileRecentQuery(query_key="1", query_ts=100, confirmed_ts=200),
        config=config,
    )
