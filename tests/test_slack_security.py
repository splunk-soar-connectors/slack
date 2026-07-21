# Copyright (c) 2016-2026 Splunk Inc.

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from slack_security import sanitize_slack_markup


def test_sanitize_slack_markup_unwraps_links():
    assert sanitize_slack_markup("see <https://example.com|example>") == "see example"
    assert sanitize_slack_markup("see <https://example.com>") == "see https://example.com"


def test_sanitize_slack_markup_returns_when_closing_bracket_precedes_opening():
    assert sanitize_slack_markup("get_container > <") == "get_container > <"


def test_sanitize_slack_markup_handles_a_valid_link_after_a_raw_closing_bracket():
    assert sanitize_slack_markup("a > b <https://example.com|example>") == "a > b example"
