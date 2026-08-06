# Copyright (c) 2016-2026 Splunk Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under
# the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
# either express or implied. See the License for the specific language governing permissions
# and limitations under the License.

from src.interactive import sanitize_slack_markup


def test_sanitize_slack_markup_unwraps_links():
    assert sanitize_slack_markup("see <https://example.com|example>") == "see example"
    assert (
        sanitize_slack_markup("see <https://example.com>") == "see https://example.com"
    )


def test_sanitize_slack_markup_returns_when_closing_bracket_precedes_opening():
    assert sanitize_slack_markup("get_container > <") == "get_container > <"


def test_sanitize_slack_markup_handles_a_valid_link_after_a_raw_closing_bracket():
    assert (
        sanitize_slack_markup("a > b <https://example.com|example>") == "a > b example"
    )
