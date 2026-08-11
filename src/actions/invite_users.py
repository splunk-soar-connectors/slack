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
    SLACK_BASE_URL,
    SLACK_ERROR_INVALID_USER,
    SLACK_ERROR_INVITING_CHANNEL,
    SLACK_ERROR_USER_TOKEN_NOT_PROVIDED,
    SLACK_INVITE_TO_CHANNEL,
    SLACK_SUCCESSFULLY_INVITE_SENT,
)
from ..helper import SlackFailure, rest_call

logger = getLogger()


class InviteUsersParams(Params):
    channel_id: str = Param(
        description="ID of channel",
        primary=True,
        cef_types=["slack channel id"],
    )
    users: str = Param(description="Comma-separated list of users (IDs) to invite")


class PurposeOutput(ActionOutput):
    creator: str | None = None
    last_set: float | None = OutputField(example_values=[0])
    value: str | None = None


class TopicOutput(ActionOutput):
    creator: str | None = None
    last_set: float | None = OutputField(example_values=[0])
    value: str | None = None


class ChannelOutput(ActionOutput):
    name: str | None = OutputField(
        cef_types=["slack channel name"],
        example_values=["channel1"],
        column_name="Channel Name",
    )
    creator: str | None = OutputField(
        example_values=["U6ZA4J17F"], column_name="Creator"
    )
    context_team_id: str | None = OutputField(example_values=["T02Q675CX6W"])
    created: float | None = OutputField(example_values=[1562715284])
    id: str | None = OutputField(example_values=["CLBC12T3R"])
    is_archived: bool | None = None
    is_channel: bool | None = None
    is_ext_shared: bool | None = None
    is_general: bool | None = None
    is_group: bool | None = None
    is_im: bool | None = None
    is_member: bool | None = None
    is_moved: float | None = OutputField(example_values=[0])
    is_mpim: bool | None = None
    is_open: bool | None = None
    is_org_shared: bool | None = None
    is_pending_ext_shared: bool | None = None
    is_private: bool | None = None
    is_shared: bool | None = None
    last_read: str | None = OutputField(example_values=["1562715284.000200"])
    name_normalized: str | None = OutputField(example_values=["channel1"])
    parent_conversation: str | None = None
    purpose: PurposeOutput | None = None
    shared_team_ids: str | None = OutputField(example_values=["T6YGC45LY"])
    topic: TopicOutput | None = None
    unlinked: float | None = OutputField(example_values=[0])
    updated: float | None = OutputField(example_values=[1683204116915])


class ResponseMetadataOutput(ActionOutput):
    warnings: str | None = OutputField(example_values=["missing_charset"])


class InviteUsersOutput(PermissiveActionOutput):
    channel: ChannelOutput | None = None
    ok: bool | None = None
    response_metadata: ResponseMetadataOutput | None = None
    warning: str | None = OutputField(example_values=["missing_charset"])


@app.action(
    description="Invite user(s) to a Slack channel",
    action_type="generic",
    read_only=False,
    verbose="Up to 1000 users may be added at one time. This action requires a User OAuth Token defined in the asset. For permissions, see: https://api.slack.com/methods/conversations.invite.",
    render_as="table",
)
def invite_users(
    params: InviteUsersParams, soar: SOARClient, asset: Asset
) -> InviteUsersOutput:
    if not asset.user_token:
        raise SlackFailure(SLACK_ERROR_USER_TOKEN_NOT_PROVIDED)

    users = [user for user in (x.strip() for x in params.users.split(",")) if user]

    if not users:
        raise SlackFailure(SLACK_ERROR_INVALID_USER)

    logger.debug("Making rest call to invite user")
    resp_json = rest_call(
        f"{SLACK_BASE_URL}{SLACK_INVITE_TO_CHANNEL}",
        method="post",
        headers={
            "Authorization": f"Bearer {asset.user_token}",
            "Content-Type": "application/json",
        },
        body={"users": users, "channel": params.channel_id, "token": asset.user_token},
    )

    if not resp_json.get("ok", True):
        error = resp_json.get("error", "N/A")
        message = f"{SLACK_ERROR_INVITING_CHANNEL}: {error}"
        if error_details := resp_json.get("detail", ""):
            message = f"{message}\r\nDetails: {error_details}"
        raise SlackFailure(message)

    soar.set_message(SLACK_SUCCESSFULLY_INVITE_SENT)

    return InviteUsersOutput(**resp_json)
