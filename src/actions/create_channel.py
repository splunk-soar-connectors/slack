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
    SLACK_CHANNEL_CREATE_ENDPOINT,
    SLACK_ERROR_CREATING_CHANNEL,
    SLACK_ERROR_INVALID_CHANNEL_TYPE,
    SLACK_ERROR_USER_TOKEN_NOT_PROVIDED,
    SLACK_SUCCESSFULLY_CHANNEL_CREATED,
)
from ..helper import SlackFailure, rest_call

logger = getLogger()


class CreateChannelParams(Params):
    name: str = Param(description="Name of channel")
    channel_type: str | None = Param(
        description="Type of channel to create (public or private)",
        default="public",
        value_list=["public", "private"],
    )


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
        example_values=["name"],
        column_name="Channel Name",
    )
    creator: str | None = OutputField(
        example_values=["UEVKZ9ZLL"], column_name="Creator"
    )
    created: float | None = OutputField(
        example_values=[1595502058], column_name="Created"
    )
    is_private: bool | None = OutputField(column_name="Private")
    context_team_id: str | None = OutputField(example_values=["T02Q675CX6W"])
    id: str | None = OutputField(example_values=["C017K3XMNTF"])
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
    is_shared: bool | None = None
    last_read: str | None = OutputField(example_values=["0000000000.000000"])
    name_normalized: str | None = OutputField(example_values=["name"])
    parent_conversation: str | None = None
    priority: float | None = OutputField(example_values=[0])
    purpose: PurposeOutput | None = None
    shared_team_ids: str | None = OutputField(example_values=["TEW1DJ485"])
    topic: TopicOutput | None = None
    unlinked: float | None = OutputField(example_values=[0])
    updated: float | None = OutputField(example_values=[1683204339510])


class ResponseMetadataOutput(ActionOutput):
    warnings: str | None = OutputField(example_values=["missing_charset"])


class CreateChannelOutput(PermissiveActionOutput):
    channel: ChannelOutput | None = None
    ok: bool | None = None
    response_metadata: ResponseMetadataOutput | None = None
    warning: str | None = OutputField(example_values=["missing_charset"])


@app.action(
    description="Create a new Slack channel",
    action_type="generic",
    read_only=False,
    verbose="To create a private channel, use the 'channel_type' selection parameter. This action requires a User OAuth Token defined in the asset. For naming conventions, see https://api.slack.com/methods/conversations.create.",
    render_as="table",
)
def create_channel(
    params: CreateChannelParams, soar: SOARClient, asset: Asset
) -> CreateChannelOutput:
    if not asset.user_token:
        raise SlackFailure(SLACK_ERROR_USER_TOKEN_NOT_PROVIDED)

    channel_type = params.channel_type or "public"

    if channel_type not in ("public", "private"):
        raise SlackFailure(SLACK_ERROR_INVALID_CHANNEL_TYPE)

    body: dict = {"name": params.name, "token": asset.user_token, "validate": True}

    if channel_type == "private":
        body["is_private"] = True

    logger.debug("Making rest call to create channel")
    resp_json = rest_call(
        f"{SLACK_BASE_URL}{SLACK_CHANNEL_CREATE_ENDPOINT}",
        method="post",
        headers={
            "Authorization": f"Bearer {asset.user_token}",
            "Content-Type": "application/json",
        },
        body=body,
    )

    if not resp_json.get("ok", True):
        error = resp_json.get("error", "N/A")
        message = f"{SLACK_ERROR_CREATING_CHANNEL}: {error}"
        if error_details := resp_json.get("detail", ""):
            message = f"{message}\r\nDetails: {error_details}"
        raise SlackFailure(message)

    soar.set_message(SLACK_SUCCESSFULLY_CHANNEL_CREATED)

    return CreateChannelOutput(**resp_json)
