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
from pathlib import Path

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
    SLACK_COMPLETE_UPLOAD,
    SLACK_ERROR_FILE_OR_CONTENT_NOT_PROVIDED,
    SLACK_ERROR_UNABLE_TO_FETCH_FILE,
    SLACK_ERROR_UPLOADING_FILE,
    SLACK_GET_UPLOAD_URL,
    SLACK_SUCCESSFULLY_FILE_UPLOAD,
)
from ..helper import (
    SlackFailure,
    resolve_conversation_id,
    slack_rest_call,
    upload_to_external_url,
)

logger = getLogger()

SLACK_DESTINATION_CEF = [
    "slack channel name",
    "slack channel id",
    "slack user name",
    "slack user id",
]


class UploadFileParams(Params):
    destination: str = Param(
        description="Channel (e.g. #channel or C1A1A1AAA) or user (e.g. @user or U1A1A1AAA) to upload to",
        primary=True,
        cef_types=SLACK_DESTINATION_CEF,
        column_name="Destination",
    )
    parent_message_ts: str | None = Param(
        description="Parent message timestamp to reply in thread",
        primary=True,
        cef_types=["slack message ts"],
    )
    file: str | None = Param(
        description="Vault ID of file to upload",
        primary=True,
        cef_types=["vault id", "sha1"],
        column_name="File",
    )
    content: str | None = Param(
        description="Contents of the file", column_name="File Content"
    )
    caption: str | None = Param(description="Caption to add to the file")
    filetype: str | None = Param(
        description="A file type identifier (https://docs.slack.dev/reference/objects/file-object/#types)",
        column_name="File Type",
    )
    filename: str | None = Param(
        description="Name of the file",
        primary=True,
        cef_types=["file name"],
        column_name="File Name",
    )


class CaptionOutput(ActionOutput):
    channel: str | None = None
    comment: str | None = None
    created: float | None = None
    id: str | None = None
    is_intro: bool | None = None
    timestamp: float | None = None
    user: str | None = OutputField(cef_types=SLACK_DESTINATION_CEF)


class FileOutput(ActionOutput):
    comments_count: float | None = None
    created: float | None = None
    display_as_bot: bool | None = None
    edit_link: str | None = OutputField(
        example_values=[
            "https://test.slack.com/files/U017MJM0352/F01NK7Y8LTU/adb3e6f532264cee9ccf4589808bb489"
        ]
    )
    editable: bool | None = None
    external_type: str | None = None
    file_access: str | None = OutputField(example_values=["visible"])
    filetype: str | None = None
    has_more_shares: bool | None = None
    has_rich_preview: bool | None = None
    id: str | None = None
    image_exif_rotation: float | None = None
    is_external: bool | None = None
    is_public: bool | None = None
    is_starred: bool | None = None
    lines: float | None = OutputField(example_values=[5])
    lines_more: float | None = OutputField(example_values=[0])
    media_display_type: str | None = OutputField(example_values=["audio"])
    mimetype: str | None = None
    mode: str | None = None
    name: str | None = OutputField(cef_types=["vault id"])
    original_h: float | None = None
    original_w: float | None = None
    permalink: str | None = OutputField(cef_types=["url"])
    permalink_public: str | None = OutputField(cef_types=["url"])
    pretty_type: str | None = None
    preview: str | None = None
    preview_highlight: str | None = None
    preview_is_truncated: bool | None = None
    public_url_shared: bool | None = None
    size: float | None = None
    timestamp: float | None = None
    title: str | None = OutputField(cef_types=["vault id"])
    url_private: str | None = OutputField(cef_types=["url"])
    url_private_download: str | None = OutputField(cef_types=["url"])
    user_team: str | None = OutputField(example_values=["E02PYRE04SJ"])


class ThumbnailUrlOutput(ActionOutput):
    img_url: str | None = OutputField(cef_types=["url"])


class ThumbnailOutput(ActionOutput):
    height: float | None = None
    img_url: str | None = OutputField(cef_types=["url"])
    width: float | None = None


class ThumbnailsOutput(ActionOutput):
    thumb_1024: ThumbnailOutput | None = None
    thumb_160: ThumbnailUrlOutput | None = None
    thumb_360: ThumbnailOutput | None = None
    thumb_480: ThumbnailOutput | None = None
    thumb_64: ThumbnailUrlOutput | None = None
    thumb_720: ThumbnailOutput | None = None
    thumb_80: ThumbnailUrlOutput | None = None
    thumb_800: ThumbnailOutput | None = None
    thumb_960: ThumbnailOutput | None = None
    thumb_pdf: ThumbnailOutput | None = None
    thumb_tiny: ThumbnailUrlOutput | None = None
    thumb_video: ThumbnailOutput | None = None


class UploadFileOutput(PermissiveActionOutput):
    caption: CaptionOutput | None = None
    destinations: str | None = OutputField(cef_types=SLACK_DESTINATION_CEF)
    file: FileOutput | None = None
    ok: bool | None = None
    sender: str | None = OutputField(cef_types=SLACK_DESTINATION_CEF)
    thumbnails: ThumbnailsOutput | None = None
    # The original app bound this column to action_result.status, which the SDK
    # emits without column metadata, so it is carried as an explicit data field.
    status: str | None = OutputField(
        example_values=["success", "failed"], column_name="Status"
    )


def _restructure_file_json(resp_json: dict, file_json: dict) -> dict:
    """Lift thumbnails, destinations and sender out of the file object.

    Slack returns thumbnails as flat 'thumb_<size>[_w|_h]' keys, which are far
    easier to consume when grouped per size.
    """
    thumbnail_dict: dict = {}
    pop_list = []

    for key, value in list(file_json.items()):
        if key.startswith("thumb"):
            pop_list.append(key)

            name_arr = key.split("_")
            thumb_dict = thumbnail_dict.setdefault(f"{name_arr[0]}_{name_arr[1]}", {})

            if len(name_arr) == 2:
                thumb_dict["img_url"] = value
            elif name_arr[2] == "w":
                thumb_dict["width"] = value
            elif name_arr[2] == "h":
                thumb_dict["height"] = value

        elif key == "initial_comment":
            resp_json["caption"] = value
            pop_list.append(key)

        elif key in ("channels", "ims", "groups"):
            resp_json.setdefault("destinations", [])
            resp_json["destinations"] += value
            pop_list.append(key)

        elif key == "username":
            pop_list.append(key)

        elif key == "user":
            resp_json["sender"] = value
            pop_list.append(key)

    for poppee in pop_list:
        file_json.pop(poppee, None)

    resp_json["thumbnails"] = thumbnail_dict
    resp_json["file"] = file_json

    return resp_json


@app.action(
    description="Upload file to Slack",
    action_type="generic",
    read_only=False,
    verbose="The <b>destination</b> parameter can be a channel ID (e.g.  C1A1A1AAA), a channel name (e.g. #general). When uploading to a channel, the configured bot user must have been added to the channel.  The <b>file</b> parameter takes the vault ID of a file that will be uploaded to Slack. Only files in the vault can be uploaded to Slack.",
    render_as="table",
)
def upload_file(
    params: UploadFileParams, soar: SOARClient, asset: Asset
) -> UploadFileOutput:
    destinations = [
        value.strip() for value in params.destination.split(",") if value.strip()
    ]
    conversation_ids = [
        resolve_conversation_id(asset.bot_token, destination)
        for destination in destinations
    ]

    filetype = params.filetype
    file_name = params.filename
    caption = params.caption or "Uploaded from Splunk SOAR"

    if params.file:
        try:
            attachments = soar.vault.get_attachment(vault_id=params.file)
        except Exception as e:
            raise SlackFailure(
                "{}. {}".format(SLACK_ERROR_UNABLE_TO_FETCH_FILE.format(key="info"), e)
            ) from e

        if not attachments:
            raise SlackFailure(SLACK_ERROR_UNABLE_TO_FETCH_FILE.format(key="info"))

        attachment = attachments[0]

        if not attachment.path:
            raise SlackFailure(SLACK_ERROR_UNABLE_TO_FETCH_FILE.format(key="path"))

        if not attachment.name:
            raise SlackFailure(SLACK_ERROR_UNABLE_TO_FETCH_FILE.format(key="name"))

        if not file_name:
            file_name = attachment.name

        try:
            file_bytes = Path(attachment.path).read_bytes()
        except Exception as e:
            raise SlackFailure(f"Unable to read vault file: {e}") from e

    elif params.content is not None:
        file_bytes = params.content.encode("utf-8")
        if not filetype:
            filetype = "text"
        if not file_name:
            file_name = f"{filetype} snippet"

    else:
        raise SlackFailure(SLACK_ERROR_FILE_OR_CONTENT_NOT_PROVIDED)

    if not file_bytes:
        raise SlackFailure("File size must be greater than zero")

    upload_request_body: dict = {"filename": file_name, "length": len(file_bytes)}
    if filetype:
        upload_request_body["snippet_type"] = filetype

    logger.debug("Requesting external upload URL from Slack")
    upload_url_resp = slack_rest_call(
        asset.bot_token, SLACK_GET_UPLOAD_URL, upload_request_body
    )

    upload_url = upload_url_resp.get("upload_url")
    file_id = upload_url_resp.get("file_id")

    if not upload_url or not file_id:
        raise SlackFailure(
            "Slack response did not include upload_url or file_id required for file upload"
        )

    logger.debug("Uploading file content to Slack-provided upload URL")
    upload_to_external_url(upload_url, file_bytes)

    complete_payload = {
        "files": json.dumps([{"id": file_id, "title": file_name}]),
        "channels": ",".join(conversation_ids),
        "initial_comment": caption,
    }

    if params.parent_message_ts:
        complete_payload["thread_ts"] = params.parent_message_ts

    logger.debug("Completing external file upload")

    try:
        resp_json = slack_rest_call(
            asset.bot_token, SLACK_COMPLETE_UPLOAD, complete_payload
        )
    except SlackFailure as e:
        raise SlackFailure(f"{SLACK_ERROR_UPLOADING_FILE}: {e.message}") from e

    file_list = resp_json.get("files", [])
    file_json = file_list[0] if file_list else resp_json.get("file", {})

    resp_json = _restructure_file_json(resp_json, file_json)

    soar.set_message(SLACK_SUCCESSFULLY_FILE_UPLOAD)

    return UploadFileOutput(status="success", **resp_json)
