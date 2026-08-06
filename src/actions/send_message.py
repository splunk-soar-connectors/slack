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
    SLACK_ERROR_BLOCKS_OR_MESSAGE_REQD,
    SLACK_ERROR_MESSAGE_TOO_LONG,
    SLACK_ERROR_SENDING_MESSAGE,
    SLACK_MESSAGE_LIMIT,
    SLACK_SEND_MESSAGE,
    SLACK_SUCCESSFULLY_MESSAGE_SENT,
)
from ..helper import SlackFailure, slack_rest_call

logger = getLogger()


class SendMessageParams(Params):
    destination: str = Param(
        description="Channel (e.g. #channel or C1A1A1AAA)",
        primary=True,
        cef_types=[
            "slack channel name",
            "slack channel id",
            "slack user name",
            "slack user id",
        ],
        column_name="Destination",
    )
    message: str | None = Param(
        description="Message to send, required if 'blocks' is not set. If 'blocks' is set, this is used as fallback text",
        column_name="Message",
    )
    blocks: str | None = Param(
        description="Blocks to send, required if 'message' is not set",
        column_name="Blocks",
    )
    parent_message_ts: str | None = Param(
        description="Parent message timestamp to reply in thread",
        primary=True,
        cef_types=["slack message ts"],
    )
    reply_broadcast: bool | None = Param(
        description="Used in conjunction with 'parent_message_ts' and indicates whether reply should be made visible to everyone in the channel or conversation",
    )
    link_names: bool | None = Param(
        description="Check this if you want to enable announcements in your Slack messages using mentions. E.g.: Use @someone or @channel in your message in combination with this check to notify people",
    )


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
    app_id: str | None = OutputField(example_values=["A017E1NAPSR"])
    deleted: bool | None = None
    icons: IconsOutput | None = None
    id: str | None = OutputField(example_values=["B017U24BH25"])
    name: str | None = OutputField(example_values=["Test_Playbook"])
    team_id: str | None = OutputField(example_values=["TEW1DJ485"])
    updated: float | None = OutputField(example_values=[1595596858])


class RootFilesOutput(ActionOutput):
    created: float | None = OutputField(example_values=[1613560453])
    display_as_bot: bool | None = None
    edit_link: str | None = OutputField(
        example_values=[
            "https://test.slack.com/files/U017MJM0352/F01ND14T56W/adb3e6f532264cee9ccf4589808bb489"
        ]
    )
    editable: bool | None = None
    external_type: str | None = None
    filetype: str | None = OutputField(example_values=["text"])
    has_rich_preview: bool | None = None
    id: str | None = OutputField(example_values=["F01ND14T56W"])
    is_external: bool | None = None
    is_public: bool | None = None
    is_starred: bool | None = None
    lines: float | None = OutputField(example_values=[5])
    lines_more: float | None = OutputField(example_values=[0])
    mimetype: str | None = OutputField(example_values=["text/plain"])
    mode: str | None = OutputField(example_values=["snippet"])
    name: str | None = OutputField(example_values=["adb3e6f532264cee9ccf4589808bb489"])
    permalink: str | None = OutputField(
        example_values=[
            "https://test.slack.com/files/U017MJM0352/F01ND14T56W/adb3e6f532264cee9ccf4589808bb489"
        ]
    )
    permalink_public: str | None = OutputField(
        example_values=["https://slack-files.com/TEW1DJ485-F01ND14T56W-d68a8bf630"]
    )
    pretty_type: str | None = OutputField(example_values=["Plain Text"])
    preview: str | None = None
    preview_highlight: str | None = None
    preview_is_truncated: bool | None = None
    public_url_shared: bool | None = None
    size: float | None = OutputField(example_values=[73])
    timestamp: float | None = OutputField(example_values=[1613560453])
    title: str | None = OutputField(example_values=["adb3e6f532264cee9ccf4589808bb489"])
    url_private: str | None = None
    url_private_download: str | None = None
    user: str | None = OutputField(example_values=["U017MJM0352"])
    username: str | None = None


class RootOutput(ActionOutput):
    bot_id: str | None = OutputField(example_values=["B017U24BH25"])
    bot_profile: BotProfileOutput | None = None
    display_as_bot: bool | None = None
    files: list[RootFilesOutput] | None = None
    latest_reply: str | None = OutputField(example_values=["1613564048.001700"])
    reply_count: float | None = OutputField(example_values=[1])
    reply_users_count: float | None = OutputField(example_values=[1])
    subscribed: bool | None = None
    team: str | None = OutputField(example_values=["TEW1DJ485"])
    text: str | None = OutputField(
        example_values=["This is a message from Playbook to channel_name"]
    )
    thread_ts: str | None = OutputField(example_values=["1613561692.001200"])
    ts: str | None = OutputField(example_values=["1613561692.001200"])
    type: str | None = OutputField(example_values=["message"])
    upload: bool | None = None
    user: str | None = OutputField(example_values=["U017MJM0352"])


class BlockElementElementsOutput(ActionOutput):
    channel_id: str | None = OutputField(example_values=["C0183RKACNM"])
    range: str | None = OutputField(example_values=["here"])
    text: str | None = OutputField(
        example_values=["This is the reply on this timestamp."]
    )
    type: str | None = OutputField(example_values=["text"])
    user_id: str | None = OutputField(example_values=["UPK123P74AGG"])


class BlockElementsOutput(ActionOutput):
    elements: list[BlockElementElementsOutput] | None = None
    type: str | None = OutputField(example_values=["rich_text_section"])


class BlockFieldsOutput(ActionOutput):
    text: str | None = OutputField(example_values=["*Type:*\nPaid Time Off"])
    type: str | None = OutputField(example_values=["mrkdwn"])
    verbatim: bool | None = None


class BlockTextOutput(ActionOutput):
    emoji: bool | None = None
    text: str | None = OutputField(example_values=["New request"])
    type: str | None = OutputField(example_values=["plain_text"])
    verbatim: bool | None = None


class BlocksOutput(ActionOutput):
    block_id: str | None = OutputField(example_values=["K60o"])
    elements: list[BlockElementsOutput] | None = None
    fields: list[BlockFieldsOutput] | None = None
    text: BlockTextOutput | None = None
    type: str | None = OutputField(example_values=["rich_text"])


class MessageOutput(ActionOutput):
    ts: str | None = OutputField(
        cef_types=["slack message ts"], column_name="Message Timestamp"
    )
    app_id: str | None = OutputField(example_values=["A03B9SMKUS2"])
    blocks: list[BlocksOutput] | None = None
    bot_id: str | None = None
    bot_profile: BotProfileOutput | None = None
    parent_user_id: str | None = OutputField(example_values=["U017MJM0352"])
    root: RootOutput | None = None
    subtype: str | None = OutputField(example_values=["thread_broadcast"])
    team: str | None = OutputField(example_values=["TEW1DJ485"])
    text: str | None = None
    thread_ts: str | None = OutputField(example_values=["1613561693.000300"])
    type: str | None = None
    user: str | None = None


class SendMessageOutput(PermissiveActionOutput):
    # The original app bound this column to action_result.status, which the SDK
    # emits without column metadata, so it is carried as an explicit data field.
    status: str | None = OutputField(
        example_values=["success", "failed"], column_name="Status"
    )
    message: MessageOutput | None = None
    channel: str | None = OutputField(cef_types=["slack channel id"])
    ok: bool | None = None
    ts: str | None = None


@app.action(
    description="Send a message to Slack",
    action_type="generic",
    read_only=False,
    verbose='The <b>destination</b> parameter can be a channel ID (e.g. C1A1A1AAA), a channel name (e.g. #general). When sending a message to a channel, the configured bot user must have been added to the channel. Slack recommends limiting messages to 4000 characters but the enforced limit is 40000 characters. Passing a "username" as a channel value is deprecated, along with the whole concept of usernames on Slack. Please always use channel-like IDs instead to make sure your message gets to where it\'s going.',
    render_as="table",
)
def send_message(
    params: SendMessageParams, soar: SOARClient, asset: Asset
) -> SendMessageOutput:
    if params.message is None and params.blocks is None:
        raise SlackFailure(SLACK_ERROR_BLOCKS_OR_MESSAGE_REQD)

    body: dict = {"channel": params.destination}

    if params.message is not None:
        message = params.message

        if "\\" in message:
            message = bytes(message, "utf-8").decode("unicode_escape")

        if len(message) > SLACK_MESSAGE_LIMIT:
            raise SlackFailure(
                SLACK_ERROR_MESSAGE_TOO_LONG.format(limit=SLACK_MESSAGE_LIMIT)
            )

        body["text"] = message

    if params.blocks is not None:
        body["blocks"] = params.blocks

    body["link_names"] = params.link_names or False

    if params.parent_message_ts is not None:
        # Support for replying in thread
        body["thread_ts"] = params.parent_message_ts

        if params.reply_broadcast is not None:
            body["reply_broadcast"] = params.reply_broadcast

    logger.debug("Making rest call to send message")

    try:
        resp_json = slack_rest_call(asset.bot_token, SLACK_SEND_MESSAGE, body)
    except SlackFailure as e:
        raise SlackFailure(f"{SLACK_ERROR_SENDING_MESSAGE}: {e.message}") from e

    soar.set_message(SLACK_SUCCESSFULLY_MESSAGE_SENT)

    return SendMessageOutput(status="success", **resp_json)
