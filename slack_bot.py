# File: slack_bot.py
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
import logging
import logging.handlers
import os
import re
import shlex
import sys
import tempfile
from argparse import ArgumentParser
from pathlib import Path

import encryption_helper
import requests
import simplejson as json
import six
import urllib3
from bs4 import UnicodeDammit
from phantom.base_connector import APPS_STATE_PATH
from slack_bolt import App as slack_app
from slack_bolt.adapter.socket_mode import SocketModeHandler

from slack_connector import process_payload
from slack_consts import *
from slack_consts import SLACK_DEFAULT_TIMEOUT


urllib3.disable_warnings()

app_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.exists("{}/dependencies".format(app_dir)):  # noqa
    os.sys.path.insert(0, "{}/dependencies/websocket-client".format(app_dir))  # noqa
    os.sys.path.insert(0, "{}/dependencies".format(app_dir))  # noqa

SLACK_JSON_MESSAGE_LIMIT = 4000
SLACK_JSON_API_URL = "https://slack.com/api/"

SLACK_BOT_HELP_MESSAGE = """
usage:

@<bot_username> act|run_playbook|get_container|list

For more information on a specific command, try @<bot_username> <command> --helpprint                     """

SLACK_ACTION_HELP_MESSAGE = """
usage:

act ACTION_NAME [--container CONTAINER_ID] [--asset ASSET] [--name NAME]
    [--TYPE TYPE] [--parameters PARAMETER:VALUE [PARAMETER:VALUE]*]

required arguments:
  ACTION_NAME               Name of the action to run
  --container CONTAINER_ID  ID of the container to run the action on

optional arguments:
  --help                    show this help message or show information about the specified action
  --name NAME               Set a name for the action (defaults to 'Slack generated action')
  --type TYPE               Set the type of the action (defaults to 'phantombot')
  --asset ASSET             Name or ID of the asset to run the action on
                            If no asset is specified, the given action will run on all possible assets
  --parameters PARAMETER:VALUE [PARAMETER:VALUE]*]
                            List of parameter/value pairs in the format
                            param1:value1 param2:value2...

For example:
    @<bot_username> act "geolocate ip" --parameters ip:1.1.1.1 --container 1291
                            """

SLACK_PLAYBOOK_HELP_MESSAGE = """
usage:

run_playbook <--repo REPO PLAYBOOK_NAME | PLAYBOOK_ID> CONTAINER_ID

required arguments:
  PLYBOOK_NAME      Name of the playbook to run (Required if repo argument is included)
  PLYBOOK_ID        ID of the playbook to run (Required if no repo argument is included)
  CONTAINER_ID      ID of container to run playbook on

optional arguments:
  --help        show this help message and exit
  --repo REPO   Name of the repo the playbook is in (required if playbook
                argument is a name, and not an ID)

For example:
    @<bot_username> run_playbook --repo community invesigate 25
  or
    @<bot_username> run_playbook 1 25
                              """

SLACK_CONTAINER_HELP_MESSAGE = """
usage:

get_container <--container CONTAINER_ID | --tags TAG [TAG]*>

arguments:
  --help                    show this help message and exit
  --container CONTAINER     ID of the container to retrieve
  --tags TAG [TAG]*         List of tags of containers to retrieve

Only one of --container or --tags flags can be included at once

For example:
    @<bot_username> get_container --container 16
  or
    @<bot_username> get_container --tags tag1 tag2 tag3
                               """

SLACK_LIST_HELP_MESSAGE = """
usage:

list <actions|containers>

arguments:
  --help        show this help message and exit
  object        name of object to list, can be 'actions' or 'containers'

For example:
    @<bot_username> list containers
  or
    @<bot_username> list actions
                          """


def _load_app_state(asset_id):
    """This function is used to load the current state file.

    :param asset_id: asset_id
    :return: state: Current state file as a dictionary
    """
    asset_id = str(asset_id)
    if not asset_id or not asset_id.isalnum():
        print("In _load_app_state: Invalid asset_id")
        return {}

    app_dir = os.path.dirname(os.path.abspath(__file__))

    state_file = f"{app_dir}/{asset_id}_state.json"
    real_state_file_path = os.path.realpath(state_file)

    if os.path.dirname(real_state_file_path) != app_dir:
        print("In _load_app_state: Invalid asset_id")
        return {}

    state = {}
    try:
        with open(real_state_file_path) as state_file_obj:
            state_file_data = state_file_obj.read()
            state = json.loads(state_file_data)

    except Exception as e:
        print(f"In _load_app_state: Exception: {e!s}")

    print("Loaded state: ", state)

    return state


def decrypt_state(asset_id, decrypt_var, token_name):
    """Handle decryption of token.
    :param decrypt_var: Variable needs to be decrypted
    :return: decrypted variable
    """
    print(SLACK_DECRYPT_TOKEN.format(token_name))  # nosemgrep
    return encryption_helper.decrypt(decrypt_var, asset_id)


class Action:
    def __init__(self, name, action_id, app):
        self.name = name
        self.action_id = action_id
        self.app = app
        self.assets = []
        self.parameters = {}

    def add_parameters(self, params):
        for param_name, param_dict in six.iteritems(params):
            required = param_dict.get("required", False)
            data_type = param_dict["data_type"]

            self.parameters[param_name] = Parameter(param_name, required, data_type)


class Parameter:
    def __init__(self, name, required, data_type):
        self.name = name
        self.required = required
        self.data_type = data_type


class Asset:
    def __init__(self, name, asset_id, apps):
        self.name = name
        self.asset_id = asset_id
        self.apps = apps


class App:
    def __init__(self, name, app_id):
        self.name = name
        self.app_id = app_id


class SlackBot:
    def __init__(
        self,
        bot_token,
        socket_token,
        bot_id,
        base_url="https://127.0.0.1/",
        verify=False,
        auth_token="",
        permit_act=False,
        permit_playbook=False,
        permit_container=False,
        permit_list=False,
        permitted_users="",
        auth_basic=(),
        app_id="",
    ):
        """This should be changed to some kind of load config thing"""
        self.bot_token = bot_token
        self.socket_token = socket_token
        self.permit_act = permit_act
        self.permit_playbook = permit_playbook
        self.permit_container = permit_container
        self.permit_list = permit_list
        self.permitted_users = permitted_users
        self.headers = {} if not auth_token else {"ph-auth-token": auth_token}
        self.cmd_start = f"<@{bot_id}>"
        self.auth = auth_basic
        self.verify = verify
        self.app_id = app_id
        base_url += "/" if not base_url.endswith("/") else ""
        self.base_url = base_url
        self.phantom_url = base_url
        self.verification_token = None
        self._init_containers()
        self._generate_dicts()
        self._init_parsers()

    def _init_containers(self):
        self.action_queue = []
        self.app_run_queue = []
        self.playbook_queue = []

    def _generate_dicts(self):
        """In order to easily keep track of and verify actions
        phantom.bot creates a couple of dictionaries
        """
        self.app_dict = {}
        self.asset_dict = {}
        self.action_dict = {}
        self.app_to_asset_dict = {}

        self._create_app_dict()
        self._create_asset_dict()
        self._create_action_dict()

    def _init_parsers(self):
        self.action_parser = ArgumentParser(add_help=False, exit_on_error=False)
        self.action_parser.add_argument("action")
        self.action_parser.add_argument("--help", dest="aid", action="store_true")
        self.action_parser.add_argument("--container")
        self.action_parser.add_argument("--name", default="Slack generated action")
        self.action_parser.add_argument("--type", dest="typ", default="phantombot")
        self.action_parser.add_argument("--asset")
        self.action_parser.add_argument("--parameters", nargs="+")

        self.playbook_parser = ArgumentParser(exit_on_error=False)
        self.playbook_parser.add_argument(
            "--repo", dest="repo", help="Name of the repo the playbook is in (required if playbook argument is a name, and not an ID)"
        )
        self.playbook_parser.add_argument("playbook", help="Name or ID of the playbook to run")
        self.playbook_parser.add_argument("container", help="ID of container to run playbook on")

        self.container_parser = ArgumentParser(exit_on_error=False)
        self.container_parser.add_argument("--container")
        self.container_parser.add_argument("--tags", nargs="+")

        self.list_parser = ArgumentParser(exit_on_error=False, add_help=False)
        self.list_parser.add_argument("--help", dest="aid", action="store_true")
        self.list_parser.add_argument("listee", choices=["actions", "containers"])

    def _create_app_dict(self):
        """Maps app IDs and names to app objects"""

        try:
            r = requests.get(
                self.base_url + "rest/app?page_size=0&pretty",
                headers=self.headers,
                auth=self.auth,
                verify=self.verify,
                timeout=SLACK_DEFAULT_TIMEOUT,
            )
        except Exception:
            return

        if r.status_code != 200:
            return

        for app in r.json().get("data", []):
            app_name = app.get("name", "")
            app_id = app.get("id")

            if not (app_id and app_name):
                continue

            app_object = App(app_name, app_id)

            self.app_dict[app_id] = app_object
            self.app_dict[app_name] = app_object

    def _create_asset_dict(self):
        """Maps asset IDs and names to asset objects
        " Also maps app IDs to lists of associated asset IDs
        """

        try:
            r = requests.get(
                self.base_url + "rest/build_action", headers=self.headers, auth=self.auth, verify=self.verify, timeout=SLACK_DEFAULT_TIMEOUT
            )
        except Exception:
            return

        if r.status_code != 200:
            return

        for asset in r.json().get("assets", []):
            asset_name = asset.get("name", "")
            asset_id = asset.get("id")
            asset_apps = asset.get("apps", [])

            if len(asset_apps) > 1:
                for app_id in asset_apps:
                    app = self.app_dict.get(app_id)

                    if not app:
                        asset_apps.remove(app_id)

            if not (asset_id and asset_name):
                continue

            for app in asset_apps:
                if app not in self.app_to_asset_dict:
                    self.app_to_asset_dict[app] = []

                self.app_to_asset_dict[app] += [asset_id]

            asset_object = Asset(asset_name, asset_id, asset_apps)

            self.asset_dict[asset_id] = asset_object
            self.asset_dict[asset_name] = asset_object

    def _create_action_dict(self):
        """Maps actions names to action objects"""

        try:
            r = requests.get(
                self.base_url + "rest/app_action?page_size=0",
                headers=self.headers,
                auth=self.auth,
                verify=self.verify,
                timeout=SLACK_DEFAULT_TIMEOUT,
            )
        except Exception:
            return

        if r.status_code != 200:
            return

        for action in r.json().get("data", []):
            action_name = action.get("action", "")
            action_id = action.get("id")
            action_app = action.get("app")

            if not (action_name and action_id and action_app):
                continue

            if action_name not in self.action_dict:
                self.action_dict[action_name] = []

            action_object = Action(action_name, action_id, action_app)

            action_object.add_parameters(action["parameters"])

            action_object.assets = self.app_to_asset_dict.get(action_app, [])

            self.action_dict[action_name] += [action_object]

    def _create_container_dict(self):
        """Maps container IDs to container objects"""

        try:
            r = requests.get(
                self.base_url + "rest/container?page_size=0",
                headers=self.headers,
                auth=self.auth,
                verify=self.verify,
                timeout=SLACK_DEFAULT_TIMEOUT,
            )
        except Exception:
            return None

        if r.status_code != 200:
            return None

        container_dict = {}

        for container in r.json().get("data", []):
            container_id = container.get("id")

            if not container_id:
                continue

            tags = container["tags"]

            for tag in tags:
                if tag not in container_dict:
                    container_dict[tag] = []

                container_dict[tag].append(container_id)

        return container_dict

    def _action_run_request(self, body, channel):
        try:
            r = requests.post(
                self.base_url + "rest/action_run",
                json=body,
                headers=self.headers,
                auth=self.auth,
                verify=self.verify,
                timeout=SLACK_DEFAULT_TIMEOUT,
            )

            resp = r.json()

        except Exception as e:
            return f"Failed to run action: Could not connect to Phantom REST endpoint: {e}"

        if resp.get("failed"):
            error = resp.get("message", "unknown error")

            if '"Container.owner" must be a "PhUser" instance' in error:
                return "Failed to run action: A container must have an owner to run an action on it.\n\n"

            return f"Failed to run action: {error}\n\n"

        run_id = resp.get("action_run_id")

        if not run_id:
            return "Failed to run action: Could not get action run ID"

        self.action_queue.append((run_id, channel))

        action_url = f"{self.phantom_url}action/{run_id}"

        self._post_message(f"Action run URL: {action_url}", channel, code_block=False)

        return "Message: {}\nAction run ID: {}".format(resp["message"], run_id)

    def _playbook_request(self, body, channel):
        try:
            r = requests.post(
                self.base_url + "rest/playbook_run",
                json=body,
                headers=self.headers,
                auth=self.auth,
                verify=self.verify,
                timeout=SLACK_DEFAULT_TIMEOUT,
            )

            resp = r.json()

        except Exception as e:
            return f"Failed to run playbook: Could not connect to Phantom REST endpoint: {e}"

        if resp.get("failed", False):
            return "Failed to run playbook: {}".format(resp.get("message", "unknown error"))

        run_id = resp.get("playbook_run_id")

        if not run_id:
            return "Failed to run playbook: Could not get playbook run ID"

        self.playbook_queue.append((run_id, channel))

        container_id = body.get("container_id", "")
        playbook_id = body.get("playbook_id", "")

        action_url = f"{self.phantom_url}mission/{container_id}"

        self._post_message(f"Container URL: {action_url}", channel, code_block=False)

        return "Playbook: {}\nPlaybook run ID: {}\nPlaybook queueing result: Playbook run successfully queued".format(
            playbook_id, resp["playbook_run_id"]
        )

    def _add_to_app_queue(self, action_run_id, channel):
        try:
            r = requests.get(
                self.base_url + f"rest/action_run/{action_run_id}/app_runs",
                headers=self.headers,
                auth=self.auth,
                verify=self.verify,
                timeout=SLACK_DEFAULT_TIMEOUT,
            )

            resp = r.json()

        except Exception as e:
            return f"Failed to run action: Could not connect to Phantom REST endpoint: {e}"

        for app_run in resp["data"]:
            self.app_run_queue.append((app_run["id"], channel))

    def _check_action_queue(self):
        for action_id, channel in self.action_queue:
            try:
                r = requests.get(
                    self.base_url + f"rest/action_run/{action_id}",
                    headers=self.headers,
                    auth=self.auth,
                    verify=self.verify,
                    timeout=SLACK_DEFAULT_TIMEOUT,
                )

                resp = r.json()

            except Exception:
                continue

            if resp.get("status", "") in ["success", "failed"]:
                self._add_to_app_queue(resp["id"], channel)

                self.action_queue.remove((action_id, channel))

    def _check_app_run_queue(self):
        for app_run_id, channel in self.app_run_queue:
            try:
                r = requests.get(
                    self.base_url + f"rest/app_run/{app_run_id}",
                    headers=self.headers,
                    auth=self.auth,
                    verify=self.verify,
                    timeout=SLACK_DEFAULT_TIMEOUT,
                )

                resp = r.json()

            except Exception:
                continue

            status = resp.get("status", "unknown")

            if status in ["success", "failed"]:
                asset = self.asset_dict.get(resp.get("asset"))

                asset_name = "N/A" if asset is None else asset.name

                msg = "Action:  {}\n".format(resp.get("action"))
                msg += f"Asset:  {asset_name}\n"
                msg += f"Status:  {status}\n"

                result_data = resp.get("result_data", [])

                if len(result_data) > 0:
                    result_data = result_data[0]

                    msg += "Message: {}\n".format(result_data.get("message", status))

                    parameters = result_data.get("parameter", [])

                    if len(parameters) > 1:
                        msg += "Parameters:\n"

                        for key, value in six.iteritems(parameters):
                            if key == "context":
                                continue

                            msg += f"  {key}: {value}\n"

                    summary = result_data.get("summary", "")

                    if summary:
                        msg += "Summary:\n"

                        for key, value in six.iteritems(summary):
                            msg += f"  {key}: {value}\n"

                else:
                    msg += "Message: {}\n".format(resp.get("message", status))

            self.app_run_queue.remove((app_run_id, channel))

            self._post_message(msg, channel)

    def _check_playbook_queue(self):
        for playbook_id, channel in self.playbook_queue:
            try:
                r = requests.get(
                    self.base_url + f"rest/playbook_run/{playbook_id}",
                    headers=self.headers,
                    auth=self.auth,
                    verify=self.verify,
                    timeout=SLACK_DEFAULT_TIMEOUT,
                )

                resp = r.json()

            except Exception:
                continue

            status = resp.get("status", "unknown")

            if status in ["success", "failed"]:
                msg = "Playbook: {}\n".format(resp.get("playbook", "unknown"))
                msg += "Playbook run ID: {}\n".format(resp.get("id", "unknown"))
                msg += f"Playbook run result: {status}\n"

            else:
                continue

            self.playbook_queue.remove((playbook_id, channel))

            self._post_message(msg, channel)

            return

    def _sanitize(self, string):
        """Slack quotes use those fancy UTF-8 ones that flip based on what side they are on
        " Unforunately, those cause problems, so we replace them with normal quotes
        " I'm sure there are other UTF-8 characters that will need to be replaced like this,
        " but I haven't run into those yet
        " Emdashes (u2014) are another of those characters.
        " Slack also formats URLs annoyingly. A message containing a domain (eg google.com) will get changed to
        " <http://google.com/|google.com>. While a full URL (eg http://google.com) will get changed to
        " <http://google.com>. Need to look for both cases and get rid of the carrots and pipe (<|>).
        " And in the domain case, get rid of the URL.
        """

        string = (
            string.replace("\xe2\x80\x9c", '"')
            .replace("\xe2\x80\x9d", '"')
            .replace("\xe2\x80\x94", "--")
            .replace("\xe2\x80\x98", "'")
            .replace("\xe2\x80\x99", "'")
        )

        while string.find("<") > -1 and string.find(">") > -1:
            left_index = string.find("<")
            right_index = string.find(">")
            pipe_index = string.find("|")

            if pipe_index > left_index and pipe_index < right_index:
                url = string[pipe_index + 1 : right_index]

            else:
                url = string[left_index + 1 : right_index]

            string = string.replace(string[left_index : right_index + 1], url, 1)

        return string

    def _post_message(self, msg, channel, code_block=True):
        url = SLACK_JSON_API_URL + "chat.postMessage"

        body = {}
        body["channel"] = channel
        body["token"] = self.bot_token
        body["as_user"] = True

        if msg:
            if len(msg) <= SLACK_JSON_MESSAGE_LIMIT:
                body["text"] = f"```{msg}```" if code_block else msg

                requests.post(url, data=body, timeout=SLACK_DEFAULT_TIMEOUT)

                return

            last_newline = msg[: SLACK_JSON_MESSAGE_LIMIT - 1].rfind("\n")

            to_send = msg[:last_newline]

            body["text"] = f"```{to_send}```" if code_block else to_send

            requests.post(url, data=body, timeout=SLACK_DEFAULT_TIMEOUT)

            self._post_message(msg[last_newline + 1 :], channel, code_block=code_block)

    def _parse_action(self, command):
        try:
            parsed_args = self.action_parser.parse_args(command)
        except:  # passing type as Exception weren't able to to catch SystemError exception. Even with multiple exceptions it didn't work
            return False, SLACK_ACTION_HELP_MESSAGE

        self._generate_dicts()

        request_body = {}
        request_body["targets"] = []

        # Initialize for static analysis safety
        asset_object = None
        action_object = None

        asset = parsed_args.asset
        action = parsed_args.action
        params = parsed_args.parameters
        container = parsed_args.container

        if action not in self.action_dict:
            return False, f"Could not find action, {action}"

        action_list = self.action_dict[action]

        if asset:
            message, result_asset, result_action = self._parse_asset(asset, action, action_list)

            if not (result_asset and result_action):
                return False, message

            asset_object = result_asset
            action_object = result_action

        if parsed_args.aid or not container:
            if asset:
                total_message = f"Info on {action} action on {asset} asset:\n"
            else:
                total_message = f"List of available '{action}' actions:\n"

            for action_object in action_list:
                if not action_object.assets:
                    continue

                if asset and asset_object and asset_object.asset_id not in action_object.assets:
                    continue

                try:
                    message = f"ID: {action_object.action_id}\n"
                    message += f"App: {self.app_dict[action_object.app].name}\n"

                    message += "Assets: "

                    for ass in action_object.assets:
                        message += f"{self.asset_dict[ass].name}, "

                    message = message[:-2]
                    message += "\nParameters:\n"

                    for param in list(action_object.parameters.values()):
                        message += f"  {param.name}:\n"
                        message += f"    Data Type: {param.data_type}\n"
                        message += f"    Required: {param.required}\n"

                    total_message += f"\n{message}"

                except Exception:
                    continue

            if not container:
                total_message += (
                    "\nThis help message was printed because no container ID was provided."
                    "\nPlease specify a container if you would like to run this action."
                )

            return False, total_message

        request_body["action"] = action
        request_body["type"] = parsed_args.typ
        request_body["name"] = parsed_args.name
        request_body["container_id"] = container

        # If an asset was passed as an argument, we only want to run one action
        if asset and asset_object:
            target = {}
            target["app_id"] = asset_object.apps[0]
            target["assets"] = [asset_object.asset_id]

            ret_val, message = self._parse_params(params, action_object.parameters, target)

            if not ret_val:
                return False, message

            request_body["targets"].append(target)

        # If no asset argument was passed, we need to find all actions that have the name given
        else:
            for action_object in action_list:
                if not action_object.assets:
                    continue

                target = {}
                target["app_id"] = action_object.app
                target["assets"] = action_object.assets

                ret_val, message = self._parse_params(params, action_object.parameters, target)

                if not ret_val:
                    return False, message

                request_body["targets"].append(target)

            if not request_body["targets"]:
                return False, "There are no valid assets to run this action on."

        return True, request_body

    def _parse_asset(self, asset, action, action_list):
        found1 = True

        if asset not in self.asset_dict:
            found1 = False

        else:
            asset_object = self.asset_dict[asset]

            if len(asset_object.apps) == 0:
                return (f"Invalid asset: {asset}", None, None)

            if len(asset_object.apps) > 1:
                return (f"Invalid asset: {asset} (Temporarily), too many apps to choose from", None, None)

            found2 = False

            for action_object in action_list:
                if asset_object.asset_id in action_object.assets:
                    found2 = True
                    break

        if (not found1) or (not found2):
            message = f"Asset '{asset}' is not valid for action '{action}'\n\nList of valid assets for {action}:\n"

            for action_object in action_list:
                for asset_id in action_object.assets:
                    if asset_id in self.asset_dict:
                        message += f"\n{self.asset_dict[asset_id].name}"

            return (message, None, None)

        return (None, asset_object, action_object)

    def _parse_params(self, params, param_dict, target):
        if (not params) and (param_dict):
            for param in list(param_dict.values()):
                if param.required:
                    return False, "Specified action requires parameters, none given"

        if not params:
            return True, None

        parameter_dict = {}

        for param in params:
            spl_param = param.split(":", 1)

            if len(spl_param) < 2:
                return False, "Action parameters not formatted correctly"

            param_name = spl_param[0]

            if param_name not in param_dict:
                return False, f"Invalid parameter: {param_name}"

            parameter_dict[param_name] = spl_param[1]

        target["parameters"] = [parameter_dict]

        # Make sure all required parameters are present
        for key, value in six.iteritems(param_dict):
            if value.required:
                for params in target["parameters"]:
                    if key not in params:
                        return False, f"Missing required parameter: {key}"

        return True, None

    def _parse_playbook(self, command):
        try:
            args = self.playbook_parser.parse_args(command)

        except:
            return False, SLACK_PLAYBOOK_HELP_MESSAGE

        request_body = {}
        request_body["run"] = True
        request_body["container_id"] = args.container

        # Check to see if its a numeric ID
        try:
            playbook = int(args.playbook)

        except Exception:
            if not args.repo:
                return False, "repo argument is required when supplying playbook name instead of playbook ID"

            playbook = f"{args.repo}/{args.playbook}"

        request_body["playbook_id"] = playbook

        return True, request_body

    def _parse_container(self, command):
        try:
            parsed_args = self.container_parser.parse_args(command)

        except:
            return False, SLACK_CONTAINER_HELP_MESSAGE

        container = parsed_args.container
        tags = parsed_args.tags

        # Perform on XOR to make sure only one of the arguments is set
        if (container is not None) == (tags is not None):
            return False, SLACK_CONTAINER_HELP_MESSAGE

        if container:
            container_info = {}

            try:
                container = int(container)

                try:
                    r = requests.get(
                        self.base_url + f"rest/container/{container}",
                        headers=self.headers,
                        auth=self.auth,
                        verify=self.verify,
                        timeout=SLACK_DEFAULT_TIMEOUT,
                    )
                except Exception as e:
                    return False, f"Could not retrieve container data. Could not connect to REST endpoint: {e}"

                container_info = r.json()

            except Exception:
                try:
                    return False, f"Could not parse container ID: {container}"
                except Exception:
                    return False, "Could not parse given container ID"

            message = ""

            for key, value in six.iteritems(container_info):
                if key == "tags":
                    message += "tags: "

                    for tag in value:
                        message += f' "{tag}",'

                    message = message[:-1]

                    message += "\n"

                    continue

                try:
                    message += f"{key}: {value}\n"
                except Exception:
                    message += "{}: {}\n".format(key, "Value could not be parsed")

            return True, message

        elif tags:
            container_dict = self._create_container_dict()

            if container_dict is None:
                return False, "Could not get containers, error contactin REST endpoint"

            if not container_dict:
                return False, "Found no containers on the Phantom instance"

            bad_tags = []
            container_list = []

            for tag in tags:
                if tag not in container_dict:
                    bad_tags.append(tag)
                    continue

                container_list += container_dict[tag]

            container_list = list(set(container_list))

            num_conts = len(container_list)

            message = "Found {} container{} matching specified tags:\n\n".format(num_conts, "s" if num_conts != 1 else "")

            for container in container_list:
                try:
                    r = requests.get(
                        self.base_url + f"rest/container/{container}",
                        headers=self.headers,
                        auth=self.auth,
                        verify=self.verify,
                        timeout=SLACK_DEFAULT_TIMEOUT,
                    )

                    resp_text = r.text
                    info = json.loads(resp_text)

                except Exception as e:
                    message += f"Could not retrieve container data for {container}: {e}\n\n"

                try:
                    message += "Name: {}\n".format(info["name"])
                    message += "ID: {}\n".format(info["id"])
                    message += "Label: {}\n".format(info["label"])
                    message += "Tags:"

                    for tag in info["tags"]:
                        message += f' "{tag}",'

                    message = message[:-1]

                    message += "\n\n"
                except Exception:
                    message += "COULD NOT PARSE CONTAINER INFO\n\n"

            if bad_tags:
                message += "Tags with no results: {}".format(" ".join(bad_tags))

            return True, message

    def _parse_list(self, command):
        try:
            parsed_args = self.list_parser.parse_args(command)
        except:
            return False, SLACK_LIST_HELP_MESSAGE

        self._generate_dicts()

        if parsed_args.listee == "actions":
            msg = ""
            sorted_actions = list(self.action_dict.keys())
            sorted_actions.sort()

            for action in sorted_actions:
                msg += f"{action}\n"

            msg += '\nFor more info on an action, try "act <action_name>"'

        elif parsed_args.listee == "containers":
            msg = ""

            try:
                r = requests.get(
                    self.base_url + "rest/container?page_size=0",
                    headers=self.headers,
                    auth=self.auth,
                    verify=self.verify,
                    timeout=SLACK_DEFAULT_TIMEOUT,
                )
            except Exception as e:
                return False, f"Could not retrieve container data. Could not connect to REST endpoint: {e}"

            for container in r.json()["data"]:
                try:
                    msg += "ID: {}".format(container["id"]).ljust(10) + "Name: {}\n".format(container["name"])
                except Exception:
                    msg += "Container info could not be parsed"

            msg += '\nFor more information on a container, try "get_container <container_id>"'

        return True, msg

    def _from_on_poll(self):
        """
        On poll method helps to establish the web socket connection with slack bot app on you slack
        using the slack-bolt sdk.
        """
        app = slack_app(token=self.bot_token)

        # decorator to catch responses to actions. Using RE to confirm the payload is in the format we expect
        # it should be given it is a response to an interactive button sent by ask_question
        @app.action({"type": "interactive_message", "callback_id": re.compile('{"qid": ".*')})
        def interactive_message_handler(ack, body, respond):
            """
            interactive_message_handler is used to handle responses to buttons actions sent by the ask_question
            action. It receives a json body which contains the data of the event. The contents of the event are
            written to the $PHANTOM_HOME/local_data/app_stats/$APP_ID folder. The ask_question action runs a loop
            looking for files in this directory - it will pickup and process the file once it is written.
            """
            ack()
            try:
                if body:
                    callback_id = body.get("callback_id")
                    callback_json = json.loads(UnicodeDammit(callback_id).unicode_markup)
                    qid = callback_json.get("qid")
                    confirmation_message = callback_json.get("confirmation")
                    state_dir = f"{APPS_STATE_PATH}/{self.app_id}"

                    answer_filename = f"{qid}.json"
                    answer_path = f"{state_dir}/{answer_filename}"
                    logging.debug(f"**going to put answer file here: {answer_path}")

                    final_payload = process_payload(body, answer_path)

                    try:
                        with open(answer_path, "w") as answer_file:  # nosemgrep
                            answer_file.write(json.dumps(final_payload))
                    except Exception as e:
                        print(f"Exception occured while writing reponse to {answer_path}. Exception: {e}")
                    respond(confirmation_message)
            except Exception as e:
                print(f"Unknown exception occured while processing answer response. Exception: {e}")

        @app.event("app_mention")
        def mention_handler(body, say):
            """
            mention handler function uses a app_mention event decorator to response to the events whenever the bot
            is mentioned in the cat. It receives a json body which contains the data of the event. The command and
            channel name are parsed from the body and passed to command handler to further process the command.
            """
            logging.info("**app_mention handler hit")
            if body:
                # logging.debug('**body from app mention: {}'.format(body))
                user = body.get("event", {}).get("user")
                logging.info(f"**user that spawned bot command is {user}")
                if not self._check_user_authorization(user):
                    say(f"`User {user} is not authorized to use this bot`")
                    return

                out_text = body.get("event", {}).get("text")
                logging.debug(f"**body exists, app_mention text: {out_text}")

                if out_text and out_text.startswith(self.cmd_start):
                    if out_text.strip() == self.cmd_start:
                        self._post_message(
                            SLACK_BOT_HELP_MESSAGE,
                            body.get("event", {}).get("channel", "#general"),
                        )

                    channel = body.get("event", {}).get("channel", "#general")
                    command = out_text[len(self.cmd_start) :].strip()

                    if command and channel:
                        command = self._sanitize(command)
                        try:
                            self._handle_command(command, channel)
                        except Exception as e:
                            try:
                                self._post_message(
                                    f"Could not run command:\n\n{command}\n\n{e}",
                                    channel,
                                )
                            except Exception as e:
                                self._post_message(f"Could not run command:\n\n{e}", channel)

        handler = SocketModeHandler(app, self.socket_token)
        handler.start()

    def _check_user_authorization(self, user):
        logging.info(f'**Checking authorization for user "{user}"')
        permitted_users = self.permitted_users

        if not permitted_users:
            logging.info("**No permitted users specified. falling back to allow all")
            return True

        else:
            user_list = permitted_users.split(",")
            logging.debug(f"**Permitted_users: {user_list}")
            if user in user_list:
                logging.info(f'**User "{user}" is permitted to use bot')
                return True
            else:
                logging.info(f'**User "{user}" is not permitted to use bot')
                return False

    def _check_command_authorization(self, cmd_type):
        if cmd_type == "act":
            if self.permit_act:
                logging.info(f'**Command: "{cmd_type}" is permitted')
                return True
            else:
                logging.info(f'**Command:"{cmd_type}" is not permitted')
                return False

        if cmd_type == "run_playbook":
            if self.permit_playbook:
                logging.info(f'**Command: "{cmd_type}" is permitted')
                return True
            else:
                logging.info(f'**Command: "{cmd_type}" is not permitted')
                return False

        if cmd_type == "get_container":
            if self.permit_container:
                logging.info(f'**Command:" {cmd_type}" is permitted')
                return True
            else:
                logging.info(f'**Command: "{cmd_type}" is not permitted')
                return False

        if cmd_type == "list":
            if self.permit_list:
                logging.info(f'**Command: "{cmd_type}" is permitted')
                return True
            else:
                logging.info(f'**Command: "{cmd_type}" is not permitted')
                return False
        else:
            return False

    def _handle_command(self, command, channel):
        try:
            args = shlex.split(command)
        except Exception as e:
            self._post_message(f"Could not parse arguments:\n\n{e}", channel)
            return

        cmd_type = args[0]
        if cmd_type not in ["act", "run_playbook", "get_container", "list"]:
            msg = f"Unknown Command\n\n {SLACK_BOT_HELP_MESSAGE}"
            self._post_message(msg, channel)
            return

        if not self._check_command_authorization(cmd_type):
            msg = SLACK_ERROR_COMMAND_NOT_PERMITTED
            self._post_message(msg, channel)
            return

        if cmd_type == "act":
            logging.info(f"**permit_bot_act: {self.permit_act}")
            status, result = self._parse_action(args[1:])
            if status:
                msg = self._action_run_request(result, channel)
            else:
                msg = result

        elif cmd_type == "run_playbook":
            logging.info(f"**permit_bot_playbook: {self.permit_playbook}")
            status, result = self._parse_playbook(args[1:])
            if status:
                msg = self._playbook_request(result, channel)
            else:
                msg = result

        elif cmd_type == "get_container":
            logging.info(f"**permit_bot_container: {self.permit_container}")
            status, msg = self._parse_container(args[1:])

        elif cmd_type == "list":
            logging.info(f"**permit_bot_list: {self.permit_list}")
            status, msg = self._parse_list(args[1:])

        else:
            msg = SLACK_BOT_HELP_MESSAGE

        self._post_message(msg, channel)


def set_up_logging():
    """Set up logging for the bot."""
    log_file = Path(tempfile.gettempdir()) / "slack.log"
    max_bytes = 5 * 1024 * 1024  # 5MB
    log_formatter = logging.Formatter("[%(process)d][%(asctime)s][%(levelname)s] %(message)s")

    log_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=4)
    log_handler.setFormatter(log_formatter)

    logger = logging.getLogger()
    logger.addHandler(log_handler)
    logger.setLevel(logging.DEBUG)
    return logger


def main():
    """Entry point for running the Slack bot as a script without mutating module globals."""
    set_up_logging()
    logging.info("**Spawning slack_bot.py...")

    if not os.path.exists("./bot_config.py"):
        if len(sys.argv) != 4:
            print("Please create a bot_config.py file, and place it in this directory")
            return 1

        asset_id_arg = sys.argv[1]
        app_id_arg = sys.argv[3]
        state_local = _load_app_state(asset_id_arg)
        bot_id_local = state_local.get("bot_id")
        ph_base_url_local = state_local.get("ph_base_url")
        bot_token_enc = state_local.get(SLACK_JSON_BOT_TOKEN)
        socket_token_enc = state_local.get(SLACK_JSON_SOCKET_TOKEN)
        ph_auth_token_enc = state_local.get(SLACK_JSON_PH_AUTH_TOKEN)
        permit_act_local = state_local.get(SLACK_JSON_PERMIT_BOT_ACT)
        permit_playbook_local = state_local.get(SLACK_JSON_PERMIT_BOT_PLAYBOOK)
        permit_container_local = state_local.get(SLACK_JSON_PERMIT_BOT_CONTAINER)
        permit_list_local = state_local.get(SLACK_JSON_PERMIT_BOT_LIST)
        permitted_users_local = state_local.get(SLACK_JSON_PERMITTED_USERS)

        try:
            if bot_token_enc:
                bot_token_dec = decrypt_state(asset_id_arg, bot_token_enc, "bot")
            else:
                bot_token_dec = None
        except Exception:
            print(SLACK_DECRYPTION_ERROR)
            return 1

        try:
            if socket_token_enc:
                socket_token_dec = decrypt_state(asset_id_arg, socket_token_enc, "socket")
            else:
                socket_token_dec = None
        except Exception:
            print(SLACK_DECRYPTION_ERROR)
            return 1

        try:
            if ph_auth_token_enc:
                ph_auth_token_dec = decrypt_state(asset_id_arg, ph_auth_token_enc, "ph_auth")
            else:
                ph_auth_token_dec = None
        except Exception:
            print(SLACK_DECRYPTION_ERROR)
            return 1

        sb = SlackBot(
            bot_token=bot_token_dec,
            socket_token=socket_token_dec,
            bot_id=bot_id_local,
            base_url=ph_base_url_local,
            auth_token=ph_auth_token_dec,
            permit_act=permit_act_local,
            permit_playbook=permit_playbook_local,
            permit_container=permit_container_local,
            permit_list=permit_list_local,
            permitted_users=permitted_users_local,
            app_id=app_id_arg,
        )
        sb._from_on_poll()
        return 0

    # Local, standalone bot mode using bot_config
    try:
        import bot_config  # type: ignore # pylint: disable=import-error
    except Exception:
        print("Could not import bot_config.py")
        return 1

    fail_local = False

    try:
        app_id_local = bot_config.APP_ID
        if not isinstance(app_id_local, str):
            print("The APP_ID entry in the bot_config file appears to not be a string")
            fail_local = True
    except Exception:
        print("Could not find an APP_ID entry in bot_config file")
        fail_local = True

    try:
        bt = bot_config.BOT_TOKEN
        if not isinstance(bt, str):
            print("The BOT_TOKEN entry in the bot_config file appears to not be a string")
            fail_local = True
    except Exception:
        print("Could not find a BOT_TOKEN entry in bot_config file")
        fail_local = True

    try:
        sat = bot_config.SOCKET_TOKEN
        if not isinstance(sat, str):
            print("The SOCKET_TOKEN entry in the bot_config file appears to not be a string")
            fail_local = True
    except Exception:
        print("Could not find a SOCKET_TOKEN entry in bot_config file")
        fail_local = True

    try:
        pu = bot_config.PHANTOM_URL
        if not isinstance(pu, str):
            print("The PHANTOM_URL entry in the bot_config file appears to not be a string")
            fail_local = True
    except Exception:
        print("Could not find a PHANTOM_URL entry in bot_config file")
        fail_local = True

    try:
        vc = bot_config.VERIFY_CERT
        if not isinstance(vc, bool):
            print("The VERIFY_CERT entry in the bot_config file appears to not be a boolean")
            fail_local = True
    except Exception:
        print("Could not find a VERIFY_CERT entry in bot_config file")
        fail_local = True

    try:
        pt = bot_config.PHANTOM_TOKEN
        has_token = True
        if not isinstance(pt, str):
            print("The PHANTOM_TOKEN entry in the bot_config file appears to not be a string")
            fail_local = True
    except Exception:
        pt = ""
        has_token = False

    try:
        pn = bot_config.PHANTOM_USERNAME
        pp = bot_config.PHANTOM_PASSWORD
        auth = (pn, pp)
        has_basic = True
        if not isinstance(pn, str):
            print("The PHANTOM_USERNAME entry in the bot_config file appears to not be a string")
            fail_local = True
        if not isinstance(pp, str):
            print("The PHANTOM_PASSWORD entry in the bot_config file appears to not be a string")
            fail_local = True
    except Exception:
        auth = ()
        has_basic = False

    if not (has_token or has_basic):
        print(
            "Please specify a form of authorization. Either PHANTOM_TOKEN or PHANTOM_USERNAME and PHANTOM_PASSWORD need to be included in the bot_config file."
        )
        fail_local = True

    try:
        resp = requests.post("https://slack.com/api/auth.test", data={"token": bot_config.BOT_TOKEN}, timeout=SLACK_DEFAULT_TIMEOUT)
        resp_json = resp.json()
    except Exception:
        print("Could not connect to Slack REST endpoint for auth check")
        return 1

    if not resp_json.get("ok", False):
        print("Given BOT_TOKEN failed authentication with Slack")
        fail_local = True

    bot_username = resp_json.get("user_id")

    if not bot_username:
        print("Could not get bot username from Slack")
        fail_local = True

    if fail_local:
        print("Config file failed verification, exiting")
        return 1

    sb = SlackBot(
        bot_token=bot_config.BOT_TOKEN,
        socket_token=bot_config.SOCKET_TOKEN,
        bot_id=bot_username,
        base_url=bot_config.PHANTOM_URL,
        verify=bot_config.VERIFY_CERT,
        auth_token=pt,
        auth_basic=auth,
        app_id=app_id_local,
    )
    sb._from_on_poll()
    return 0


if __name__ == "__main__":
    sys.exit(main())
