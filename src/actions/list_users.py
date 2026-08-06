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
    SLACK_USER_LIST,
)
from ..helper import paginate, validate_integer


class ListUsersParams(Params):
    limit: int | None = Param(
        description="Specify the maximum number of results to return. Default is 100",
        default=SLACK_DEFAULT_LIMIT,
    )


class EnterpriseUserOutput(ActionOutput):
    enterprise_id: str | None = OutputField(example_values=["E02PYRE04SJ"])
    enterprise_name: str | None = OutputField(example_values=["Test Soar Sandbox"])
    id: str | None = OutputField(example_values=["U02QJ5JLTNV"])
    is_admin: bool | None = None
    is_owner: bool | None = None
    is_primary_owner: bool | None = None


class ProfileOutput(ActionOutput):
    always_active: bool | None = None
    api_app_id: str | None = OutputField(example_values=["AEVNKT17D"])
    avatar_hash: str | None = OutputField(example_values=["g6f8c4b87d3e"])
    bot_id: str | None = OutputField(example_values=["BEV82RKAM"])
    display_name: str | None = OutputField(example_values=["Slackbot"])
    display_name_normalized: str | None = OutputField(example_values=["Slackbot"])
    fields: str | None = None
    first_name: str | None = OutputField(example_values=["slackbot"])
    image_1024: str | None = OutputField(
        cef_types=["url"],
        example_values=["https://a.slack-edge.com/80588/img/slackbot_1024.png"],
    )
    image_192: str | None = OutputField(
        cef_types=["url"],
        example_values=["https://a.slack-edge.com/80588/img/slackbot_192.png"],
    )
    image_24: str | None = OutputField(
        cef_types=["url"],
        example_values=["https://a.slack-edge.com/80588/img/slackbot_24.png"],
    )
    image_32: str | None = OutputField(
        cef_types=["url"],
        example_values=["https://a.slack-edge.com/80588/img/slackbot_32.png"],
    )
    image_48: str | None = OutputField(
        cef_types=["url"],
        example_values=["https://a.slack-edge.com/80588/img/slackbot_48.png"],
    )
    image_512: str | None = OutputField(
        cef_types=["url"],
        example_values=["https://a.slack-edge.com/80588/img/slackbot_512.png"],
    )
    image_72: str | None = OutputField(
        cef_types=["url"],
        example_values=["https://a.slack-edge.com/80588/img/slackbot_72.png"],
    )
    image_original: str | None = OutputField(cef_types=["url"])
    is_custom_image: bool | None = None
    last_name: str | None = OutputField(example_values=["Slackbot"])
    phone: str | None = None
    real_name_normalized: str | None = OutputField(example_values=["Slackbot"])
    skype: str | None = None
    status_emoji: str | None = None
    status_expiration: float | None = OutputField(example_values=[0])
    status_text: str | None = None
    status_text_canonical: str | None = None
    team: str | None = OutputField(example_values=["TEW1DJ485"])
    title: str | None = None
    who_can_share_contact_card: str | None = OutputField(example_values=["NO_ONE"])


class MembersOutput(ActionOutput):
    # The four column fields are declared first so that their generated
    # column_order matches the order the widget expects. Real Name and Email live
    # under 'profile', so they are declared here with a dotted alias to keep the
    # data paths correct without disturbing the column order.
    name: str | None = OutputField(
        cef_types=["slack user name"], column_name="Username"
    )
    profile_real_name: str | None = OutputField(
        alias="profile.real_name",
        example_values=["Slackbot"],
        column_name="Real Name",
    )
    id: str | None = OutputField(cef_types=["slack user id"], column_name="User ID")
    profile_email: str | None = OutputField(
        alias="profile.email",
        cef_types=["email"],
        example_values=["slackbot@test.com"],
        column_name="Email",
    )
    color: str | None = None
    deleted: bool | None = None
    enterprise_user: EnterpriseUserOutput | None = None
    is_admin: bool | None = None
    is_app_user: bool | None = None
    is_bot: bool | None = None
    is_email_confirmed: bool | None = None
    is_invited_user: bool | None = None
    is_owner: bool | None = None
    is_primary_owner: bool | None = None
    is_restricted: bool | None = None
    is_ultra_restricted: bool | None = None
    profile: ProfileOutput | None = None
    real_name: str | None = OutputField(example_values=["Test Invite Bot"])
    team_id: str | None = OutputField(example_values=["TEW1DJ485"])
    tz: str | None = OutputField(example_values=["America/Los_Angeles"])
    tz_label: str | None = OutputField(example_values=["Pacific Standard Time"])
    tz_offset: float | None = OutputField(example_values=[-28800])
    updated: float | None = OutputField(example_values=[1569140077])
    who_can_share_contact_card: str | None = OutputField(example_values=["EVERYONE"])


class ResponseMetadataOutput(ActionOutput):
    next_cursor: str | None = None


class ListUsersOutput(PermissiveActionOutput):
    cache_ts: float | None = None
    members: list[MembersOutput] | None = None
    ok: bool | None = None
    response_metadata: ResponseMetadataOutput | None = None


class ListUsersSummary(ActionOutput):
    num_users: int = OutputField(example_values=[28])


@app.action(
    description="List users of a Slack team",
    action_type="investigate",
    render_as="table",
    summary_type=ListUsersSummary,
)
def list_users(
    params: ListUsersParams, soar: SOARClient, asset: Asset
) -> ListUsersOutput:
    limit = validate_integer(
        params.limit if params.limit is not None else SLACK_DEFAULT_LIMIT,
        SLACK_LIMIT_KEY,
    )

    resp_json = paginate(asset.bot_token, SLACK_USER_LIST, "members", limit=limit)

    users = resp_json.get("members", [])

    for user in users:
        user["name"] = "@{}".format(user.get("name", "unknownuser"))

    soar.set_summary(ListUsersSummary(num_users=len(users)))
    soar.set_message(f"Num users: {len(users)}")

    return ListUsersOutput(**resp_json)
