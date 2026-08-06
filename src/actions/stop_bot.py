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
from soar_sdk.action_results import OutputField, PermissiveActionOutput
from soar_sdk.params import Params

from ..app import Asset, app, stop_slack_bot


class StopBotParams(Params):
    pass


class StopBotOutput(PermissiveActionOutput):
    # The original app bound these columns to action_result.status and
    # action_result.message, which the SDK emits without column metadata, so they
    # are carried as explicit data fields.
    status: str | None = OutputField(
        example_values=["success", "failed"], column_name="Status"
    )
    message: str | None = OutputField(
        example_values=["SlackBot has been stopped."], column_name="Message"
    )


@app.action(
    description="Stop SlackBot",
    action_type="correct",
    read_only=False,
    verbose="This action will stop SlackBot if it is running. It will also disable ingestion if it is enabled.",
    render_as="table",
)
def stop_bot(params: StopBotParams, soar: SOARClient, asset: Asset) -> StopBotOutput:
    message = stop_slack_bot(asset)

    soar.set_message(message)

    return StopBotOutput(status="success", message=message)
