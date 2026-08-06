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

import urllib.parse

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
    SLACK_ERROR_DATA_NOT_FOUND_IN_OUTPUT,
    SLACK_ERROR_FETCHING_USER,
    SLACK_ERROR_NO_USERID_OR_EMAIL,
    SLACK_ERROR_NOT_A_USER_ID,
    SLACK_ERROR_USER_TOKEN_NOT_PROVIDED,
    SLACK_SUCCESSFULLY_USER_DATA_RETRIEVED,
    SLACK_USER_INFO,
    SLACK_USER_LOOKUP_BY_EMAIL,
)
from ..helper import SlackFailure, rest_call, slack_rest_call

logger = getLogger()


class GetUserParams(Params):
    user_id: str | None = Param(
        description="Unique ID of user to get info of",
        primary=True,
        cef_types=["slack user id"],
    )
    email_address: str | None = Param(
        description="Email address of user to get info of. Will not be used if User ID is specified",
        primary=True,
        cef_types=["email"],
    )


class EnterpriseUserOutput(ActionOutput):
    enterprise_id: str | None = OutputField(example_values=["E02PYRE04SJ"])
    enterprise_name: str | None = OutputField(example_values=["Test Soar Sandbox"])
    id: str | None = OutputField(example_values=["U03DU1BA9ML"])
    is_admin: bool | None = None
    is_owner: bool | None = None
    is_primary_owner: bool | None = None


class ProfileOutput(ActionOutput):
    email: str | None = OutputField(
        cef_types=["email"],
        example_values=["slackbot@test.com"],
        column_name="Email",
    )
    always_active: bool | None = None
    api_app_id: str | None = OutputField(example_values=["A017K8386N9"])
    avatar_hash: str | None = OutputField(example_values=["g6f8c4b87d3e"])
    bot_id: str | None = OutputField(example_values=["B017LK9BYTC"])
    display_name: str | None = OutputField(example_values=["Slackbot"])
    display_name_normalized: str | None = OutputField(example_values=["Slackbot"])
    fields: str | None = None
    first_name: str | None = OutputField(example_values=["Slackbot"])
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
    is_custom_image: bool | None = None
    last_name: str | None = OutputField(example_values=["Slackbot"])
    phone: str | None = None
    real_name: str | None = OutputField(example_values=["Slackbot"])
    real_name_normalized: str | None = OutputField(example_values=["Test Invite Bot"])
    skype: str | None = None
    status_emoji: str | None = None
    status_expiration: float | None = OutputField(example_values=[0])
    status_text: str | None = None
    status_text_canonical: str | None = None
    team: str | None = OutputField(example_values=["TEW1DJ485"])
    title: str | None = None


class UserOutput(ActionOutput):
    # Declared in the order the widget columns are expected in. The Email column
    # comes from the nested profile model, which is declared straight after so the
    # generated column order stays contiguous.
    id: str | None = OutputField(
        cef_types=["slack user id"],
        example_values=["UEV44MD9N"],
        column_name="User ID",
    )
    name: str | None = OutputField(
        cef_types=["slack user name"],
        example_values=["@testinvite-noreply"],
        column_name="Username",
    )
    real_name: str | None = OutputField(
        example_values=["Slackbot"], column_name="Real Name"
    )
    profile: ProfileOutput | None = None
    color: str | None = OutputField(example_values=["4bbe2e"])
    deleted: bool | None = None
    enterprise_user: EnterpriseUserOutput | None = None
    is_admin: bool | None = None
    is_app_user: bool | None = None
    is_bot: bool | None = None
    is_email_confirmed: bool | None = None
    is_owner: bool | None = None
    is_primary_owner: bool | None = None
    is_restricted: bool | None = None
    is_ultra_restricted: bool | None = None
    team_id: str | None = OutputField(example_values=["TEW1DJ485"])
    tz: str | None = OutputField(example_values=["America/Los_Angeles"])
    tz_label: str | None = OutputField(example_values=["Pacific Standard Time"])
    tz_offset: float | None = OutputField(example_values=[-28800])
    updated: float | None = OutputField(example_values=[1569140077])
    who_can_share_contact_card: str | None = OutputField(example_values=["EVERYONE"])


class GetUserOutput(PermissiveActionOutput):
    ok: bool | None = None
    user: UserOutput | None = None


@app.action(
    description="Get information about a user of a Slack team",
    action_type="investigate",
    verbose="This action will ignore email_address parameter when user_id parameter is provided.",
    render_as="table",
)
def get_user(params: GetUserParams, soar: SOARClient, asset: Asset) -> GetUserOutput:
    if not params.user_id and not params.email_address:
        raise SlackFailure(SLACK_ERROR_NO_USERID_OR_EMAIL)

    if params.user_id and not params.user_id.startswith(("U", "W")):
        raise SlackFailure(SLACK_ERROR_NOT_A_USER_ID)

    if not params.user_id and not asset.bot_token:
        raise SlackFailure(SLACK_ERROR_USER_TOKEN_NOT_PROVIDED)

    try:
        if params.user_id:
            resp_json = slack_rest_call(
                asset.bot_token, SLACK_USER_INFO, {"user": params.user_id}
            )
        else:
            email = urllib.parse.quote(params.email_address or "")
            logger.debug("Making rest call to lookup user")

            resp_json = rest_call(
                f"{SLACK_BASE_URL}{SLACK_USER_LOOKUP_BY_EMAIL}?email={email}",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {asset.bot_token}",
                },
            )
    except SlackFailure as e:
        raise SlackFailure(f"{SLACK_ERROR_FETCHING_USER}: {e.message}") from e

    user = resp_json.get("user")

    if not user:
        raise SlackFailure(SLACK_ERROR_DATA_NOT_FOUND_IN_OUTPUT.format(key="User"))

    user["name"] = "@{}".format(user.get("name", ""))

    soar.set_message(SLACK_SUCCESSFULLY_USER_DATA_RETRIEVED)

    return GetUserOutput(**resp_json)
