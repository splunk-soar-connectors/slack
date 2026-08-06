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

import time
from pathlib import Path

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
    SLACK_DEFAULT_TIMEOUT,
    SLACK_ERROR_QUESTION_TIMED_OUT,
    SLACK_ERROR_UNABLE_TO_SEND_QUESTION_TO_CHANNEL,
)
from ..helper import SlackFailure
from ..questions import ask_question_in_slack, read_answer_file

logger = getLogger()


class AskQuestionParams(Params):
    destination: str = Param(
        description="User (e.g. @user or U1A1A1AAA) to ask question to",
        primary=True,
        cef_types=["slack user name", "slack user id"],
    )
    question: str = Param(description="Question to ask", column_name="Question")
    responses: str | None = Param(
        description="Comma separated string values for responses. (Maximum responses allowed are 5)"
    )
    confirmation: str | None = Param(description="Message to user after response")


class ActionsOutput(ActionOutput):
    value: str | None = OutputField(column_name="Response")
    name: str | None = None
    type: str | None = None


class ChannelOutput(ActionOutput):
    id: str | None = None
    name: str | None = None


class EnterpriseOutput(ActionOutput):
    id: str | None = OutputField(example_values=["E02PYRE04SJ"])
    name: str | None = OutputField(example_values=["Test Soar Sandbox"])


class TeamOutput(ActionOutput):
    domain: str | None = OutputField(cef_types=["domain"])
    enterprise_id: str | None = OutputField(example_values=["E02PYRE04SJ"])
    enterprise_name: str | None = OutputField(example_values=["Test Soar Sandbox"])
    id: str | None = None


class UserOutput(ActionOutput):
    id: str | None = None
    name: str | None = None
    team_id: str | None = OutputField(example_values=["T02Q675CX6W"])


class AttachmentActionsOutput(ActionOutput):
    id: str | None = None
    name: str | None = None
    style: str | None = None
    text: str | None = None
    type: str | None = None
    value: str | None = None


class AttachmentsOutput(ActionOutput):
    actions: list[AttachmentActionsOutput] | None = None
    callback_id: str | None = None
    color: str | None = None
    fallback: str | None = None
    id: float | None = None
    text: str | None = None


class IconsOutput(ActionOutput):
    image_36: str | None = OutputField(
        example_values=["https://a.slack-edge.com/80588/img/plugins/app/bot_36.png"]
    )
    image_48: str | None = OutputField(
        example_values=["https://a.slack-edge.com/80588/img/plugins/app/bot_48.png"]
    )
    image_72: str | None = OutputField(
        example_values=["https://a.slack-edge.com/80588/img/plugins/app/service_72.png"]
    )


class BotProfileOutput(ActionOutput):
    app_id: str | None = OutputField(example_values=["A056963QALF"])
    deleted: bool | None = None
    icons: IconsOutput | None = None
    id: str | None = OutputField(example_values=["B05696DUY4X"])
    name: str | None = OutputField(example_values=["Heena_bot"])
    team_id: str | None = OutputField(example_values=["T02Q675CX6W"])
    updated: float | None = OutputField(example_values=[1677140860])


class MessageOutput(ActionOutput):
    attachments: list[AttachmentsOutput] | None = None
    bot_id: str | None = None
    text: str | None = None
    ts: str | None = None
    type: str | None = None
    user: str | None = None


class OriginalMessageOutput(ActionOutput):
    app_id: str | None = OutputField(example_values=["A056963QALF"])
    attachments: list[AttachmentsOutput] | None = None
    bot_id: str | None = None
    bot_profile: BotProfileOutput | None = None
    team: str | None = OutputField(example_values=["T02Q675CX6W"])
    text: str | None = None
    ts: str | None = OutputField(cef_types=["slack message ts"])
    type: str | None = None
    user: str | None = None


class AskQuestionOutput(PermissiveActionOutput):
    actions: list[ActionsOutput] | None = None
    action_ts: str | None = None
    attachment_id: str | None = None
    callback_id: str | None = None
    channel: ChannelOutput | None = None
    enterprise: EnterpriseOutput | None = None
    is_app_unfurl: bool | None = None
    is_enterprise_install: bool | None = None
    message: MessageOutput | None = None
    message_ts: str | None = OutputField(cef_types=["slack message ts"])
    original_message: OriginalMessageOutput | None = None
    response_url: str | None = None
    team: TeamOutput | None = None
    token: str | None = None
    trigger_id: str | None = OutputField(
        example_values=["5352404279280.2822243439234.8b1d29c8cf8df1243f25ac510252c95c"]
    )
    ts: str | None = None
    type: str | None = OutputField(example_values=["interactive_message"])
    user: UserOutput | None = None


class AskQuestionSummary(ActionOutput):
    question_id: str = OutputField(
        cef_types=["slack question id"], column_name="Question ID"
    )
    response_received: bool = False
    response: str | None = None


@app.action(
    description="Ask a question to a Slack user",
    action_type="generic",
    read_only=False,
    verbose="This action will send a Slack user a direct message containing a question with a series of buttons which represent possible responses. Slack recommends limiting questions to 4000 characters but the enforced limit is 40000 characters. Once the user clicks on one of the responses, Slack will send the response back to Splunk SOAR. The action will succeed and output this response in the action result. If the user fails to respond within the timeout configured in the asset, the action will succeed, and output the <b>question ID</b> in the action result. The question ID can be used as input to the <b>get response</b> action.<br><br>If the <b>responses</b> parameter is not filled out, the response options will be <b>yes</b> and <b>no</b>.<br><br>The <b>confirmation</b> parameter takes a string that will be sent to the user after the user clicks a response. <b>Note:</b> It is recommended to use user ID instead of username since the latter usage has been deprecated by Slack.",
    render_as="table",
    summary_type=AskQuestionSummary,
)
def ask_question(
    params: AskQuestionParams, soar: SOARClient, asset: Asset
) -> AskQuestionOutput:
    if params.destination.startswith(("#", "C")):
        # Don't want to send question to channels because then we would not know who
        # was answering
        raise SlackFailure(SLACK_ERROR_UNABLE_TO_SEND_QUESTION_TO_CHANNEL)

    question_data = ask_question_in_slack(
        asset.bot_token,
        soar.get_asset_id(),
        params.destination,
        params.question,
        params.responses,
        params.confirmation or " ",
    )

    qid = question_data["qid"]
    path = Path(question_data["answer_path"])

    interval = asset.response_poll_interval or SLACK_DEFAULT_TIMEOUT
    timeout_in_seconds = (asset.timeout or SLACK_DEFAULT_TIMEOUT) * 60

    if interval > timeout_in_seconds:
        logger.debug("Question timeout is greater than the polling interval")
        interval = timeout_in_seconds
        loop_count = 1
    else:
        loop_count = timeout_in_seconds // interval

    for _ in range(loop_count):
        resp_json = read_answer_file(path)

        if resp_json is not None:
            break

        time.sleep(interval)
    else:
        soar.set_summary(AskQuestionSummary(question_id=qid, response_received=False))
        raise SlackFailure(SLACK_ERROR_QUESTION_TIMED_OUT)

    payload = resp_json["payloads"][0]
    response = payload.get("actions", [{}])[0].get("value")

    soar.set_summary(
        AskQuestionSummary(question_id=qid, response_received=True, response=response)
    )
    soar.set_message(
        f"Response received: True, Question id: {qid}, Response: {response}"
    )

    path.unlink()

    return AskQuestionOutput(**payload)
