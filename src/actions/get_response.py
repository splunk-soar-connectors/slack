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

from soar_sdk.abstract import SOARClient
from soar_sdk.action_results import (
    ActionOutput,
    OutputField,
    PermissiveActionOutput,
)
from soar_sdk.logging import getLogger
from soar_sdk.params import Param, Params

from ..app import Asset, app
from ..consts import (
    SLACK_ERROR_INVALID_FILE_PATH,
    SLACK_ERROR_QUESTION_RESPONSE_NOT_AVAILABLE,
)
from ..helper import SlackFailure
from ..interactive import answer_path
from ..questions import read_answer_file

logger = getLogger()


class GetResponseParams(Params):
    question_id: str = Param(
        description="Question ID",
        primary=True,
        cef_types=["slack question id"],
    )


class ActionsOutput(ActionOutput):
    value: str | None = OutputField(column_name="Response")
    name: str | None = None
    type: str | None = None


class ChannelOutput(ActionOutput):
    id: str | None = None
    name: str | None = None


class TeamOutput(ActionOutput):
    domain: str | None = OutputField(cef_types=["domain"])
    id: str | None = None


class AttachmentActionsOutput(ActionOutput):
    id: str | None = None
    name: str | None = None
    style: str | None = None
    text: str | None = None
    type: str | None = None
    value: str | None = None


class AttachmentsOutput(ActionOutput):
    text: str | None = OutputField(column_name="Question")
    actions: list[AttachmentActionsOutput] | None = None
    callback_id: str | None = None
    color: str | None = None
    fallback: str | None = None
    id: float | None = None


class OriginalMessageOutput(ActionOutput):
    attachments: list[AttachmentsOutput] | None = None
    bot_id: str | None = None
    text: str | None = None
    ts: str | None = OutputField(cef_types=["slack message ts"])
    type: str | None = None
    user: str | None = None


class UserOutput(ActionOutput):
    name: str | None = OutputField(column_name="Username")
    id: str | None = None


class PayloadsOutput(ActionOutput):
    # Declared so that the generated column order matches the order the widget
    # expects: the question text, the chosen response, then the responding user.
    original_message: OriginalMessageOutput | None = None
    actions: list[ActionsOutput] | None = None
    user: UserOutput | None = None
    action_ts: str | None = None
    attachment_id: str | None = None
    callback_id: str | None = None
    channel: ChannelOutput | None = None
    is_app_unfurl: bool | None = None
    message_ts: str | None = OutputField(cef_types=["slack message ts"])
    response_url: str | None = None
    team: TeamOutput | None = None
    token: str | None = None


class GetResponseOutput(PermissiveActionOutput):
    payloads: list[PayloadsOutput] | None = None
    # The original app bound this column to action_result.parameter.question_id, which
    # the SDK always orders ahead of the output columns, so it is carried as an
    # explicit data field to keep the widget column order intact.
    question_id: str | None = OutputField(
        cef_types=["slack question id"], column_name="Question ID"
    )


class GetResponseSummary(ActionOutput):
    response_received: bool = False
    response: str | None = None


@app.action(
    description="Get the response to a previously asked question",
    action_type="investigate",
    read_only=True,
    verbose="The purpose of the 'get response' action is to get the response of a question, asked using the 'ask question' action, that timed out before it could get the response.<br>The action will check to see if a question has been answered.<br><ul><li>If the user has answered the question, the question id generated in the 'ask question' action can be used to get the response.</li><li>If no response is yet available, the action will fail.</li></ul>",
    render_as="table",
    summary_type=GetResponseSummary,
)
def get_response(
    params: GetResponseParams, soar: SOARClient, asset: Asset
) -> GetResponseOutput:
    try:
        path = answer_path(params.question_id)
    except ValueError as e:
        raise SlackFailure(SLACK_ERROR_INVALID_FILE_PATH) from e

    logger.progress(f"Checking for response to question with ID: {params.question_id}")

    resp_json = read_answer_file(path)

    if resp_json is None:
        raise SlackFailure(SLACK_ERROR_QUESTION_RESPONSE_NOT_AVAILABLE)

    soar.set_summary(GetResponseSummary(response_received=True))
    soar.set_message("Response received: True")

    return GetResponseOutput(question_id=params.question_id, **resp_json)
