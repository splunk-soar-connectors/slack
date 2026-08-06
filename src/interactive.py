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

import json
import os
from pathlib import Path
from typing import Any

APP_ID = "3ac26c7f-baa4-4583-86ff-5aac82778a86"


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
