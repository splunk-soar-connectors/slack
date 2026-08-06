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

"""Logic shared by the ask question, ask question channel and get response actions."""

import json
import uuid
from pathlib import Path

from soar_sdk.logging import getLogger

from .consts import (
    SLACK_CALLBACK_ID_LIMIT,
    SLACK_CONFIRMATION_LIMIT,
    SLACK_ERROR_ASKING_QUESTION,
    SLACK_ERROR_CONFIRMATION_TOO_LONG,
    SLACK_ERROR_LENGTH_LIMIT_EXCEEDED,
    SLACK_ERROR_QUESTION_TOO_LONG,
    SLACK_ERROR_UNABLE_TO_PARSE_RESPONSE,
    SLACK_MESSAGE_LIMIT,
    SLACK_SEND_MESSAGE,
)
from .helper import SlackFailure, slack_rest_call
from .interactive import answer_path

logger = getLogger()


def _response_buttons(responses: str | None) -> list[dict]:
    """Build the interactive message buttons for the configured responses."""
    given_answers = [x.strip().lower() for x in (responses or "yes,no").split(",")]

    ordered_answers: list[str] = []
    for answer in given_answers:
        if answer and answer not in ordered_answers:
            ordered_answers.append(answer)

    if not ordered_answers:
        ordered_answers = ["yes", "no"]

    return [
        {"name": answer, "text": answer, "value": answer, "type": "button"}
        for answer in ordered_answers
    ]


def ask_question_in_slack(
    bot_token: str,
    asset_id: str,
    destination: str,
    question: str,
    responses: str | None,
    confirmation: str = " ",
) -> dict:
    """Post a question with response buttons and return its ID and answer file path."""
    if len(question) > SLACK_MESSAGE_LIMIT:
        raise SlackFailure(
            SLACK_ERROR_QUESTION_TOO_LONG.format(limit=SLACK_MESSAGE_LIMIT)
        )

    if len(confirmation) > SLACK_CONFIRMATION_LIMIT:
        raise SlackFailure(
            SLACK_ERROR_CONFIRMATION_TOO_LONG.format(limit=SLACK_CONFIRMATION_LIMIT)
        )

    qid = uuid.uuid4().hex
    path_json = {"qid": qid, "asset_id": asset_id, "confirmation": confirmation}
    callback_id = json.dumps(path_json)

    if len(callback_id) > SLACK_CALLBACK_ID_LIMIT:
        path_json["confirmation"] = ""
        valid_length = SLACK_CALLBACK_ID_LIMIT - len(json.dumps(path_json))
        raise SlackFailure(
            SLACK_ERROR_LENGTH_LIMIT_EXCEEDED.format(
                asset_length=len(asset_id), valid_length=valid_length
            )
        )

    logger.progress(f"Asking question with ID: {qid}")

    attachments = [
        {
            "text": question,
            "fallback": "Phantom cannot post questions on this channel.",
            "callback_id": callback_id,
            "color": "#422E61",
            "attachment_type": "default",
            "actions": _response_buttons(responses),
        }
    ]

    body = {
        "channel": destination,
        "attachments": json.dumps(attachments),
        "as_user": True,
    }

    try:
        slack_rest_call(bot_token, SLACK_SEND_MESSAGE, body)
    except SlackFailure as e:
        raise SlackFailure(f"{SLACK_ERROR_ASKING_QUESTION}: {e.message}") from e

    return {"qid": qid, "answer_path": str(answer_path(qid))}


def read_answer_file(path: Path) -> dict | None:
    """Parse the answer file the webhook wrote for a question, if there is one yet."""
    try:
        raw_answer = path.read_text()
    except OSError:
        return None

    try:
        return json.loads(raw_answer)
    except Exception as e:
        raise SlackFailure(SLACK_ERROR_UNABLE_TO_PARSE_RESPONSE) from e
