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
from typing import Any

import requests
from bs4 import BeautifulSoup
from soar_sdk.exceptions import ActionFailure
from soar_sdk.logging import getLogger

from .consts import (
    SLACK_BASE_URL,
    SLACK_CONVERSATIONS_OPEN,
    SLACK_DEFAULT_LIMIT,
    SLACK_ERROR_BOT_TOKEN_INVALID,
    SLACK_ERROR_CHANNEL_NOT_FOUND,
    SLACK_ERROR_DATA_NOT_FOUND_IN_OUTPUT,
    SLACK_ERROR_EMPTY_RESPONSE,
    SLACK_ERROR_FROM_SERVER,
    SLACK_ERROR_INVALID_INT,
    SLACK_ERROR_NEGATIVE_AND_ZERO_INT,
    SLACK_ERROR_NEGATIVE_INT,
    SLACK_ERROR_NOT_IN_CHANNEL,
    SLACK_ERROR_OPENING_DM_CHANNEL,
    SLACK_ERROR_PAGINATION_LIMIT,
    SLACK_ERROR_REST_CALL_FAILED,
    SLACK_ERROR_SERVER_CONNECTION,
    SLACK_ERROR_UNABLE_TO_DECODE_JSON_RESPONSE,
    SLACK_ERROR_UNABLE_TO_PARSE_JSON_RESPONSE,
    SLACK_ERROR_USER_NOT_FOUND,
    SLACK_LIST_CHANNEL,
    SLACK_MAX_PAGINATION_PAGES,
    SLACK_REST_CALL_TIMEOUT,
    SLACK_UNABLE_TO_PARSE_ERROR_DETAILS,
    SLACK_USER_LIST,
)

logger = getLogger()


class SlackFailure(ActionFailure):
    """Action failure reporting the Slack error message without any prefix."""

    def __str__(self) -> str:
        """Return the raw failure message."""
        return self.message


def _process_html_response(response: requests.Response) -> str:
    try:
        soup = BeautifulSoup(response.text, "html.parser")

        for element in soup(["script", "style", "footer", "nav"]):
            element.extract()

        split_lines = [line.strip() for line in soup.text.split("\n") if line.strip()]
        error_text = "\n".join(split_lines)
    except Exception:
        error_text = SLACK_UNABLE_TO_PARSE_ERROR_DETAILS

    return f"Status Code: {response.status_code}. Data from server:\n{error_text}\n"


def _process_json_response(response: requests.Response) -> dict:
    try:
        resp_json = response.json()
    except Exception as e:
        raise SlackFailure(
            SLACK_ERROR_UNABLE_TO_PARSE_JSON_RESPONSE.format(error=e)
        ) from e

    # The 'ok' parameter in a response from slack says if the call passed or failed
    if resp_json.get("ok", "") is not False:
        return resp_json

    error = resp_json.get("error", "")
    if error == "invalid_auth":
        error = SLACK_ERROR_BOT_TOKEN_INVALID
    elif error == "not_in_channel":
        error = SLACK_ERROR_NOT_IN_CHANNEL
    elif not error:
        error = SLACK_ERROR_FROM_SERVER

    raise SlackFailure(error)


def _process_response(response: requests.Response) -> dict:
    content_type = response.headers.get("Content-Type", "")

    if "json" in content_type:
        return _process_json_response(response)

    if "html" in content_type:
        raise SlackFailure(_process_html_response(response))

    if not response.text:
        if response.status_code == 200:
            return {}
        raise SlackFailure(SLACK_ERROR_EMPTY_RESPONSE.format(code=response.status_code))

    raise SlackFailure(
        f"Can't process response from server. Status Code: {response.status_code} Data from server: {response.text}"
    )


def slack_rest_call(
    bot_token: str,
    endpoint: str,
    body: dict | None = None,
    headers: dict | None = None,
    files: dict | None = None,
) -> dict:
    """Send a form encoded call to the Slack API using the configured bot token."""
    body = dict(body or {})
    body["token"] = bot_token

    try:
        response = requests.post(
            f"{SLACK_BASE_URL}{endpoint}",
            data=body,
            headers=headers,
            files=files,
            timeout=SLACK_REST_CALL_TIMEOUT,
        )
    except Exception as e:
        raise SlackFailure(f"{SLACK_ERROR_SERVER_CONNECTION}. {e}") from e

    return _process_response(response)


def slack_bearer_call(token: str, endpoint: str) -> dict:
    """Send a call to the Slack API authenticated with a bearer token only.

    App level tokens, such as the socket token, are only accepted in the
    Authorization header.
    """
    try:
        response = requests.post(
            f"{SLACK_BASE_URL}{endpoint}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=SLACK_REST_CALL_TIMEOUT,
        )
    except Exception as e:
        raise SlackFailure(f"{SLACK_ERROR_SERVER_CONNECTION}. {e}") from e

    return _process_response(response)


def rest_call(
    url: str, method: str = "get", headers: dict | None = None, body: dict | None = None
) -> dict:
    """Send a JSON encoded call to the Slack API using a caller supplied token."""
    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            data=json.dumps(body) if body is not None else None,
            timeout=SLACK_REST_CALL_TIMEOUT,
        )
    except Exception as e:
        raise SlackFailure(f"{SLACK_ERROR_REST_CALL_FAILED}. {e}") from e

    try:
        resp_json = response.json()
    except Exception as e:
        raise SlackFailure(SLACK_ERROR_UNABLE_TO_DECODE_JSON_RESPONSE) from e

    if "failed" in resp_json:
        raise SlackFailure(
            "{}. Message: {}".format(
                SLACK_ERROR_REST_CALL_FAILED, resp_json.get("message", "NA")
            )
        )

    if 200 <= response.status_code <= 399:
        return resp_json

    details = json.dumps(resp_json) if resp_json else "NA"

    raise SlackFailure(
        f"Error from server: Status code: {response.status_code} Details: {details}"
    )


def upload_to_external_url(upload_url: str, file_content: bytes) -> None:
    """Upload file bytes to the Slack provided external upload URL."""
    headers = {"Content-Type": "application/octet-stream"}

    try:
        response = requests.post(
            upload_url,
            data=file_content,
            headers=headers,
            timeout=SLACK_REST_CALL_TIMEOUT,
        )
    except Exception as e:
        raise SlackFailure(f"Failed to upload file: {e}") from e

    if not 200 <= response.status_code < 300:
        raise SlackFailure(
            f"File upload failed with status {response.status_code}: {response.text}"
        )


def paginate(
    bot_token: str,
    endpoint: str,
    key: str,
    body: dict | None = None,
    limit: int | None = None,
) -> dict:
    """Fetch results from multiple API calls using pagination for the given endpoint."""
    body = dict(body or {})
    body["limit"] = SLACK_DEFAULT_LIMIT
    results: dict[str, Any] = {}

    while True:
        resp_json = slack_rest_call(bot_token, endpoint, body)

        key_result_value = resp_json.get(key, [])

        if not results:
            if not key_result_value:
                raise SlackFailure(
                    SLACK_ERROR_DATA_NOT_FOUND_IN_OUTPUT.format(
                        key=("users" if key == "members" else key)
                    )
                )
            results = resp_json
        else:
            results[key].extend(key_result_value)

        if limit and len(results[key]) >= limit:
            results[key] = results[key][:limit]
            return results

        next_cursor = resp_json.get("response_metadata", {}).get("next_cursor", "")

        if not next_cursor:
            break

        body["cursor"] = next_cursor

    return results


def is_channel_id(destination: str) -> bool:
    """Determine if the provided destination already represents a channel/user ID."""
    if not destination:
        return False

    # If it starts with @ or #, it's a name, not an ID
    if destination.startswith(("@", "#")):
        return False

    # Channel IDs: C (public), G (private/group), D (direct message). User IDs: U, W
    return destination[:1] in {"C", "G", "D", "U", "W"}


def _find_by_name(
    bot_token: str, endpoint: str, key: str, name: str, body: dict
) -> str | None:
    name_to_find = name.lstrip("@#").lower()
    seen_cursors = set()

    for _ in range(SLACK_MAX_PAGINATION_PAGES):
        resp_json = slack_rest_call(bot_token, endpoint, body)

        for item in resp_json.get(key, []):
            if item.get("name", "").lower() == name_to_find:
                return item.get("id")

        next_cursor = resp_json.get("response_metadata", {}).get("next_cursor", "")

        if not next_cursor:
            return None

        if next_cursor in seen_cursors:
            raise SlackFailure(SLACK_ERROR_PAGINATION_LIMIT.format(endpoint=endpoint))
        seen_cursors.add(next_cursor)
        body["cursor"] = next_cursor

    raise SlackFailure(SLACK_ERROR_PAGINATION_LIMIT.format(endpoint=endpoint))


def get_channel_id_from_name(bot_token: str, channel_name: str) -> str:
    """Resolve a Slack channel name to its ID using the conversations.list API."""
    body = {"limit": 200, "types": "public_channel,private_channel"}
    channel_id = _find_by_name(
        bot_token, SLACK_LIST_CHANNEL, "channels", channel_name, body
    )

    if not channel_id:
        raise SlackFailure(SLACK_ERROR_CHANNEL_NOT_FOUND.format(name=channel_name))

    return channel_id


def get_user_id_from_name(bot_token: str, user_name: str) -> str:
    """Resolve a Slack user name to its ID using the users.list API."""
    body = {"limit": 200}
    user_id = _find_by_name(bot_token, SLACK_USER_LIST, "members", user_name, body)

    if not user_id:
        raise SlackFailure(SLACK_ERROR_USER_NOT_FOUND.format(name=user_name))

    return user_id


def get_dm_channel_id(bot_token: str, user_id: str) -> str:
    """Open a direct message channel with a user and return the channel ID."""
    logger.debug(f"Opening DM channel with user {user_id}")
    resp_json = slack_rest_call(bot_token, SLACK_CONVERSATIONS_OPEN, {"users": user_id})

    channel_id = resp_json.get("channel", {}).get("id")

    if not channel_id:
        raise SlackFailure(SLACK_ERROR_OPENING_DM_CHANNEL)

    return channel_id


def resolve_conversation_id(bot_token: str, destination: str) -> str:
    """Resolve a channel or user name/ID to the conversation ID to post into."""
    if is_channel_id(destination):
        if destination.startswith(("U", "W")):
            logger.debug(f"User ID '{destination}' provided, opening DM channel")
            return get_dm_channel_id(bot_token, destination)
        return destination

    if destination.startswith("@"):
        logger.debug(f"User name '{destination}' provided, resolving to user ID")
        user_id = get_user_id_from_name(bot_token, destination)
        logger.debug(f"User ID '{user_id}' resolved, opening DM channel")
        return get_dm_channel_id(bot_token, user_id)

    logger.debug(f"Channel name '{destination}' provided, resolving to channel ID")
    return get_channel_id_from_name(bot_token, destination)


def validate_integer(parameter: Any, key: str, allow_zero: bool = False) -> int:
    """Validate that the parameter is a positive integer and return it as an int."""
    try:
        if not float(parameter).is_integer():
            raise SlackFailure(SLACK_ERROR_INVALID_INT.format(key=key))
        parameter = int(parameter)
    except SlackFailure:
        raise
    except Exception as e:
        raise SlackFailure(SLACK_ERROR_INVALID_INT.format(key=key)) from e

    if parameter < 0:
        raise SlackFailure(SLACK_ERROR_NEGATIVE_INT.format(key=key))
    if not allow_zero and parameter == 0:
        raise SlackFailure(SLACK_ERROR_NEGATIVE_AND_ZERO_INT.format(key=key))

    return parameter
