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

"""Helpers shared by the app and the standalone SlackBot process.

This module intentionally depends only on the standard library and uses no
relative imports so that ``slack_bot.py``, which the on poll action spawns as a
separate process, can import it without the ``src`` package being installed.
"""

import contextlib
import json
import os
from pathlib import Path
from typing import Any

APP_ID = "3ac26c7f-baa4-4583-86ff-5aac82778a86"

# Defined here rather than in consts.py because this module is also imported by the
# standalone SlackBot process, which cannot resolve the src package.
SLACK_ERROR_RESPONDER_NOT_PERMITTED = (
    "The user that responded to the question is not permitted"
)


def state_dir(app_id: str = APP_ID) -> Path:
    """Return the directory SOAR keeps this app's asset state and answer files in."""
    phantom_home = os.getenv("PHANTOM_HOME", "/opt/phantom")
    return Path(phantom_home) / "local_data" / "app_states" / app_id


def is_safe_path(basedir: Path, path: Path) -> bool:
    """Check the given path resolves inside basedir, to combat path traversal."""
    return str(basedir) == os.path.commonpath((str(basedir), str(path.resolve())))


def answer_path(qid: str, app_id: str = APP_ID) -> Path:
    """Return the path of the answer file for a question, validating the question ID."""
    base = state_dir(app_id)
    path = base / f"{qid}.json"

    if not is_safe_path(base, path):
        raise ValueError("The file path is invalid")

    return path


def question_path(qid: str, app_id: str = APP_ID) -> Path:
    """Return the path of a question's metadata file, validating the question ID."""
    base = state_dir(app_id)
    path = base / f"{qid}_question.json"

    if not is_safe_path(base, path):
        raise ValueError("The file path is invalid")

    return path


def write_question_metadata(
    qid: str,
    choices: list[str],
    channel: str,
    user: str | None,
    app_id: str = APP_ID,
) -> None:
    """Record the choices, conversation and intended user a question was posted with."""
    path = question_path(qid, app_id)
    state_dir(app_id).mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"choices": choices, "channel": channel, "user": user}))


def remove_question_metadata(qid: str, app_id: str = APP_ID) -> None:
    """Delete a question's metadata once it has been answered or has timed out."""
    with contextlib.suppress(OSError, ValueError):
        question_path(qid, app_id).unlink(missing_ok=True)


def validate_answer_payload(
    payload: dict, path: Path, permitted_users: str | None = None
) -> str | None:
    """Return why an interaction does not match its pending question, or None if it does.

    Nothing about the payload Slack posts back is trustworthy on its own, so the answer,
    the conversation it came from and the responder are all checked against what the
    question was actually posted with.
    """
    try:
        question = json.loads(path.read_text())
    except Exception:
        return "No pending question was found for this question ID"

    if not isinstance(payload, dict) or not isinstance(question, dict):
        return "The question response payload is invalid"

    stored_choices = question.get("choices")

    if not isinstance(stored_choices, list):
        return "The pending question metadata is invalid"

    choices = {choice for choice in stored_choices if isinstance(choice, str)}
    actions = payload.get("actions")

    if not isinstance(actions, list) or not actions:
        return "The question response contains no answer"

    if any(
        not isinstance(action, dict) or action.get("value") not in choices
        for action in actions
    ):
        return "The answer is not one of the offered choices"

    channel = payload.get("channel")
    channel_id = channel.get("id") if isinstance(channel, dict) else None

    if question.get("channel") and channel_id != question["channel"]:
        return "The response came from a different Slack conversation"

    user = payload.get("user")
    user_id = user.get("id") if isinstance(user, dict) else None

    if not user_id:
        return "The question response does not identify a Slack user"

    if question.get("user") and user_id != question["user"]:
        return "The response did not come from the intended Slack user"

    if permitted_users:
        allowed_users = {
            value.strip() for value in str(permitted_users).split(",") if value.strip()
        }

        if user_id not in allowed_users:
            return SLACK_ERROR_RESPONDER_NOT_PERMITTED

    return None


def sanitize_slack_markup(value: str) -> str:
    """Unwrap Slack links while guaranteeing progress on malformed input."""
    while (left_index := value.find("<")) != -1:
        right_index = value.find(">", left_index + 1)
        if right_index == -1:
            break

        pipe_index = value.find("|", left_index + 1, right_index)
        start_index = pipe_index + 1 if pipe_index != -1 else left_index + 1
        replacement = value[start_index:right_index]
        value = value[:left_index] + replacement + value[right_index + 1 :]

    return value


def process_payload(payload: dict, path: Path) -> dict[str, Any]:
    """Merge an interactive message payload into any answer already recorded for it."""
    current_user_id = payload.get("user", {}).get("id")

    if not path.exists():
        return {"payloads": [payload], "replies_from": [current_user_id]}

    old_payload = json.loads(path.read_text())

    if current_user_id not in old_payload.get("replies_from", []):
        old_payload["payloads"].append(payload)
        old_payload["replies_from"].append(current_user_id)
    else:
        for data in old_payload.get("payloads", []):
            if data.get("user", {}).get("id") == current_user_id:
                data["actions"] = payload.get("actions")

    return old_payload
