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
    SLACK_DEFAULT_LIMIT,
    SLACK_LIMIT_KEY,
    SLACK_LIST_CHANNEL,
)
from ..helper import paginate, validate_integer


class ListChannelsParams(Params):
    limit: int | None = Param(
        description="Specify the maximum number of results to return. Default is 100",
        default=SLACK_DEFAULT_LIMIT,
    )


class PurposeOutput(ActionOutput):
    creator: str | None = OutputField(example_values=["UEVKZ9ZLL"])
    last_set: float | None = OutputField(example_values=[1545061069])
    value: str | None = OutputField(
        example_values=[
            "This channel is for workspace-wide communication and announcements. All members are in this channel."
        ]
    )


class TopicOutput(ActionOutput):
    creator: str | None = OutputField(example_values=["UEVKZ9ZLL"])
    last_set: float | None = OutputField(example_values=[1545061069])
    value: str | None = OutputField(
        example_values=["Non-work banter and water cooler conversation"]
    )


class ChannelsOutput(ActionOutput):
    name: str | None = OutputField(
        cef_types=["slack channel name"], column_name="Channel Name"
    )
    id: str | None = OutputField(
        cef_types=["slack channel id"], column_name="Channel ID"
    )
    context_team_id: str | None = OutputField(example_values=["T02Q675CX6W"])
    created: float | None = OutputField(example_values=[1545061069])
    creator: str | None = OutputField(example_values=["UEVKZ9ZLL"])
    is_archived: bool | None = None
    is_channel: bool | None = None
    is_ext_shared: bool | None = None
    is_general: bool | None = None
    is_group: bool | None = None
    is_im: bool | None = None
    is_member: bool | None = None
    is_moved: float | None = OutputField(example_values=[0])
    is_mpim: bool | None = None
    is_org_shared: bool | None = None
    is_pending_ext_shared: bool | None = None
    is_private: bool | None = None
    is_shared: bool | None = None
    members: str | None = None
    name_normalized: str | None = OutputField(example_values=["general"])
    num_members: float | None = OutputField(example_values=[23])
    parent_conversation: str | None = None
    purpose: PurposeOutput | None = None
    topic: TopicOutput | None = None
    unlinked: float | None = OutputField(example_values=[0])
    updated: float | None = OutputField(example_values=[1639075392157])


class ResponseMetadataOutput(ActionOutput):
    next_cursor: str | None = OutputField(example_values=["dGVhbTpDMDE3WENOQVE4TA=="])


class ListChannelsOutput(PermissiveActionOutput):
    channels: list[ChannelsOutput] | None = None
    ok: bool | None = None
    response_metadata: ResponseMetadataOutput | None = None


class ListChannelsSummary(ActionOutput):
    num_public_channels: int = OutputField(example_values=[10])


@app.action(
    description="List public channels of a Slack team",
    action_type="investigate",
    verbose="The output of this action is a list of all public channels in the configured Slack team. The channels will be listed with their corresponding channel IDs.",
    render_as="table",
    summary_type=ListChannelsSummary,
)
def list_channels(
    params: ListChannelsParams, soar: SOARClient, asset: Asset
) -> ListChannelsOutput:
    limit = validate_integer(
        params.limit if params.limit is not None else SLACK_DEFAULT_LIMIT,
        SLACK_LIMIT_KEY,
    )

    resp_json = paginate(asset.bot_token, SLACK_LIST_CHANNEL, "channels", limit=limit)

    channels = resp_json.get("channels", [])

    for channel in channels:
        channel["name"] = "#{}".format(channel.get("name", "unknownchannel"))

    soar.set_summary(ListChannelsSummary(num_public_channels=len(channels)))
    soar.set_message(f"Num public channels: {len(channels)}")

    return ListChannelsOutput(**resp_json)
