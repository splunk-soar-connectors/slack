# File: slack_connector.py
#
# Copyright (c) 2016-2024 Splunk Inc.
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
import os
import shlex
import subprocess
import sys
import time
import uuid
from os.path import exists
from pathlib import Path
from urllib.parse import unquote

import encryption_helper
import phantom.app as phantom
import phantom.rules as ph_rules
import requests
import sh
import simplejson as json
from bs4 import BeautifulSoup, UnicodeDammit
from django.http import HttpResponse
from phantom.base_connector import APPS_STATE_PATH

from slack_consts import *


class RetVal(tuple):
    def __new__(cls, val1, val2=None):
        return tuple.__new__(RetVal, (val1, val2))


def _load_app_state(asset_id, app_connector=None):
    """ This function is used to load the current state file.

    :param asset_id: asset_id
    :param app_connector: Object of app_connector class
    :return: state: Current state file as a dictionary
    """

    asset_id = str(asset_id)
    if not asset_id or not asset_id.isalnum():
        if app_connector:
            app_connector.debug_print('In _load_app_state: Invalid asset_id')
        return {}

    app_dir = os.path.dirname(os.path.abspath(__file__))
    state_file = '{0}/{1}_state.json'.format(app_dir, asset_id)
    real_state_file_path = os.path.realpath(state_file)
    if not os.path.dirname(real_state_file_path) == app_dir:
        if app_connector:
            app_connector.debug_print('In _load_app_state: Invalid asset_id')
        return {}

    state = {}
    try:
        with open(real_state_file_path, 'r') as state_file_obj:
            state_file_data = state_file_obj.read()
            state = json.loads(state_file_data)
    except Exception as e:
        if app_connector:
            app_connector.debug_print('In _load_app_state: Exception: {0}'.format(str(e)))

    if app_connector:
        app_connector.debug_print('Loaded state: ', state)

    return state


def _save_app_state(state, asset_id, app_connector=None):
    """ This function is used to save current state in file.

    :param state: Dictionary which contains data to write in state file
    :param asset_id: asset_id
    :param app_connector: Object of app_connector class
    :return: status: phantom.APP_SUCCESS
    """

    asset_id = str(asset_id)
    if not asset_id or not asset_id.isalnum():
        if app_connector:
            app_connector.debug_print('In _save_app_state: Invalid asset_id')
        return {}

    app_dir = os.path.split(__file__)[0]
    state_file = '{0}/{1}_state.json'.format(app_dir, asset_id)

    real_state_file_path = os.path.realpath(state_file)
    if os.path.dirname(real_state_file_path) != app_dir:
        if app_connector:
            app_connector.debug_print('In _save_app_state: Invalid asset_id')
        return {}

    if app_connector:
        app_connector.debug_print('Saving state: ', state)

    try:
        with open(real_state_file_path, 'w+') as state_file_obj:
            state_file_obj.write(json.dumps(state))
    except Exception as e:
        if app_connector:
            app_connector.debug_print('Unable to save state file: {0}'.format(str(e)))

    return phantom.APP_SUCCESS


def _is_safe_path(basedir, path, follow_symlinks=True):
    """
    This function checks the given file path against the actual app directory
    path to combat path traversal attacks
    """
    if follow_symlinks:
        matchpath = os.path.realpath(path)
    else:
        matchpath = os.path.abspath(path)
    return basedir == os.path.commonpath((basedir, matchpath))


def rest_log(msg):
    state_dir = "{0}/{1}".format(APPS_STATE_PATH, SLACK_APP_ID)
    path.unlink()
    path = Path(state_dir) / "resthandler.log"
    path.touch()  # default exists_ok=True
    with path.open('a') as highscore:
        highscore.write(msg + "\n")


def process_payload(payload, answer_path):

    if not exists(answer_path):
        final_payload = {
            "payloads": [payload],
            "replies_from": [payload.get('user').get('id')]
        }
        return final_payload
    else:
        old_payload = dict()
        try:
            with open(answer_path, "r") as read_old_file:
                old_payload = json.loads(read_old_file.read())
        except Exception as e:
            return HttpResponse(
                "Error while reading data from file: {}".format(e),
                content_type="text/plain",
                status=400
            )
        current_user_id = payload.get('user').get('id')
        if current_user_id not in old_payload.get('replies_from'):
            old_payload['payloads'].append(payload)
            old_payload['replies_from'].append(payload.get('user').get('id'))
        else:
            user_payloads = old_payload.get('payloads')
            for data in user_payloads:
                if data.get('user').get('id') == current_user_id:
                    data['actions'] = payload.get('actions')

        return old_payload


def handle_request(request, path):

    try:
        payload = request.POST.get('payload')
        payload = json.loads(payload)
        state_dir = "{0}/{1}".format(APPS_STATE_PATH, SLACK_APP_ID)

        if not payload:
            return HttpResponse(SLACK_ERROR_PAYLOAD_NOT_FOUND, content_type="text/plain", status=400)

        callback_id = payload.get('callback_id')
        # rest_log(f"Callback_id: {callback_id}")
        if not callback_id:
            return HttpResponse(SLACK_ERROR_CALLBACK_ID_NOT_FOUND, content_type="text/plain", status=400)

        try:
            callback_json = json.loads(UnicodeDammit(callback_id).unicode_markup)
        except Exception as e:
            # rest_log(f"Callback parse error")
            return HttpResponse(SLACK_ERROR_PARSE_JSON_FROM_CALLBACK_ID.format(error=e), content_type="text/plain", status=400)

        asset_id = callback_json.get('asset_id')
        # rest_log(f"Asset retrieved: {asset_id}")
        try:
            int(asset_id)
        except ValueError:
            return HttpResponse(SLACK_ERROR_STATE_FILE_NOT_FOUND, content_type="text/plain", status=400)

        state_filename = "{0}_state.json".format(asset_id)
        state_dir = "{0}/{1}".format(APPS_STATE_PATH, SLACK_APP_ID)
        state_path = "{0}/{1}".format(state_dir, state_filename)

        try:
            with open(state_path, 'r') as state_file_obj:  # nosemgrep
                state_file_data = state_file_obj.read()
                state = json.loads(state_file_data)
        except Exception as e:
            return HttpResponse(SLACK_ERROR_UNABLE_TO_READ_STATE_FILE.format(error=e), content_type="text/plain", status=400)

        my_token = state.get('token')
        if my_token:
            try:
                my_token = encryption_helper.decrypt(my_token, asset_id)
            except Exception:
                return RetVal(phantom.APP_ERROR, SLACK_DECRYPTION_ERROR)

        their_token = payload.get('token')
        # rest_log(f"My token: {my_token}, Their token: {their_token}")

        if not my_token or not their_token or my_token != their_token:
            return HttpResponse(SLACK_ERROR_AUTH_FAILED, content_type="text/plain", status=400)

        qid = callback_json.get('qid')
        # rest_log(f"Question ID: {qid}")

        if not qid:
            return HttpResponse(SLACK_ERROR_ANSWER_FILE_NOT_FOUND, content_type="text/plain", status=400)

        answer_filename = '{0}.json'.format(qid)
        answer_path = "{0}/{1}".format(state_dir, answer_filename)
        if not _is_safe_path(state_dir, answer_path):
            return HttpResponse(SLACK_ERROR_INVALID_FILE_PATH, content_type="text/plain", status=400)

        final_payload = process_payload(payload, answer_path)

        try:
            with open(answer_path, 'w') as answer_file:  # nosemgrep
                answer_file.write(json.dumps(final_payload))
        except Exception as e:
            return HttpResponse(SLACK_ERROR_WHILE_WRITING_ANSWER_FILE.format(error=e), content_type="text/plain", status=400)

        confirmation = callback_json.get('confirmation', "Received response")
        return HttpResponse(f"Response: {confirmation}", content_type="text/plain", status=200)

    except Exception as e:
        return HttpResponse(SLACK_ERROR_PROCESS_RESPONSE.format(error=e), content_type="text/plain", status=500)


# Define the App Class
class SlackConnector(phantom.BaseConnector):

    def __init__(self):

        # Call the BaseConnectors init first
        super(SlackConnector, self).__init__()

        self._base_url = None
        self._state = {}
        self._slack_client = None
        self._interval = None
        self._timeout = None
        self._socket_token = None
        self._verification_token = None
        self._permit_act = None
        self._permit_playbook = None
        self._permit_container = None
        self._permit_list = None
        self._permitted_users = None

    def encrypt_state(self, encrypt_var, token_name):
        """ Handle encryption of token.
        :param encrypt_var: Variable needs to be encrypted
        :return: encrypted variable
        """
        self.debug_print(SLACK_ENCRYPT_TOKEN.format(token_name))   # nosemgrep
        return encryption_helper.encrypt(encrypt_var, self.get_asset_id())

    def decrypt_state(self, decrypt_var, token_name):
        """ Handle decryption of token.
        :param decrypt_var: Variable needs to be decrypted
        :return: decrypted variable
        """
        self.debug_print(SLACK_DECRYPT_TOKEN.format(token_name))    # nosemgrep
        return encryption_helper.decrypt(decrypt_var, self.get_asset_id())

    def initialize(self):

        config = self.get_config()
        self._state = self.load_state()

        if not isinstance(self._state, dict):
            self.debug_print("Resetting the state file with the default format")
            self._state = {"app_version": self.get_app_json().get("app_version")}

        self._bot_token = config.get(SLACK_JSON_BOT_TOKEN)
        self._socket_token = config.get(SLACK_JSON_SOCKET_TOKEN)
        self._ph_auth_token = config.get(SLACK_JSON_PH_AUTH_TOKEN)
        self._permit_act = config.get(SLACK_JSON_PERMIT_BOT_ACT, False)
        self._permit_playbook = config.get(SLACK_JSON_PERMIT_BOT_PLAYBOOK, False)
        self._permit_container = config.get(SLACK_JSON_PERMIT_BOT_CONTAINER, False)
        self._permit_list = config.get(SLACK_JSON_PERMIT_BOT_LIST, False)
        self._permitted_users = config.get(SLACK_JSON_PERMITTED_USERS, False)
        self._base_url = SLACK_BASE_URL

        self._verification_token = self._state.get('token')
        self._interval = self._validate_integers(self, config.get("response_poll_interval", 30), SLACK_RESP_POLL_INTERVAL_KEY)
        if self._interval is None:
            return self.get_status()

        self._timeout = self._validate_integers(self, config.get("timeout", 30), SLACK_TIMEOUT_KEY)
        if self._timeout is None:
            return self.get_status()

        ret_val, ph_base_url = self._get_phantom_base_url_slack(self)
        if phantom.is_fail(ret_val):
            return ret_val
        ph_base_url += '/' if not ph_base_url.endswith('/') else ''

        # Storing Bot file required data in state file
        self._state['ph_base_url'] = ph_base_url
        self._state[SLACK_JSON_PH_AUTH_TOKEN] = self._ph_auth_token
        self._state[SLACK_JSON_BOT_TOKEN] = self._bot_token
        self._state[SLACK_JSON_SOCKET_TOKEN] = self._socket_token
        self._state[SLACK_JSON_PERMIT_BOT_ACT] = self._permit_act
        self._state[SLACK_JSON_PERMIT_BOT_PLAYBOOK] = self._permit_playbook
        self._state[SLACK_JSON_PERMIT_BOT_CONTAINER] = self._permit_container
        self._state[SLACK_JSON_PERMIT_BOT_LIST] = self._permit_list
        self._state[SLACK_JSON_PERMITTED_USERS] = self._permitted_users

        # Decrypting data from state file
        if self._state.get(SLACK_STATE_IS_ENCRYPTED):
            try:
                if self._verification_token:
                    self._verification_token = self.decrypt_state(self._verification_token, "verification")
            except Exception as e:
                self.debug_print("{}: {}".format(SLACK_DECRYPTION_ERROR, self._get_error_message_from_exception(e)))
                return self.set_status(phantom.APP_ERROR, SLACK_DECRYPTION_ERROR)

        return phantom.APP_SUCCESS

    def finalize(self):

        # Encrypting tokens
        try:
            if self._verification_token:
                self._state['token'] = self.encrypt_state(self._verification_token, "verification")

            if self._bot_token:
                self._state[SLACK_JSON_BOT_TOKEN] = self.encrypt_state(self._bot_token, "bot")

            if self._socket_token:
                self._state[SLACK_JSON_SOCKET_TOKEN] = self.encrypt_state(self._socket_token, "socket")

            if self._ph_auth_token:
                self._state[SLACK_JSON_PH_AUTH_TOKEN] = self.encrypt_state(self._ph_auth_token, "ph_auth")

        except Exception as e:
            self.debug_print("{}: {}".format(SLACK_ENCRYPTION_ERROR, self._get_error_message_from_exception(e)))
            return self.set_status(phantom.APP_ERROR, SLACK_ENCRYPTION_ERROR)

        self._state[SLACK_STATE_IS_ENCRYPTED] = True
        self.save_state(self._state)
        _save_app_state(self._state, self.get_asset_id(), self)

        return phantom.APP_SUCCESS

    def _get_phantom_base_url_slack(self, action_result):
        base_url = self.get_phantom_base_url()
        rest_url = SLACK_PHANTOM_SYS_INFO_URL.format(url=base_url if base_url.endswith('/') else base_url + '/')

        ret_val, resp_json = self._make_rest_call(action_result, rest_url, False)

        if phantom.is_fail(ret_val):
            return RetVal(ret_val)

        phantom_base_url = resp_json.get('base_url')

        if not phantom_base_url:
            return RetVal(action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_BASE_URL_NOT_FOUND))

        return RetVal(phantom.APP_SUCCESS, phantom_base_url)

    def _process_empty_reponse(self, response, action_result):

        if response.status_code == 200:
            return RetVal(phantom.APP_SUCCESS, {})

        return RetVal(action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_EMPTY_RESPONSE.format(code=response.status_code)), None)

    def _process_html_response(self, response, action_result):

        # An html response, is bound to be an error
        status_code = response.status_code

        try:
            soup = BeautifulSoup(response.text, "html.parser")

            # Remove the script, style, footer and navigation part from the HTML message
            for element in soup(["script", "style", "footer", "nav"]):
                element.extract()

            error_text = soup.text
            split_lines = error_text.split('\n')
            split_lines = [x.strip() for x in split_lines if x.strip()]
            error_text = '\n'.join(split_lines)
        except Exception:
            error_text = SLACK_UNABLE_TO_PARSE_ERROR_DETAILS

        message = "Status Code: {0}. Data from server:\n{1}\n".format(status_code, error_text)

        message = message.replace('{', '{{').replace('}', '}}')

        return RetVal(action_result.set_status(phantom.APP_ERROR, message), None)

    def _process_json_response(self, r, action_result):

        # Try a json parse
        try:
            resp_json = r.json()
        except Exception as e:
            return RetVal(action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_UNABLE_TO_PARSE_JSON_RESPONSE.format(
                error=self._get_error_message_from_exception(e))), None)

        # The 'ok' parameter in a response from slack says if the call passed or failed
        if resp_json.get('ok', '') is not False:
            return RetVal(phantom.APP_SUCCESS, resp_json)

        action_result.add_data(resp_json)

        error = resp_json.get('error', '')
        if error == 'invalid_auth':
            error = SLACK_ERROR_BOT_TOKEN_INVALID
        elif error == 'not_in_channel':
            error = SLACK_ERROR_NOT_IN_CHANNEL
        elif not error:
            error = SLACK_ERROR_FROM_SERVER

        return RetVal(action_result.set_status(phantom.APP_ERROR, error), None)

    def _process_response(self, r, action_result):

        # store the r_text in debug data, it will get dumped in the logs if an error occurs
        if hasattr(action_result, 'add_debug_data'):
            if r is not None:
                action_result.add_debug_data({'r_status_code': r.status_code})
                action_result.add_debug_data({'r_text': r.text})
                action_result.add_debug_data({'r_headers': r.headers})
            else:
                action_result.add_debug_data({'r_text': 'r is None'})
                return RetVal(action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_NO_RESPONSE_FROM_SERVER), None)

        # There are just too many differences in the response to handle all of them in the same function
        if 'json' in r.headers.get('Content-Type', ''):
            return self._process_json_response(r, action_result)

        if 'html' in r.headers.get('Content-Type', ''):
            return self._process_html_response(r, action_result)

        # it's not an html or json, handle if it is a successfull empty reponse
        if not r.text:
            return self._process_empty_reponse(r, action_result)

        # everything else is actually an error at this point
        message = "Can't process response from server. Status Code: {0} Data from server: {1}".format(
            r.status_code, r.text.replace('{', '{{').replace('}', '}}'))

        return RetVal(action_result.set_status(phantom.APP_ERROR, message), None)

    def _get_error_message_from_exception(self, e):
        """ This method is used to get appropriate error message from the exception.
        :param e: Exception object
        :return: error message
        """
        error_code = None
        error_message = SLACK_ERROR_MESSAGE_UNAVAILABLE

        self.error_print("Error occurred.", e)

        try:
            if hasattr(e, "args"):
                if len(e.args) > 1:
                    error_code = e.args[0]
                    error_message = e.args[1]
                elif len(e.args) == 1:
                    error_message = e.args[0]
        except Exception as e:
            self.error_print("Error occurred while fetching exception information. Details: {}".format(str(e)))

        if not error_code:
            error_text = "Error Message: {}".format(error_message)
        else:
            error_text = "Error Code: {}. Error Message: {}".format(error_code, error_message)

        return error_text

    def _make_rest_call(self, action_result, rest_url, verify, method=requests.get, headers={}, body={}):

        try:
            r = method(rest_url, verify=verify, headers=headers, data=json.dumps(body))
        except Exception as e:
            return RetVal(action_result.set_status(phantom.APP_ERROR, "{0}. {1}".format(
                SLACK_ERROR_REST_CALL_FAILED, self._get_error_message_from_exception(e))), None)

        try:
            resp_json = r.json()
        except Exception:
            return RetVal(action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_UNABLE_TO_DECODE_JSON_RESPONSE), None)

        if 'failed' in resp_json:
            return RetVal(action_result.set_status(phantom.APP_ERROR, "{0}. Message: {1}".format(
                SLACK_ERROR_REST_CALL_FAILED, resp_json.get('message', 'NA'))), None)

        if 200 <= r.status_code <= 399:
            return RetVal(phantom.APP_SUCCESS, resp_json)

        details = 'NA'

        if resp_json:
            details = json.dumps(resp_json).replace('{', '{{').replace('}', '}}')

        return RetVal(action_result.set_status(phantom.APP_ERROR, "Error from server: Status code: {0} Details: {1}".format(
            r.status_code, details)), None)

    def _make_slack_rest_call(self, action_result, endpoint, body, headers={}, files={}):

        body.update({'token': self._bot_token})
        # send api call to slack
        try:
            response = requests.post("{}{}".format(self._base_url, endpoint),
                                     data=body,
                                     headers=headers,
                                     files=files,
                                     timeout=SLACK_DEFAULT_TIMEOUT)
        except Exception as e:
            return RetVal(action_result.set_status(phantom.APP_ERROR, "{}. {}".format(
                SLACK_ERROR_SERVER_CONNECTION, self._get_error_message_from_exception(e))), None)

        return self._process_response(response, action_result)

    def _validate_integers(self, action_result, parameter, key, allow_zero=False):
        """Validate the provided input parameter value is a non-zero positive integer and returns the integer value of the parameter itself.

        Parameters:
            :param action_result: object of ActionResult class
            :param parameter: input parameter
            :param key: input parameter message key
            :allow_zero: whether zero should be considered as valid value or not
            :return: integer value of the parameter or None in case of failure

        Returns:
            :return: integer value of the parameter
        """
        try:
            if not float(parameter).is_integer():
                action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_INVALID_INT.format(key=key))
                return None

            parameter = int(parameter)
        except Exception:
            action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_INVALID_INT.format(key=key))
            return None

        if parameter < 0:
            action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_NEGATIVE_INT.format(key=key))
            return None
        if not allow_zero and parameter == 0:
            action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_NEGATIVE_AND_ZERO_INT.format(key=key))
            return None

        return parameter

    def _test_connectivity(self, param):

        action_result = self.add_action_result(phantom.ActionResult(dict(param)))

        ret_val, resp_json = self._make_slack_rest_call(action_result, SLACK_AUTH_TEST, {})

        if not ret_val:
            self.save_progress(SLACK_ERROR_TEST_CONNECTIVITY_FAILED)
            return ret_val

        action_result.add_data(resp_json)

        self.save_progress("Auth check to Slack passed. Configuring app for team, {}".format(resp_json.get('team', 'Unknown Team')))

        bot_username = resp_json.get('user')
        bot_user_id = resp_json.get('user_id')

        self.save_progress("Got username, {0}, and user ID, {1}, for the bot".format(bot_username, bot_user_id))

        self._state['bot_name'] = bot_username
        self._state['bot_id'] = bot_user_id

        self.save_progress(SLACK_SUCCESSFULLY_TEST_CONNECTIVITY_PASSED)

        return action_result.set_status(phantom.APP_SUCCESS)

    def _create_channel(self, param):

        action_result = self.add_action_result(phantom.ActionResult(dict(param)))

        user_token = self.get_config().get('user_token')
        self.debug_print("Inside create channel action")

        if not user_token:
            return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_USER_TOKEN_NOT_PROVIDED)

        headers = {
            "Authorization": "Bearer {}".format(user_token),
            'Content-Type': 'application/json'
        }

        params = {
            'name': param['name'],
            'token': user_token,
            'validate': True
        }
        endpoint = "{}{}".format(SLACK_BASE_URL, SLACK_CHANNEL_CREATE_ENDPOINT)

        # private channel
        channel_type = param.get("channel_type", "public")
        if channel_type not in ["public", "private"]:
            return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_INVALID_CHANNEL_TYPE)
        if channel_type == "private":
            params.update({"is_private": True})

        self.debug_print("Making rest call to create channel")
        ret_val, resp_json = self._make_rest_call(
            action_result,
            endpoint,
            False,
            method=requests.post,
            headers=headers,
            body=params
        )

        if not ret_val:
            return ret_val

        if not resp_json.get('ok', True):
            error = resp_json.get('error', 'N/A')
            error_details = resp_json.get('detail', '')
            if error_details:
                error_message = "{}: {}\r\nDetails: {}".format(SLACK_ERROR_CREATING_CHANNEL, error, error_details)
            else:
                error_message = "{}: {}".format(SLACK_ERROR_CREATING_CHANNEL, error)
            return action_result.set_status(phantom.APP_ERROR, error_message)

        action_result.add_data(resp_json)

        return action_result.set_status(phantom.APP_SUCCESS, SLACK_SUCCESSFULLY_CHANNEL_CREATED)

    def _list_channels(self, param):

        self.debug_print("param", param)
        self.save_progress("In action handler for: {0}".format(self.get_action_identifier()))
        action_result = self.add_action_result(phantom.ActionResult(dict(param)))

        limit = self._validate_integers(action_result, param.get("limit", SLACK_DEFAULT_LIMIT), SLACK_LIMIT_KEY)
        if limit is None:
            return action_result.get_status()

        ret_val, resp_json = self._paginator(action_result, SLACK_LIST_CHANNEL, "channels", limit=limit)

        if not ret_val:
            return action_result.get_status()

        action_result.add_data(resp_json)

        channels = resp_json.get('channels', [])

        for chan in channels:
            name = chan.get('name', 'unknownchannel')
            chan['name'] = '#{}'.format(name)

        action_result.set_summary({"num_public_channels": len(channels)})

        return action_result.set_status(phantom.APP_SUCCESS)

    def _paginator(self, action_result, endpoint, key, body=None, limit=None):
        """Fetch results from multiple API calls using pagination for the given endpoint

        Args:
            action_result : Object of ActionResult class
            endpoint : REST endpoint that needs to be attended to the address
            limit : User specified maximum number of events to be returned

        Returns:
            results : The aggregated response
        """
        if body is None:
            body = {}
        body.update({"limit": SLACK_DEFAULT_LIMIT})
        results = {}

        while True:
            ret_val, resp_json = self._make_slack_rest_call(action_result, endpoint, body)

            if not ret_val:
                return phantom.APP_ERROR, None

            key_result_value = resp_json.get(key, [])

            if not results:
                if not key_result_value:
                    return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_DATA_NOT_FOUND_IN_OUTPUT.format(
                        key=("users" if key == "members" else key))), None
                results = resp_json
            else:
                results[key].extend(key_result_value)

            result_length = len(results[key])

            if limit and result_length >= limit:
                results[key] = results[key][:limit]
                return phantom.APP_SUCCESS, results

            # set the next cursor
            next_cursor = resp_json.get("response_metadata", {}).get("next_cursor", "")

            if not next_cursor:
                break
            else:
                body.update({"cursor": next_cursor})

        return phantom.APP_SUCCESS, results

    def _list_users(self, param):

        self.debug_print("param", param)
        self.save_progress("In action handler for: {0}".format(self.get_action_identifier()))
        action_result = self.add_action_result(phantom.ActionResult(dict(param)))

        limit = self._validate_integers(action_result, param.get("limit", SLACK_DEFAULT_LIMIT), SLACK_LIMIT_KEY)
        if limit is None:
            return action_result.get_status()

        ret_val, resp_json = self._paginator(action_result, SLACK_USER_LIST, "members", limit=limit)

        if not ret_val:
            return action_result.get_status()

        action_result.add_data(resp_json)

        users = resp_json.get('members', [])

        for user in users:
            name = user.get('name', 'unknownuser')
            user['name'] = '@{}'.format(name)

        action_result.set_summary({"num_users": len(users)})

        return action_result.set_status(phantom.APP_SUCCESS)

    def _get_user(self, param):

        self.debug_print("param", param)
        self.save_progress("In action handler for: {0}".format(self.get_action_identifier()))
        action_result = self.add_action_result(phantom.ActionResult(dict(param)))

        user_id = param.get('user_id')
        email_address = param.get('email_address')
        if not user_id and not email_address:
            return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_NO_USERID_OR_EMAIL)
        if user_id:
            if not user_id.startswith('U') and not user_id.startswith('W'):
                return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_NOT_A_USER_ID)

            ret_val, resp_json = self._make_slack_rest_call(action_result, SLACK_USER_INFO, {'user': user_id})

        elif email_address:
            bot_token = self._bot_token

            if not bot_token:
                return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_USER_TOKEN_NOT_PROVIDED)
            endpoint = "{}{}?email={}".format(SLACK_BASE_URL, SLACK_USER_LOOKUP_BY_EMAIL, email_address)

            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer {}'.format(bot_token)
            }

            self.debug_print("Making rest call to lookup user")

            ret_val, resp_json = self._make_rest_call(
                action_result,
                endpoint,
                False,
                method=requests.get,
                headers=headers
            )

        if not ret_val:
            message = action_result.get_message()
            if message:
                error_message = "{}: {}".format(SLACK_ERROR_FETCHING_USER, message)
            else:
                error_message = SLACK_ERROR_FETCHING_USER
            return action_result.set_status(phantom.APP_ERROR, error_message)

        action_result.add_data(resp_json)

        user = resp_json.get('user')

        if not user:
            return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_DATA_NOT_FOUND_IN_OUTPUT.format(key="User"))

        name = user.get('name', '')
        user['name'] = '@{}'.format(name)

        return action_result.set_status(phantom.APP_SUCCESS, SLACK_SUCCESSFULLY_USER_DATA_RETRIEVED)

    def _invite_users(self, param):

        action_result = self.add_action_result(phantom.ActionResult(dict(param)))

        user_token = self.get_config().get('user_token')
        self.debug_print("Inside invite user action")

        if not user_token:
            return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_USER_TOKEN_NOT_PROVIDED)

        headers = {
            "Authorization": "Bearer {}".format(user_token),
            'Content-Type': 'application/json'
        }

        users = [x.strip() for x in param['users'].split(',')]
        users = list(filter(None, users))
        if not users:
            return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_INVALID_USER)

        params = {
            'users': users,
            'channel': param['channel_id'],
            'token': user_token
        }

        endpoint = "{}{}".format(SLACK_BASE_URL, SLACK_INVITE_TO_CHANNEL)
        self.debug_print("Making rest call to invite user")
        ret_val, resp_json = self._make_rest_call(
            action_result,
            endpoint,
            False,
            method=requests.post,
            headers=headers,
            body=params
        )

        if not ret_val:
            return ret_val

        if not resp_json.get('ok', True):
            error = resp_json.get('error', 'N/A')
            error_details = resp_json.get('detail', '')
            if error_details:
                error_message = "{}: {}\r\nDetails: {}".format(SLACK_ERROR_INVITING_CHANNEL, error, error_details)
            else:
                error_message = "{}: {}".format(SLACK_ERROR_INVITING_CHANNEL, error)
            return action_result.set_status(phantom.APP_ERROR, error_message)

        action_result.add_data(resp_json)

        return action_result.set_status(phantom.APP_SUCCESS, SLACK_SUCCESSFULLY_INVITE_SENT)

    def _send_message(self, param):

        self.save_progress("In action handler for: {0}".format(self.get_action_identifier()))
        action_result = self.add_action_result(phantom.ActionResult(dict(param)))

        params = {'channel': param['destination']}

        if 'message' not in param and 'blocks' not in param:
            return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_BLOCKS_OR_MESSAGE_REQD)

        if 'message' in param:
            message = param['message']

            if '\\' in message:
                message = bytes(message, "utf-8").decode("unicode_escape")

            if len(message) > SLACK_MESSAGE_LIMIT:
                return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_MESSAGE_TOO_LONG.format(limit=SLACK_MESSAGE_LIMIT))

            params['text'] = message

        if 'blocks' in param:
            params['blocks'] = param['blocks']

        params['link_names'] = param.get('link_names', False)

        if 'parent_message_ts' in param:
            # Support for replying in thread
            params['thread_ts'] = param.get('parent_message_ts')

            if 'reply_broadcast' in param:
                params['reply_broadcast'] = param.get('reply_broadcast', False)

        self.debug_print("Making rest call to send message")
        ret_val, resp_json = self._make_slack_rest_call(action_result, SLACK_SEND_MESSAGE, params)

        if not ret_val:
            message = action_result.get_message()
            if message:
                error_message = "{}: {}".format(SLACK_ERROR_SENDING_MESSAGE, message)
            else:
                error_message = SLACK_ERROR_SENDING_MESSAGE
            return action_result.set_status(phantom.APP_ERROR, error_message)

        action_result.add_data(resp_json)

        return action_result.set_status(phantom.APP_SUCCESS, SLACK_SUCCESSFULLY_MESSAGE_SENT)

    def _add_reaction(self, param):

        self.save_progress("In action handler for: {0}".format(self.get_action_identifier()))
        action_result = self.add_action_result(phantom.ActionResult(dict(param)))

        emoji = param['emoji']

        params = {'channel': param['destination'], 'name': emoji, 'timestamp': param['message_ts']}

        self.debug_print("Making rest call to add reaction")
        ret_val, resp_json = self._make_slack_rest_call(action_result, SLACK_ADD_REACTION, params)

        if not ret_val:
            message = action_result.get_message()
            if message:
                error_message = "{}: {}".format(SLACK_ERROR_ADDING_REACTION, message)
            else:
                error_message = SLACK_ERROR_ADDING_REACTION
            return action_result.set_status(phantom.APP_ERROR, error_message)

        action_result.add_data(resp_json)

        return action_result.set_status(phantom.APP_SUCCESS, SLACK_SUCCESSFULLY_REACTION_ADDED)

    def _upload_file(self, param):

        self.save_progress("In action handler for: {0}".format(self.get_action_identifier()))
        action_result = self.add_action_result(phantom.ActionResult(dict(param)))

        caption = param.get('caption', '')

        if caption:
            caption += ' -- '

        caption += 'Uploaded from Phantom'

        kwargs = {}
        params = {'channels': param['destination'], 'initial_comment': caption}

        if 'filetype' in param:
            params['filetype'] = param.get('filetype')

        if 'filename' in param:
            params['filename'] = param.get('filename')

        if 'parent_message_ts' in param:
            # Support for replying in thread
            params['thread_ts'] = param.get('parent_message_ts')

        if 'file' in param:
            vault_id = param.get('file')

            # check the vault for a file with the supplied ID
            try:
                success, message, vault_meta_info = ph_rules.vault_info(vault_id=vault_id)
                vault_meta_info = list(vault_meta_info)
                if not success or not vault_meta_info:
                    error_msg = " Error Details: {}".format(unquote(message)) if message else ''
                    return action_result.set_status(phantom.APP_ERROR, "{}.{}".format(
                        SLACK_ERROR_UNABLE_TO_FETCH_FILE.format(key="info"), error_msg))
            except Exception as e:
                err = self._get_error_message_from_exception(e)
                return action_result.set_status(phantom.APP_ERROR, "{}. {}".format(SLACK_ERROR_UNABLE_TO_FETCH_FILE.format(key="info"), err))

            # phantom vault file path
            file_path = vault_meta_info[0].get('path')
            if not file_path:
                return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_UNABLE_TO_FETCH_FILE.format(key="path"))

            # phantom vault file name
            file_name = vault_meta_info[0].get('name')
            if not file_name:
                return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_UNABLE_TO_FETCH_FILE.format(key="name"))

            upfile = open(file_path, 'rb')
            params['filename'] = file_name
            kwargs['files'] = {'file': upfile}
        elif 'content' in param:
            params['content'] = param.get('content')
        else:
            return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_FILE_OR_CONTENT_NOT_PROVIDED)

        self.debug_print("Making rest call to upload file")
        ret_val, resp_json = self._make_slack_rest_call(action_result, SLACK_UPLOAD_FILE, params, **kwargs)
        if 'files' in kwargs:
            upfile.close()

        if not ret_val:
            message = action_result.get_message()
            if message:
                error_message = "{}: {}".format(SLACK_ERROR_UPLOADING_FILE, message)
            else:
                error_message = SLACK_ERROR_UPLOADING_FILE
            return action_result.set_status(phantom.APP_ERROR, error_message)

        file_json = resp_json.get('file', {})

        thumbnail_dict = {}
        pop_list = []

        for key, value in list(file_json.items()):

            if key.startswith('thumb'):

                pop_list.append(key)

                name_arr = key.split('_')

                thumb_name = "{0}_{1}".format(name_arr[0], name_arr[1])

                if thumb_name not in thumbnail_dict:
                    thumbnail_dict[thumb_name] = {}

                thumb_dict = thumbnail_dict[thumb_name]

                if len(name_arr) == 2:
                    thumb_dict['img_url'] = value

                elif name_arr[2] == 'w':
                    thumb_dict['width'] = value

                elif name_arr[2] == 'h':
                    thumb_dict['height'] = value

            elif key == 'initial_comment':
                resp_json['caption'] = value
                pop_list.append(key)

            elif key in ['channels', 'ims', 'groups']:

                if 'destinations' not in resp_json:
                    resp_json['destinations'] = []

                resp_json['destinations'] += value

                pop_list.append(key)

            elif key == 'username':
                pop_list.append(key)

            elif key == 'user':
                resp_json['sender'] = value
                pop_list.append(key)

        for poppee in pop_list:
            file_json.pop(poppee)

        resp_json['thumbnails'] = thumbnail_dict

        action_result.add_data(resp_json)

        return action_result.set_status(phantom.APP_SUCCESS, SLACK_SUCCESSFULLY_FILE_UPLOAD)

    def _stop_bot(self, param):

        self.debug_print("Inside stop bot action")
        action_result = self.add_action_result(phantom.ActionResult(dict(param)))

        pid = self._state.get('pid')
        self.debug_print("PID of Bot : {}".format(pid))
        if pid:
            self._state.pop('pid')
            try:
                if 'slack_bot.py' in sh.ps('ww', pid):  # pylint: disable=E1101
                    try:
                        sh.kill(pid)  # pylint: disable=E1101
                        return action_result.set_status(phantom.APP_SUCCESS, SLACK_SUCCESSFULLY_SLACKBOT_STOPPED)
                    except Exception:
                        return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_COUDNT_STOP_SLACKBOT)
            except Exception:
                return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_SLACKBOT_NOT_RUNNING)
        else:
            try:
                ps_out = sh.grep(sh.ps('ww', 'aux'), 'slack_bot.py')
                pid = shlex.split(str(ps_out))[1]
                try:
                    sh.kill(pid)  # pylint: disable=E1101
                    return action_result.set_status(phantom.APP_SUCCESS, SLACK_SUCCESSFULLY_SLACKBOT_STOPPED)
                except Exception:
                    return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_COUDNT_STOP_SLACKBOT)
            except Exception:
                return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_SLACKBOT_NOT_RUNNING)

    def _on_poll(self, param):

        action_result = self.add_action_result(phantom.ActionResult(dict(param)))
        ret_val, resp_json = self._make_slack_rest_call(action_result, SLACK_AUTH_TEST, {})
        if not ret_val:
            return ret_val

        bot_id = resp_json.get('user_id')
        bot_username = resp_json.get('user')

        if not bot_id:
            return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_COULD_NOT_GET_BOT_ID)

        # we need to save the bot username and bot id to state file in case test connectivity has not been run
        # certain bot actions will fail if these values do not exist in the state file loaded at bot start
        self._state['bot_name'] = bot_username
        self._state['bot_id'] = bot_id
        self.save_state(self._state)

        # we are using container count to decide if we will restart the bot or not
        container_count = int(param.get('container_count'))

        pid = self._state.get('pid')
        if pid:
            try:
                # use manual on poll action to 'reload' state file into slack_bot.py
                if self.is_poll_now():
                    self.save_progress("Container Count: {}".format(container_count))
                    if container_count == 1234:
                        sh.kill(pid)
                        self.save_progress("Container count set to 1234, stopping slack_bot.py at pid {}".format(pid))
                    elif container_count == int(pid):
                        sh.kill(pid)
                        self.save_progress("pid passed in as container count, stopping bot")
                        return action_result.set_status(phantom.APP_SUCCESS, "bot has been stopped")
                    else:
                        self.save_progress("HINT: Set Maximum Containers to 1234 to restart slackbot, or set to PID to stop slackbot")

                if 'slack_bot.py' in sh.ps('ww', pid):  # pylint: disable=E1101
                    self.save_progress("Detected SlackBot running with pid {0}".format(pid))
                    return action_result.set_status(phantom.APP_SUCCESS, SLACK_SUCCESSFULLY_SLACKBOT_RUNNING)
            except Exception:
                pass

        asset_id = self.get_asset_id()
        app_version = self.get_app_json().get('app_version', '')

        try:
            ps_out = sh.grep(sh.ps('ww', 'aux'), 'slack_bot.py')  # pylint: disable=E1101
            old_pid = shlex.split(str(ps_out))[1]
            if app_version not in ps_out:
                self.save_progress("Found an old version of slackbot running with pid {}, going to kill it".format(old_pid))
                sh.kill(old_pid)  # pylint: disable=E1101
            elif asset_id in ps_out:  # pylint: disable=E1101
                self._state['pid'] = int(old_pid)
                return action_result.set_status(phantom.APP_SUCCESS, SLACK_ERROR_SLACKBOT_RUNNING_WITH_SAME_BOT_TOKEN)
        except Exception:
            pass

        slack_bot_filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'slack_bot.py')

        # check if the socket token is valid
        headers = {
            'Authorization': 'Bearer {}'.format(self._socket_token)
        }
        url = "{}apps.connections.open".format(SLACK_BASE_URL)
        resp = requests.post(url, headers=headers, timeout=30)
        resp = resp.json()

        if not resp.get('ok'):
            self.save_progress("Failed to start Slack Bot")
            return action_result.set_status(phantom.APP_ERROR, SLACK_SOCKET_TOKEN_ERROR)

        self.save_progress("Starting SlackBot")
        proc = subprocess.Popen(['phenv', 'python3', slack_bot_filename, asset_id, app_version])
        self._state['pid'] = proc.pid
        self.save_progress("Started SlackBot with pid: {0}".format(proc.pid))

        return action_result.set_status(phantom.APP_SUCCESS, SLACK_SUCCESSFULLY_SLACKBOT_STARTED)

    def _handle_ask_question(self, action_result, param, user):

        config = self.get_config()
        local_data_state_dir = self.get_state_dir().rstrip('/')
        self._state['local_data_path'] = local_data_state_dir
        # Need to make sure the configured verification token is in the app state so the request_handler can use it to verify POST requests
        if 'token' not in self._state:
            self._verification_token = config[SLACK_JSON_VERIFICATION_TOKEN]
        elif self._state['token'] != config[SLACK_JSON_VERIFICATION_TOKEN]:
            self._verification_token = config[SLACK_JSON_VERIFICATION_TOKEN]

        try:
            if self._verification_token:
                self._state['token'] = self.encrypt_state(self._verification_token, "verification")
        except Exception as e:
            self.debug_print("{}: {}".format(SLACK_ENCRYPTION_ERROR, self._get_error_message_from_exception(e)))
            return self.set_status(phantom.APP_ERROR, SLACK_ENCRYPTION_ERROR)

        self.save_state(self._state)
        # The default permission of state file in Phantom v4.9 is 600. So when from rest handler method (handle_request) reads this state file,
        # the action fails with "permission denied" error message
        # Adding the data of state file to another temporary file to resolve this issue
        _save_app_state(self._state, self.get_asset_id(), self)
        question = param['question']
        if len(question) > SLACK_MESSAGE_LIMIT:
            return RetVal(action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_QUESTION_TOO_LONG.format(limit=SLACK_MESSAGE_LIMIT)))
        qid = uuid.uuid4().hex

        answer_filename = '{0}.json'.format(qid)
        answer_path = "{0}/{1}".format(local_data_state_dir, answer_filename)

        confirmation = param.get('confirmation', ' ')
        if len(confirmation) > SLACK_CONFIRMATION_LIMIT:
            return RetVal(action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_CONFIRMATION_TOO_LONG.format(limit=SLACK_CONFIRMATION_LIMIT)))

        path_json = {'qid': qid,
                     'asset_id': str(self.get_asset_id()),
                     'confirmation': confirmation}

        callback_id = json.dumps(path_json)
        if len(callback_id) > 255:
            path_json['confirmation'] = ''
            valid_length = 255 - len(json.dumps(path_json))
            return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_LENGTH_LIMIT_EXCEEDED.format(
                asset_length=len(self.get_asset_id()), valid_length=valid_length))

        self.save_progress('Asking question with ID: {0}'.format(qid))

        answers = []
        given_answers = [x.strip().lower() for x in param.get('responses', 'yes,no').split(',')]
        ordered_answers = []
        for answer in given_answers:
            if answer not in ordered_answers:
                ordered_answers.append(answer)
        given_answers = list(filter(None, ordered_answers))

        if not given_answers:
            given_answers = ['yes', 'no']

        for answer in given_answers:
            answer_json = {'name': answer, 'text': answer, 'value': answer, 'type': 'button'}
            answers.append(answer_json)

        answer_json = [
            {
                'text': question,
                'fallback': 'Phantom cannot post questions on this channel.',
                'callback_id': callback_id,
                'color': '#422E61',
                'attachment_type': 'default',
                'actions': answers
            }
        ]
        params = {'channel': user, 'attachments': json.dumps(answer_json), 'as_user': True}

        ret_val, resp_json = self._make_slack_rest_call(action_result, SLACK_SEND_MESSAGE, params)
        if not ret_val:
            message = action_result.get_message()
            if message:
                error_message = "{}: {}".format(SLACK_ERROR_ASKING_QUESTION, message)
            else:
                error_message = SLACK_ERROR_ASKING_QUESTION
            return action_result.set_status(phantom.APP_ERROR, error_message), None

        data = {"qid": qid, "answer_path": answer_path}
        return action_result.set_status(phantom.APP_SUCCESS), data

    def _ask_question_channel(self, param):

        self.save_progress("In action handler for: {0}".format(self.get_action_identifier()))
        action_result = self.add_action_result(phantom.ActionResult(dict(param)))

        user = param['destination']
        if user.startswith('@') or user.startswith('U'):
            # Don't want to send question to channels because then we would not know who was answering
            return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_UNABLE_TO_SEND_QUESTION_TO_USER)

        ret_val, resp_json = self._handle_ask_question(action_result, param, user)

        if phantom.is_fail(ret_val):
            return action_result.get_status()

        action_result.add_data(resp_json)
        return action_result.set_status(phantom.APP_SUCCESS, SLACK_SUCCESSFULLY_ASKED_QUESTION)

    def _ask_question(self, param):

        self.save_progress("In action handler for: {0}".format(self.get_action_identifier()))
        action_result = self.add_action_result(phantom.ActionResult(dict(param)))

        user = param['destination']
        if user.startswith('#') or user.startswith('C'):
            # Don't want to send question to channels because then we would not know who was answering
            return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_UNABLE_TO_SEND_QUESTION_TO_CHANNEL)

        ret_val, resp_json = self._handle_ask_question(action_result, param, user)

        if phantom.is_fail(ret_val):
            return action_result.get_status()

        self.debug_print("resp json : {}".format(resp_json))
        answer_path = resp_json.get('answer_path')
        qid = resp_json.get('qid')

        loop_count = (self._timeout * 60) / self._interval
        count = 0

        while True:
            if count >= loop_count:
                action_result.set_summary({'response_received': False, 'question_id': qid})
                return action_result.set_status(phantom.APP_SUCCESS)

            try:
                answer_file = open(answer_path, 'r')
            except Exception:
                count += 1
                time.sleep(self._interval)
                continue

            try:
                resp_json = json.loads(answer_file.read())
                answer_file.close()
            except Exception:
                return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_UNABLE_TO_PARSE_RESPONSE)

            break

        payload = resp_json.get('payloads')[0]
        action_result.add_data(payload)
        action_result.set_summary({'response_received': True, 'question_id': qid, 'response': payload.get("actions", [{}])[0].get("value")})

        os.remove(answer_path)

        return action_result.set_status(phantom.APP_SUCCESS)

    def _get_response(self, param):

        action_result = self.add_action_result(phantom.ActionResult(dict(param)))

        qid = param['question_id']
        state_dir = self.get_state_dir()
        answer_path = '{0}/{1}.json'.format(state_dir, qid)
        self.debug_print("answer path : {}".format(answer_path))
        self.save_progress('Checking for response to question with ID: {0}'.format(qid))

        try:
            answer_file = open(answer_path, 'r')
        except Exception:
            return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_QUESTION_RESPONSE_NOT_AVAILABLE)

        try:
            resp_json = json.loads(answer_file.read())
            answer_file.close()
        except Exception:
            return action_result.set_status(phantom.APP_ERROR, SLACK_ERROR_UNABLE_TO_PARSE_RESPONSE)

        action_result.add_data(resp_json)
        action_result.set_summary({'response_received': True})

        return action_result.set_status(phantom.APP_SUCCESS)

    def handle_action(self, param):

        ret_val = None

        # Get the action that we are supposed to execute for this App Run
        action_id = self.get_action_identifier()

        self.debug_print("action_id: {}".format(self.get_action_identifier()))

        if action_id == ACTION_ID_TEST_CONNECTIVITY:
            ret_val = self._test_connectivity(param)
        elif action_id == ACTION_ID_LIST_CHANNELS:
            ret_val = self._list_channels(param)
        elif action_id == ACTION_ID_POST_MESSAGE:
            ret_val = self._send_message(param)
        elif action_id == ACTION_ID_ADD_REACTION:
            ret_val = self._add_reaction(param)
        elif action_id == ACTION_ID_ASK_QUESTION:
            ret_val = self._ask_question(param)
        elif action_id == ACTION_ID_ASK_QUESTION_CHANNLE:
            ret_val = self._ask_question_channel(param)
        elif action_id == ACTION_ID_GET_RESPONSE:
            ret_val = self._get_response(param)
        elif action_id == ACTION_ID_UPLOAD_FILE:
            ret_val = self._upload_file(param)
        elif action_id == ACTION_ID_LIST_USERS:
            ret_val = self._list_users(param)
        elif action_id == ACTION_ID_GET_USER:
            ret_val = self._get_user(param)
        elif action_id == ACTION_ID_STOP_BOT:
            ret_val = self._stop_bot(param)
        elif action_id == ACTION_ID_ON_POLL:
            ret_val = self._on_poll(param)
        elif action_id == ACTION_ID_CREATE_CHANNEL:
            ret_val = self._create_channel(param)
        elif action_id == ACTION_ID_INVITE_USERS:
            ret_val = self._invite_users(param)

        return ret_val


if __name__ == '__main__':

    # import pudb
    # pudb.set_trace()

    if len(sys.argv) < 2:
        print("No test json specified as input")
        sys.exit(0)

    with open(sys.argv[1]) as f:
        in_json = f.read()
        in_json = json.loads(in_json)
        print(json.dumps(in_json, indent=4))

        connector = SlackConnector()
        connector.print_progress_message = True
        ret_val = connector._handle_action(json.dumps(in_json), None)
        print(json.dumps(json.loads(ret_val), indent=4))

    sys.exit(0)
