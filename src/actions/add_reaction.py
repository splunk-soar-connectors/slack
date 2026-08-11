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
    OutputField,
    PermissiveActionOutput,
)
from soar_sdk.logging import getLogger
from soar_sdk.params import Param, Params

from ..app import Asset, app
from ..consts import (
    SLACK_ADD_REACTION,
    SLACK_ERROR_ADDING_REACTION,
    SLACK_SUCCESSFULLY_REACTION_ADDED,
)
from ..helper import SlackFailure, slack_rest_call

logger = getLogger()


class AddReactionParams(Params):
    destination: str = Param(
        description="Channel ID (C1A1A1AAA) to send message to",
        primary=True,
        cef_types=["slack channel id"],
        column_name="Destination",
    )
    emoji: str = Param(description="Reaction (emoji) to add")
    message_ts: str = Param(
        description="Timestamp of the message to add reaction to",
        primary=True,
        cef_types=["slack message ts"],
    )


class AddReactionOutput(PermissiveActionOutput):
    # The original app bound these columns to action_result.message and
    # action_result.status, which the SDK emits without column metadata, so they
    # are carried as explicit data fields.
    message: str | None = OutputField(
        example_values=["Reaction added successfully"], column_name="Message"
    )
    status: str | None = OutputField(
        example_values=["success", "failed"], column_name="Status"
    )
    ok: bool | None = None


@app.action(
    description="React to a message in Slack",
    action_type="generic",
    read_only=False,
    verbose="This method adds a reaction (emoji) to a message.",
    render_as="table",
)
def add_reaction(
    params: AddReactionParams, soar: SOARClient, asset: Asset
) -> AddReactionOutput:
    body = {
        "channel": params.destination,
        "name": params.emoji,
        "timestamp": params.message_ts,
    }

    logger.debug("Making rest call to add reaction")

    try:
        resp_json = slack_rest_call(asset.bot_token, SLACK_ADD_REACTION, body)
    except SlackFailure as e:
        raise SlackFailure(f"{SLACK_ERROR_ADDING_REACTION}: {e.message}") from e

    soar.set_message(SLACK_SUCCESSFULLY_REACTION_ADDED)

    return AddReactionOutput(
        message=SLACK_SUCCESSFULLY_REACTION_ADDED, status="success", **resp_json
    )
