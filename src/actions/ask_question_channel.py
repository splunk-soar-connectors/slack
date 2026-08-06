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
from soar_sdk.params import Param, Params

from ..app import Asset, app
from ..consts import (
    SLACK_ERROR_UNABLE_TO_SEND_QUESTION_TO_USER,
    SLACK_SUCCESSFULLY_ASKED_QUESTION,
)
from ..helper import SlackFailure
from ..questions import ask_question_in_slack


class AskQuestionChannelParams(Params):
    destination: str = Param(
        description="Channel (e.g. #channel-name or C1A1A1AAA) to ask question to",
        primary=True,
        cef_types=["slack user name", "slack user id"],
    )
    question: str = Param(description="Question to ask", column_name="Question")
    responses: str | None = Param(
        description="Comma separated string values for responses. (Maximum responses allowed are 5)"
    )


class AskQuestionChannelOutput(PermissiveActionOutput):
    qid: str | None = OutputField(
        cef_types=["slack question id"], column_name="Question ID"
    )
    answer_path: str | None = OutputField(
        example_values=[
            "/opt/test/local_data/app_states/3ac26c7f-baa4-4583-86ff-5aac82778a86/2d13708f3f0147959880dcbf080147f2.json"
        ]
    )


class AskQuestionChannelSummary(ActionOutput):
    response_received: bool = False
    response: str | None = None


@app.action(
    description="Ask a question in slack channel",
    action_type="generic",
    read_only=False,
    verbose="This action will send message containing a question with a series of buttons which represent possible responses in a channel. Once the user clicks on one of the responses, Slack will send the response back to Splunk SOAR. The question ID can be used as input to the <b>get response</b> action.<br><br>If the <b>responses</b> parameter is not filled out, the response options will be <b>yes</b> and <b>no</b>.<br><br>The <b>confirmation</b> parameter takes a string that will be sent to the user after the user clicks a response. <b>Note:</b> To use the bot in a private channel you need to invite the bot first iin the private channel, else it would give channel not found error.",
    render_as="table",
    summary_type=AskQuestionChannelSummary,
)
def ask_question_channel(
    params: AskQuestionChannelParams, soar: SOARClient, asset: Asset
) -> AskQuestionChannelOutput:
    if params.destination.startswith(("@", "U")):
        # Questions asked here are answerable by anyone in the channel, so a direct
        # message has to go through the ask question action instead
        raise SlackFailure(SLACK_ERROR_UNABLE_TO_SEND_QUESTION_TO_USER)

    question_data = ask_question_in_slack(
        asset.bot_token,
        soar.get_asset_id(),
        params.destination,
        params.question,
        params.responses,
    )

    soar.set_message(SLACK_SUCCESSFULLY_ASKED_QUESTION)

    return AskQuestionChannelOutput(**question_data)
