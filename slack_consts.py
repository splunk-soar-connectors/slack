# File: slack_consts.py
#
# Copyright (c) 2016-2025 Splunk Inc.
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
#
#
# Action IDs
ACTION_ID_TEST_CONNECTIVITY = "test_connectivity"
ACTION_ID_LIST_CHANNELS = "list_channels"
ACTION_ID_POST_MESSAGE = "send_message"
ACTION_ID_ADD_REACTION = "add_reaction"
ACTION_ID_ASK_QUESTION = "ask_question"
ACTION_ID_ASK_QUESTION_CHANNLE = "ask_question_channel"
ACTION_ID_GET_RESPONSE = "get_response"
ACTION_ID_UPLOAD_FILE = "upload_file"
ACTION_ID_LIST_USERS = "list_users"
ACTION_ID_GET_USER = "get_user"
ACTION_ID_STOP_BOT = "stop_bot"
ACTION_ID_ON_POLL = "on_poll"
ACTION_ID_CREATE_CHANNEL = "create_channel"
ACTION_ID_INVITE_USERS = "invite_users"
ACTION_ID_GET_HISTORY = "get_history"

SLACK_BASE_URL = "https://slack.com/api/"
SLACK_MESSAGE_LIMIT = 40000
SLACK_DEFAULT_LIMIT = 100
SLACK_CONFIRMATION_LIMIT = 174

SLACK_JSON_BOT_TOKEN = "bot_token"
SLACK_JSON_PH_AUTH_TOKEN = "ph_auth_token"
SLACK_JSON_VERIFICATION_TOKEN = "verification_token"
SLACK_JSON_SOCKET_TOKEN = "socket_token"
SLACK_JSON_PERMIT_BOT_ACT = "permit_bot_act"
SLACK_JSON_PERMIT_BOT_PLAYBOOK = "permit_bot_playbook"
SLACK_JSON_PERMIT_BOT_CONTAINER = "permit_bot_container"
SLACK_JSON_PERMIT_BOT_LIST = "permit_bot_list"
SLACK_JSON_PERMITTED_USERS = "permitted_bot_users"

SLACK_PHANTOM_ASSET_INFO_URL = "{url}rest/asset/{asset_id}"
SLACK_PHANTOM_SYS_INFO_URL = "{url}rest/system_info"
SLACK_PHANTOM_ICON = "https://www.phantom.us/img/phantom_icon_160x160.png"

SLACK_ADD_REACTION = "reactions.add"
SLACK_CHANNEL_CREATE_ENDPOINT = "conversations.create"
SLACK_INVITE_TO_CHANNEL = "conversations.invite"
SLACK_LIST_CHANNEL = "conversations.list"
SLACK_OPEN_CONVERSATION = "conversations.open"
SLACK_AUTH_TEST = "auth.test"
SLACK_USER_LIST = "users.list"
SLACK_USER_INFO = "users.info"
SLACK_USER_LOOKUP_BY_EMAIL = "users.lookupByEmail"
SLACK_SEND_MESSAGE = "chat.postMessage"
SLACK_GET_UPLOAD_URL = "files.getUploadURLExternal"
SLACK_COMPLETE_UPLOAD = "files.completeUploadExternal"
SLACK_CONVERSATIONS_HISTORY = "conversations.history"
SLACK_THREADS_HISTORY = "conversations.replies"

SLACK_TC_STATUS_SLEEP = 2
SLACK_TC_FILE = "slack_auth_task.out"

SLACK_SUCCESSFULLY_MESSAGE = "Slack message post successfulLY"

SLACK_ERROR_MESSAGE_RETURNED_NO_DATA = "Message post did not receive response"
SLACK_ERROR_SERVER_CONNECTION = "Connection to server failed"
SLACK_ERROR_UNSUPPORTED_METHOD = "Unsupported method"
SLACK_ERROR_FROM_SERVER = "Got unknown error from the Slack server"
SLACK_ERROR_NOT_IN_VAULT = "No item in vault has the supplied ID"
SLACK_ERROR_MESSAGE_UNAVAILABLE = "Error message unavailable. Please check the asset configuration and|or action parameters"
SLACK_ERROR_INVALID_FILE_PATH = "The file path is invalid"
SLACK_ERROR_INVALID_INT = "Please provide a valid integer value in the {key} parameter"
SLACK_ERROR_NEGATIVE_AND_ZERO_INT = "Please provide a valid non-zero positive integer value in the {key} parameter"
SLACK_ERROR_NEGATIVE_INT = "Please provide a valid non-negative integer value in the {key} parameter"
SLACK_ERROR_UNABLE_TO_FETCH_FILE = "Unable to fetch the file {key}"
SLACK_ERROR_PAYLOAD_NOT_FOUND = "Found no payload field in rest post body"
SLACK_ERROR_CALLBACK_ID_NOT_FOUND = "Found no callback_id field in payload"
SLACK_ERROR_PARSE_JSON_FROM_CALLBACK_ID = "Could not parse JSON from callback_id field in payload: {error}"
SLACK_ERROR_STATE_DIR_NOT_FOUND = "Found no state directory in callback"
SLACK_ERROR_UNEXPECTED_STATE_DIR = "Unexpected state directory found in callback"
SLACK_ERROR_STATE_FILE_NOT_FOUND = "Found no state filename in callback"
SLACK_ERROR_UNABLE_TO_READ_STATE_FILE = "Could not properly read state file: {error}"
SLACK_ERROR_AUTH_FAILED = "Authorization failed. Tokens do not match."
SLACK_ERROR_ANSWER_FILE_NOT_FOUND = "Found no answer filename in callback"
SLACK_ERROR_COULD_NOT_OPEN_ANSWER_FILE = "Could not open answer file for writing: {error}"
SLACK_ERROR_WHILE_WRITING_ANSWER_FILE = "Error occurred while writing in answer file: {error}"
SLACK_ERROR_PROCESS_RESPONSE = "There was an error processing the response: {error}"
SLACK_ERROR_FETCHING_PYTHON_VERSION = "Error occurred while fetching the Phantom server's Python major version"
SLACK_ERROR_PY_2TO3 = "Error occurred while handling python 2to3 compatibility for the input string"
SLACK_ERROR_BASE_URL_NOT_FOUND = "Phantom Base URL not found in System Setting. Please specify this value in System Settings"
SLACK_ERROR_EMPTY_RESPONSE = "Status Code {code}. Empty response and no information in the header"
SLACK_UNABLE_TO_PARSE_ERROR_DETAILS = "Cannot parse error details"
SLACK_ERROR_UNABLE_TO_PARSE_JSON_RESPONSE = "Unable to parse response as JSON. {error}"
SLACK_ERROR_BOT_TOKEN_INVALID = "The configured bot token is invalid"
SLACK_ERROR_NOT_IN_CHANNEL = "The configured bot is not in the specified channel. Invite the bot to that channel to send messages there."
SLACK_ERROR_UNABLE_TO_DECODE_JSON_RESPONSE = "Unable to decode the response as JSON"
SLACK_ERROR_REST_CALL_FAILED = "REST call failed"
SLACK_ERROR_TEST_CONNECTIVITY_FAILED = "Test Connectivity Failed"
SLACK_SUCCESSFULLY_TEST_CONNECTIVITY_PASSED = "Test Connectivity Passed"
SLACK_ERROR_USER_TOKEN_NOT_PROVIDED = (
    "'OAuth Access Token' is required for this action. Navigate to the asset's configuration and add a token now and try again."
)
SLACK_ERROR_CREATING_CHANNEL = "Error creating channel"
SLACK_SUCCESSFULLY_CHANNEL_CREATED = "Channel created successfully"
SLACK_ERROR_DATA_NOT_FOUND_IN_OUTPUT = "{key} data not found in json output"
SLACK_ERROR_NOT_A_USER_ID = "The user parameter must be a user ID"
SLACK_ERROR_NO_USERID_OR_EMAIL = "No User ID or Email was provided. Please provide a User ID or Email address for the target user."
SLACK_SUCCESSFULLY_USER_DATA_RETRIEVED = "User data successfully retrieved"
SLACK_ERROR_INVALID_USER = "Please provide a valid value in 'users' action parameter"
SLACK_ERROR_INVITING_CHANNEL = "Error inviting to channel"
SLACK_ERROR_ADDING_REACTION = "Error adding reaction"
SLACK_ERROR_ASKING_QUESTION = "Error asking question"
SLACK_ERROR_SENDING_MESSAGE = "Error sending message"
SLACK_ERROR_UPLOADING_FILE = "Error uploading file"
SLACK_ERROR_GETTING_UPLOAD_URL = "Error getting upload URL from Slack"
SLACK_ERROR_UPLOADING_TO_URL = "Error uploading file to provided URL"
SLACK_ERROR_COMPLETING_UPLOAD = "Error completing file upload"
SLACK_ERROR_FETCHING_USER = "Error fetching user"
SLACK_SUCCESSFULLY_INVITE_SENT = "Invite sent to user(s)"
SLACK_ERROR_MESSAGE_TOO_LONG = "Message too long. Please limit messages to {limit} characters."
SLACK_ERROR_QUESTION_TOO_LONG = "Question too long. Please limit questions to {limit} characters."
SLACK_ERROR_CONFIRMATION_TOO_LONG = "Confirmation too long. Please limit questions to {limit} characters."
SLACK_SUCCESSFULLY_MESSAGE_SENT = "Message sent successfully"
SLACK_SUCCESSFULLY_REACTION_ADDED = "Reaction added successfully"
SLACK_SUCCESSFULLY_ASKED_QUESTION = "Asked question in channel successfully"
SLACK_ERROR_FILE_OR_CONTENT_NOT_PROVIDED = "Please provide either a 'file' or 'content' to upload"
SLACK_SUCCESSFULLY_FILE_UPLOAD = "File uploaded successfully"
SLACK_SUCCESSFULLY_SLACKBOT_STOPPED = "SlackBot has been stopped."
SLACK_ERROR_SLACKBOT_NOT_RUNNING = "SlackBot isn't running, not going to stop it."
SLACK_ERROR_COUDNT_STOP_SLACKBOT = "Something went wrong, wasn't able to stop the BOT. Please rerun the stop bot action"
SLACK_FAILED_TO_DISABLE_INGESTION = "{message} Failed to disable ingestion, please check that ingest settings are correct."
SLACK_INGESTION_NOT_ENABLED = "{message} Ingestion isn't enabled, not going to disable it."
SLACK_INGESTION_DISABLED = "{message} Ingestion has been disabled."
SLACK_ERROR_COULD_NOT_GET_BOT_ID = "Could not get bot ID from Slack"
SLACK_SUCCESSFULLY_SLACKBOT_RUNNING = "SlackBot already running"
SLACK_ERROR_AUTH_TOKEN_NOT_PROVIDED = "The 'ph_auth_token' asset configuration parameter is required to run the on_poll action"
SLACK_ERROR_SLACKBOT_RUNNING_WITH_SAME_BOT_TOKEN = (
    "Detected an instance of SlackBot running with the same bot token. Not going to start new instance."
)
SLACK_SUCCESSFULLY_SLACKBOT_STARTED = "SlackBot started"
SLACK_ERROR_UNABLE_TO_SEND_QUESTION_TO_CHANNEL = (
    "Questions can only be sent as direct messages to users using this action. To send message in channel, use the ask question channel action."
)
SLACK_ERROR_UNABLE_TO_SEND_QUESTION_TO_USER = (
    "Questions can only be sent in channel using this action. To send message to a user, use the ask question action."
)

SLACK_ERROR_UNABLE_TO_PARSE_RESPONSE = "Error occurred while parsing the response"
SLACK_ERROR_QUESTION_RESPONSE_NOT_AVAILABLE = "Response to question not available"
SLACK_ERROR_NO_RESPONSE_FROM_SERVER = "Got no response from the Slack server"
SLACK_ERROR_INVALID_CHANNEL_TYPE = "Please provide a valid value in the 'channel_type' action parameter"
SLACK_ERROR_LENGTH_LIMIT_EXCEEDED = (
    "Based on your asset_id length ({asset_length}), valid length for the 'confirmation' parameter is {valid_length}"
)

SLACK_ERROR_BLOCKS_OR_MESSAGE_REQD = "You must provide at least one of 'blocks' or 'message'"
SLACK_ERROR_COMMAND_NOT_PERMITTED = "This command is not permitted to be run on this asset"
SLACK_ERROR_RESPONDER_NOT_PERMITTED = "The user that responded to the question is not permitted"

SLACK_RESP_POLL_INTERVAL_KEY = "'How often to poll for a response (in seconds)' configuration"
SLACK_TIMEOUT_KEY = "'Question timeout (in minutes)' configuration"
SLACK_TOTAL_RESP_KEY = "'Total number of responses to keep' configuration"
SLACK_LIMIT_KEY = "'limit' action"

SLACK_DEFAULT_TIMEOUT = 30

SLACK_STATE_FILE_CORRUPT_ERROR = (
    "Error occurred while loading the state file due to it's unexpected format. Resetting "
    "the state file with the default format. Please test the connectivity."
)
SLACK_SOCKET_TOKEN_ERROR = "Invalid Socket Token please update the configuration file and rerun test connectivity"

SLACK_STATE_IS_ENCRYPTED = "is_encrypted"

# For encryption and decryption
SLACK_ENCRYPT_TOKEN = "Encrypting the {} token"
SLACK_DECRYPT_TOKEN = "Decrypting the {} token"
SLACK_ENCRYPTION_ERROR = "Error occurred while encrypting the state file"
SLACK_DECRYPTION_ERROR = "Error occurred while decrypting the state file"

SLACK_ERROR_MESSAGE_UNAVAILABLE = "Error message unavailable. Please check the asset configuration and|or action parameters"

SLACK_ERROR_NO_CHANNEL_ID = "No Channel ID was provided. Please provide a Channel ID for the target channel."
SLACK_ERROR_NOT_A_CHANNEL_ID = "The Channel ID parameter is not in a correct format"
SLACK_ERROR_FETCHING_CONVERSATION_HISTORY = "Error fetching conversation history"
SLACK_ERROR_THREAD_NOT_FOUND = "Failed to find thread with specified ts parameter"
SLACK_SUCCESSFULLY_CONVERSATION_HISTORY_DATA_RETRIEVED = "Conversation history data successfully retrieved"
