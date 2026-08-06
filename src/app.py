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

import json
import os
import shlex
import shutil
import subprocess
import urllib.parse
from collections.abc import Iterator
from pathlib import Path

from soar_sdk.abstract import SOARClient
from soar_sdk.app import App
from soar_sdk.asset import AssetField, BaseAsset, FieldCategory
from soar_sdk.logging import getLogger
from soar_sdk.models.artifact import Artifact
from soar_sdk.models.container import Container
from soar_sdk.params import OnPollParams
from soar_sdk.webhooks.models import WebhookRequest, WebhookResponse

from .consts import (
    SLACK_APP_ID,
    SLACK_AUTH_TEST,
    SLACK_CONNECTIONS_OPEN,
    SLACK_ERROR_ANSWER_FILE_NOT_FOUND,
    SLACK_ERROR_AUTH_FAILED,
    SLACK_ERROR_BASE_URL_NOT_FOUND,
    SLACK_ERROR_CALLBACK_ID_NOT_FOUND,
    SLACK_ERROR_COUDNT_STOP_SLACKBOT,
    SLACK_ERROR_COULD_NOT_GET_BOT_ID,
    SLACK_ERROR_INVALID_FILE_PATH,
    SLACK_ERROR_PARSE_JSON_FROM_CALLBACK_ID,
    SLACK_ERROR_PAYLOAD_NOT_FOUND,
    SLACK_ERROR_PROCESS_RESPONSE,
    SLACK_ERROR_SLACKBOT_NOT_RUNNING,
    SLACK_ERROR_SLACKBOT_RUNNING_WITH_SAME_BOT_TOKEN,
    SLACK_ERROR_STATE_FILE_NOT_FOUND,
    SLACK_ERROR_TEST_CONNECTIVITY_FAILED,
    SLACK_ERROR_WHILE_WRITING_ANSWER_FILE,
    SLACK_JSON_BOT_TOKEN,
    SLACK_JSON_PH_AUTH_TOKEN,
    SLACK_JSON_SOCKET_TOKEN,
    SLACK_SOCKET_TOKEN_ERROR,
    SLACK_SUCCESSFULLY_SLACKBOT_RUNNING,
    SLACK_SUCCESSFULLY_SLACKBOT_STARTED,
    SLACK_SUCCESSFULLY_SLACKBOT_STOPPED,
    SLACK_SUCCESSFULLY_TEST_CONNECTIVITY_PASSED,
)
from .helper import SlackFailure, slack_bearer_call, slack_rest_call
from .interactive import answer_path, process_payload, state_dir

logger = getLogger()


class Asset(BaseAsset):
    bot_token: str = AssetField(
        description="Bot User OAuth Token",
        sensitive=True,
        category=FieldCategory.CONNECTIVITY,
    )
    verification_token: str = AssetField(
        description="Verification Token",
        sensitive=True,
        category=FieldCategory.CONNECTIVITY,
    )
    user_token: str | None = AssetField(
        description="User OAuth Token",
        sensitive=True,
        category=FieldCategory.CONNECTIVITY,
    )
    socket_token: str | None = AssetField(
        description="Socket Token",
        sensitive=True,
        category=FieldCategory.CONNECTIVITY,
    )
    ph_auth_token: str | None = AssetField(
        description="Automation User Auth Token",
        sensitive=True,
        category=FieldCategory.CONNECTIVITY,
    )
    timeout: int | None = AssetField(
        description="Question timeout (in minutes)",
        default=30,
        category=FieldCategory.ACTION,
    )
    response_poll_interval: int | None = AssetField(
        description="How often to poll for a response (in seconds)",
        default=30,
        category=FieldCategory.ACTION,
    )
    permit_bot_act: bool | None = AssetField(
        description="Permit 'act' commands on Bot (I.E. @SOARbot act 'list channels' --container 123 --asset slack)",
        category=FieldCategory.INGEST,
    )
    permit_bot_playbook: bool | None = AssetField(
        description="Permit 'run_playbook' commands on Bot (I.E. @SOARbot run_playbook <playbook_id> <container_id>)",
        category=FieldCategory.INGEST,
    )
    permit_bot_container: bool | None = AssetField(
        description="Permit 'get_container' commands on Bot (I.E. @SOARbot get_container <container_id>)",
        category=FieldCategory.INGEST,
    )
    permit_bot_list: bool | None = AssetField(
        description="Permit 'list' commands on Bot (I.E. @SOARbot list [actions|containers])",
        category=FieldCategory.INGEST,
    )
    permitted_bot_users: str | None = AssetField(
        description="Users permitted to use Bot Actions. Comma seperated list of Member IDs. Leave blank to allow all users (Default Setting)",
        category=FieldCategory.INGEST,
    )


app = App(
    name="Slack",
    app_type="information",
    logo="logo_slack.svg",
    logo_dark="logo_slack_dark.svg",
    product_vendor="Slack Technologies",
    product_name="Slack",
    publisher="Splunk",
    appid=SLACK_APP_ID,
    fips_compliant=True,
    asset_cls=Asset,
    min_phantom_version="6.3.0",
).enable_webhooks(default_requires_auth=False)


@app.test_connectivity()
def test_connectivity(soar: SOARClient, asset: Asset) -> None:
    try:
        resp_json = slack_rest_call(asset.bot_token, SLACK_AUTH_TEST)
    except SlackFailure:
        logger.progress(SLACK_ERROR_TEST_CONNECTIVITY_FAILED)
        raise

    logger.progress(
        "Auth check to Slack passed. Configuring app for team, {}".format(
            resp_json.get("team", "Unknown Team")
        )
    )

    bot_username = resp_json.get("user")
    bot_user_id = resp_json.get("user_id")

    logger.progress(
        f"Got username, {bot_username}, and user ID, {bot_user_id}, for the bot"
    )

    state = asset.cache_state.get_all()
    state["bot_name"] = bot_username
    state["bot_id"] = bot_user_id
    asset.cache_state.put_all(state)

    soar.set_message(SLACK_SUCCESSFULLY_TEST_CONNECTIVITY_PASSED)
    logger.progress(SLACK_SUCCESSFULLY_TEST_CONNECTIVITY_PASSED)


@app.on_poll()
def on_poll(
    params: OnPollParams, soar: SOARClient, asset: Asset
) -> Iterator[Container | Artifact]:
    """Start SlackBot and make health checks to it.

    The bot runs as a separate long lived process so that it can keep a socket mode
    connection open, which means this action never ingests any containers.
    """
    import sh  # noqa: PLC0415

    resp_json = slack_rest_call(asset.bot_token, SLACK_AUTH_TEST)
    bot_id = resp_json.get("user_id")

    if not bot_id:
        raise SlackFailure(SLACK_ERROR_COULD_NOT_GET_BOT_ID)

    # Certain bot actions fail if these are missing from the state the bot loads at
    # startup, so store them here too in case test connectivity was never run.
    _stage_bot_state(soar, asset, bot_id, resp_json.get("user"))

    container_count = int(params.container_count or 0)
    pid = asset.cache_state.get("pid")

    if pid:
        try:
            if params.is_manual_poll():
                logger.progress(f"Container Count: {container_count}")
                if container_count == 1234:
                    sh.kill(pid)
                    logger.progress(
                        f"Container count set to 1234, stopping slack_bot.py at pid {pid}"
                    )
                elif container_count == int(pid):
                    sh.kill(pid)
                    logger.progress("pid passed in as container count, stopping bot")
                    soar.set_message("bot has been stopped")
                    return
                else:
                    logger.progress(
                        "HINT: Set Maximum Containers to 1234 to restart slackbot, or set to PID to stop slackbot"
                    )

            if "slack_bot.py" in sh.ps("ww", pid):
                logger.progress(f"Detected SlackBot running with pid {pid}")
                soar.set_message(SLACK_SUCCESSFULLY_SLACKBOT_RUNNING)
                return
        except Exception:
            logger.debug("Found no SlackBot running with the stored pid")

    asset_id = soar.get_asset_id()
    app_version = str(app.app_meta_info["app_version"])

    try:
        ps_out = str(sh.grep(sh.ps("ww", "aux"), "slack_bot.py"))
        old_pid = shlex.split(ps_out)[1]
        if app_version not in ps_out:
            logger.progress(
                f"Found an old version of slackbot running with pid {old_pid}, going to kill it"
            )
            sh.kill(old_pid)
        elif asset_id in ps_out:
            asset.cache_state["pid"] = int(old_pid)
            soar.set_message(SLACK_ERROR_SLACKBOT_RUNNING_WITH_SAME_BOT_TOKEN)
            return
    except Exception:
        logger.debug("Found no other SlackBot process running")

    if not _socket_token_is_valid(asset):
        logger.progress("Failed to start Slack Bot")
        raise SlackFailure(SLACK_SOCKET_TOKEN_ERROR)

    logger.progress("Starting SlackBot")

    slack_bot_filename = str(Path(__file__).parent / "slack_bot.py")
    command = [*_python_command(), slack_bot_filename, asset_id, app_version]

    try:
        process = subprocess.Popen(command)  # noqa: S603
    except Exception as e:
        raise SlackFailure(f"Failed to start SlackBot: {e}") from e

    asset.cache_state["pid"] = process.pid
    logger.progress(f"Started SlackBot with pid: {process.pid}")
    soar.set_message(SLACK_SUCCESSFULLY_SLACKBOT_STARTED)
    return
    yield  # keeps this action a generator, as on poll actions must be


def _socket_token_is_valid(asset: Asset) -> bool:
    """Check the configured socket token can open an app level connection."""
    try:
        resp_json = slack_bearer_call(asset.socket_token or "", SLACK_CONNECTIONS_OPEN)
    except SlackFailure:
        return False

    return bool(resp_json.get("ok"))


def _python_command() -> list[str]:
    """Return the interpreter prefix used to launch the SlackBot process."""
    if phenv_path := shutil.which("phenv"):
        logger.progress("Using phenv wrapper")
        return [phenv_path, "python3"]

    # Isolated automation broker: use the direct Python path from the environment
    python313_location = os.environ.get(
        "PYTHON313_LOCATION", "/opt/phantom/usr/python313"
    )
    py3 = Path(python313_location) / "bin" / "python3"

    if not py3.is_file():
        raise SlackFailure(f"Python executable not found at: {py3}")

    logger.progress(f"phenv not available, using direct Python path: {py3}")
    return [str(py3)]


def _stage_bot_state(
    soar: SOARClient, asset: Asset, bot_id: str, bot_name: str | None
) -> None:
    """Write everything the standalone SlackBot process reads out of asset state."""
    base_url = soar.get("rest/system_info").json().get("base_url", "")

    if not base_url:
        raise SlackFailure(SLACK_ERROR_BASE_URL_NOT_FOUND)

    state = asset.cache_state.get_all()
    state.update(
        {
            "bot_id": bot_id,
            "bot_name": bot_name,
            "ph_base_url": base_url.rstrip("/") + "/",
            SLACK_JSON_BOT_TOKEN: asset.bot_token,
            SLACK_JSON_SOCKET_TOKEN: asset.socket_token,
            SLACK_JSON_PH_AUTH_TOKEN: asset.ph_auth_token,
            "permit_bot_act": asset.permit_bot_act or False,
            "permit_bot_playbook": asset.permit_bot_playbook or False,
            "permit_bot_container": asset.permit_bot_container or False,
            "permit_bot_list": asset.permit_bot_list or False,
            "permitted_bot_users": asset.permitted_bot_users or "",
        }
    )
    asset.cache_state.put_all(state)


def stop_slack_bot(asset: Asset) -> str:
    """Terminate the SlackBot process, returning the message to report."""
    import sh  # noqa: PLC0415

    pid = asset.cache_state.get("pid")
    logger.debug(f"PID of Bot : {pid}")

    if pid:
        del asset.cache_state["pid"]
        try:
            running = "slack_bot.py" in sh.ps("ww", pid)
        except Exception as e:
            raise SlackFailure(SLACK_ERROR_SLACKBOT_NOT_RUNNING) from e

        if not running:
            raise SlackFailure(SLACK_ERROR_SLACKBOT_NOT_RUNNING)
    else:
        try:
            ps_out = sh.grep(sh.ps("ww", "aux"), "slack_bot.py")
            pid = shlex.split(str(ps_out))[1]
        except Exception as e:
            raise SlackFailure(SLACK_ERROR_SLACKBOT_NOT_RUNNING) from e

    try:
        sh.kill(pid)
    except Exception as e:
        raise SlackFailure(SLACK_ERROR_COUDNT_STOP_SLACKBOT) from e

    return SLACK_SUCCESSFULLY_SLACKBOT_STOPPED


@app.webhook("interactive", allowed_methods=["POST"])
def handle_interactive_message(request: WebhookRequest[Asset]) -> WebhookResponse:
    """Record a user's answer to a question asked by one of the ask question actions.

    Slack posts here when a user clicks one of the response buttons. The answer is
    written to a file which the polling actions and SlackBot both read.
    """
    try:
        form = urllib.parse.parse_qs(request.body or "")
        raw_payload = next(iter(form.get("payload", [])), "")

        if not raw_payload:
            return WebhookResponse.text_response(SLACK_ERROR_PAYLOAD_NOT_FOUND, 400)

        payload = json.loads(raw_payload)
        callback_id = payload.get("callback_id")

        if not callback_id:
            return WebhookResponse.text_response(SLACK_ERROR_CALLBACK_ID_NOT_FOUND, 400)

        try:
            callback_json = json.loads(callback_id)
        except Exception as e:
            return WebhookResponse.text_response(
                SLACK_ERROR_PARSE_JSON_FROM_CALLBACK_ID.format(error=e), 400
            )

        try:
            int(callback_json.get("asset_id"))
        except (TypeError, ValueError):
            return WebhookResponse.text_response(SLACK_ERROR_STATE_FILE_NOT_FOUND, 400)

        verification_token = request.asset.verification_token
        if not verification_token or verification_token != payload.get("token"):
            return WebhookResponse.text_response(SLACK_ERROR_AUTH_FAILED, 400)

        qid = callback_json.get("qid")

        if not qid:
            return WebhookResponse.text_response(SLACK_ERROR_ANSWER_FILE_NOT_FOUND, 400)

        try:
            path = answer_path(qid)
        except ValueError:
            return WebhookResponse.text_response(SLACK_ERROR_INVALID_FILE_PATH, 400)

        try:
            state_dir().mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(process_payload(payload, path)))
        except Exception as e:
            return WebhookResponse.text_response(
                SLACK_ERROR_WHILE_WRITING_ANSWER_FILE.format(error=e), 400
            )

        confirmation = callback_json.get("confirmation", "Received response")
        return WebhookResponse.text_response(f"Response: {confirmation}")

    except Exception as e:
        return WebhookResponse.text_response(
            SLACK_ERROR_PROCESS_RESPONSE.format(error=e), 500
        )


# Register the actions. The imports live at the bottom so that the `app` instance
# their decorators reference already exists.
from .actions import add_reaction  # noqa: F401
from .actions import ask_question  # noqa: F401
from .actions import ask_question_channel  # noqa: F401
from .actions import create_channel  # noqa: F401
from .actions import get_history  # noqa: F401
from .actions import get_response  # noqa: F401
from .actions import get_user  # noqa: F401
from .actions import invite_users  # noqa: F401
from .actions import list_channels  # noqa: F401
from .actions import list_users  # noqa: F401
from .actions import send_message  # noqa: F401
from .actions import stop_bot  # noqa: F401
from .actions import upload_file  # noqa: F401
