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

import json

import pytest

from src.interactive import sanitize_slack_markup, validate_answer_payload


@pytest.fixture
def question_file(tmp_path):
    path = tmp_path / "qid_question.json"
    path.write_text(
        json.dumps({"choices": ["yes", "no"], "channel": "D01ABC", "user": "U01USER"})
    )
    return path


def answer(value="yes", channel="D01ABC", user="U01USER"):
    return {
        "actions": [{"value": value}],
        "channel": {"id": channel},
        "user": {"id": user},
    }


def test_validate_answer_payload_accepts_the_intended_response(question_file):
    assert validate_answer_payload(answer(), question_file) is None


def test_validate_answer_payload_rejects_an_answer_that_was_never_offered(
    question_file,
):
    assert validate_answer_payload(answer(value="maybe"), question_file) is not None


def test_validate_answer_payload_rejects_another_conversation(question_file):
    assert (
        validate_answer_payload(answer(channel="C09OTHER"), question_file) is not None
    )


def test_validate_answer_payload_rejects_another_user(question_file):
    assert validate_answer_payload(answer(user="U09EVIL"), question_file) is not None


def test_validate_answer_payload_rejects_a_payload_without_an_answer(question_file):
    payload = answer()
    del payload["actions"]

    assert validate_answer_payload(payload, question_file) is not None


def test_validate_answer_payload_rejects_an_unidentified_user(question_file):
    payload = answer()
    del payload["user"]

    assert validate_answer_payload(payload, question_file) is not None


def test_validate_answer_payload_rejects_a_question_that_is_not_pending(tmp_path):
    assert validate_answer_payload(answer(), tmp_path / "missing.json") is not None


def test_validate_answer_payload_honors_the_responder_allowlist(question_file):
    assert validate_answer_payload(answer(), question_file, "U02OK,U03OK") is not None
    assert validate_answer_payload(answer(), question_file, "U01USER,U03OK") is None


def test_validate_answer_payload_allows_any_user_when_no_user_is_bound(tmp_path):
    path = tmp_path / "qid_question.json"
    path.write_text(
        json.dumps({"choices": ["approve"], "channel": "C01CHAN", "user": None})
    )

    assert (
        validate_answer_payload(
            answer(value="approve", channel="C01CHAN", user="U0ANYONE"), path
        )
        is None
    )


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
