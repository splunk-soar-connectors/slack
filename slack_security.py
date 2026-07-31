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


def sanitize_slack_markup(value: str) -> str:
    """Unwrap Slack links while guaranteeing progress on malformed input."""
    while (left_index := value.find("<")) != -1:
        right_index = value.find(">", left_index + 1)
        if right_index == -1:
            break
        pipe_index = value.find("|", left_index + 1, right_index)
        start_index = pipe_index + 1 if pipe_index != -1 else left_index + 1
        replacement = value[start_index:right_index]
        value = value[:left_index] + replacement + value[right_index + 1 :]
    return value
