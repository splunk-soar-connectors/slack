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
    SLACK_CONVERSATIONS_HISTORY,
    SLACK_ERROR_FETCHING_CONVERSATION_HISTORY,
    SLACK_ERROR_NOT_A_CHANNEL_ID,
    SLACK_ERROR_THREAD_NOT_FOUND,
    SLACK_SUCCESSFULLY_CONVERSATION_HISTORY_DATA_RETRIEVED,
    SLACK_THREADS_HISTORY,
)
from ..helper import SlackFailure, slack_rest_call

logger = getLogger()


class GetHistoryParams(Params):
    channel_id: str = Param(
        description="Unique ID of a Slack channel",
        primary=True,
        cef_types=["slack channel id"],
    )
    message_ts: str | None = Param(
        description="Message timestamp (e.g. 1234567890.123456)",
        primary=True,
        cef_types=["slack message timestamp"],
    )


class MessagesOutput(ActionOutput):
    type: str | None = OutputField(example_values=["message"], column_name="Type")
    user: str | None = OutputField(example_values=["U123ABC456"], column_name="User")
    text: str | None = OutputField(
        example_values=["Hello, this is a test message"], column_name="Message"
    )
    client_msg_id: str | None = OutputField(
        example_values=["aa73fcc6-e1d4-480e-a466-3edad41bf011"]
    )
    is_locked: bool | None = None
    latest_reply: str | None = OutputField(example_values=["1704970971.951549"])
    parent_user_id: str | None = OutputField(example_values=["U123ABC456"])
    reply_count: float | None = OutputField(example_values=[1])
    reply_users_count: float | None = OutputField(example_values=[1])
    subscribed: bool | None = None
    team: str | None = OutputField(example_values=["T06LF49SKJM"])
    thread_ts: str | None = OutputField(example_values=["1512085950.000216"])
    ts: str | None = OutputField(example_values=["1512085950.000216"])


class GetHistoryOutput(PermissiveActionOutput):
    messages: list[MessagesOutput] | None = None
    ok: bool | None = None


class GetHistorySummary(ActionOutput):
    num_messages: int = OutputField(example_values=[28])


def _fetch_thread(bot_token: str, channel_id: str, timestamp: str) -> dict:
    try:
        return slack_rest_call(
            bot_token, SLACK_THREADS_HISTORY, {"channel": channel_id, "ts": timestamp}
        )
    except SlackFailure as e:
        raise SlackFailure(
            f"{SLACK_ERROR_FETCHING_CONVERSATION_HISTORY}: {e.message}"
        ) from e


@app.action(
    description="Get conversation history from specific Slack channel",
    action_type="investigate",
    read_only=True,
    verbose="To get conversation history from a specified Slack channel. It also supports `message_ts` filter to retrieve a specific message. If `message_ts` is not provided then it will retrieve the latest 100 messages.",
    render_as="table",
    summary_type=GetHistorySummary,
)
def get_history(
    params: GetHistoryParams, soar: SOARClient, asset: Asset
) -> GetHistoryOutput:
    logger.debug(f"Executing Get History action for channel {params.channel_id}")

    if params.message_ts:
        resp_json = _fetch_thread(asset.bot_token, params.channel_id, params.message_ts)

        if not resp_json:
            raise SlackFailure(SLACK_ERROR_THREAD_NOT_FOUND)

    else:
        if not params.channel_id.startswith("C"):
            raise SlackFailure(SLACK_ERROR_NOT_A_CHANNEL_ID)

        try:
            channel_history = slack_rest_call(
                asset.bot_token,
                SLACK_CONVERSATIONS_HISTORY,
                {"channel": params.channel_id},
            )
        except SlackFailure as e:
            raise SlackFailure(
                f"{SLACK_ERROR_FETCHING_CONVERSATION_HISTORY}: {e.message}"
            ) from e

        # Add threads for each received timestamp
        resp_json = {"messages": []}

        for message in channel_history.get("messages", []):
            timestamp = message["ts"]
            logger.debug(f"Fetching message history for {timestamp}")
            thread = _fetch_thread(asset.bot_token, params.channel_id, timestamp)
            resp_json["messages"] += thread.get("messages", [])

    soar.set_summary(GetHistorySummary(num_messages=len(resp_json["messages"])))
    soar.set_message(SLACK_SUCCESSFULLY_CONVERSATION_HISTORY_DATA_RETRIEVED)

    return GetHistoryOutput(**resp_json)
