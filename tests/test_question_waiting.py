# Copyright (c) 2016-2026 Splunk Inc.

"""Exercise the real action with a simulated clock and SOAR platform interfaces."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest  # pylint: disable=import-error


class ActionResult:
    def __init__(self, param):
        self.param = param
        self.status = 0
        self.message = ""
        self.summary = {}
        self.data = []

    def set_status(self, status, message=""):
        self.status = status
        self.message = message
        return status

    def get_status(self):
        return self.status

    def set_summary(self, summary):
        self.summary = summary

    def add_data(self, data):
        self.data.append(data)


@pytest.fixture
def waiting(monkeypatch, tmp_path):
    # These interfaces are supplied by SOAR in production. Keep the polling tests
    # runnable without installing the platform or invoking any external services.
    platform = ModuleType("phantom.app")
    platform.BaseConnector = object
    platform.ActionResult = ActionResult
    platform.APP_SUCCESS = 0
    platform.APP_ERROR = -1
    platform.is_fail = lambda status: status == -1
    phantom_package = ModuleType("phantom")
    phantom_package.app = platform
    rules = ModuleType("phantom.rules")
    phantom_package.rules = rules
    base_connector = ModuleType("phantom.base_connector")
    base_connector.APPS_STATE_PATH = str(tmp_path)
    django_http = ModuleType("django.http")
    django_http.HttpResponse = Mock()
    bs4 = ModuleType("bs4")
    bs4.BeautifulSoup = Mock()
    bs4.UnicodeDammit = Mock()
    requests = ModuleType("requests")
    requests.get = Mock()
    for name, module in {
        "phantom": phantom_package,
        "phantom.app": platform,
        "phantom.rules": rules,
        "phantom.base_connector": base_connector,
        "encryption_helper": ModuleType("encryption_helper"),
        "django": ModuleType("django"),
        "django.http": django_http,
        "bs4": bs4,
        "sh": ModuleType("sh"),
        "requests": requests,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    repo = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(repo))
    spec = importlib.util.spec_from_file_location("slack_question_waiting_test", repo / "slack_connector.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    connector = module.SlackConnector()
    connector._timeout = 10
    connector._interval = 30
    connector.get_action_identifier = Mock(return_value="ask_question")
    connector.debug_print = Mock()
    connector._get_error_message_from_exception = str
    results = []

    def add_result(result):
        results.append(result)
        return result

    connector.add_action_result = add_result
    qid = "a" * 32
    answer_path = tmp_path / f"{qid}.json"
    metadata_path = tmp_path / f"{qid}_question.json"
    metadata_path.write_text("{}")
    connector._handle_ask_question = Mock(return_value=(0, {"qid": qid, "answer_path": str(answer_path)}))
    clock = SimpleNamespace(now=0, sleeps=[], progress=[], polls=[], reply_at=None)
    payload = {"actions": [{"value": "yes"}], "user": {"id": "U123"}}

    def progress(message):
        clock.progress.append(clock.now)

    def sleep(seconds):
        assert 0 < seconds <= 60, "A blocking sleep must not suppress progress for more than 60 seconds"
        assert clock.now - clock.progress[-1] < 300, "The connector exceeded the IPC inactivity timeout"
        clock.sleeps.append(seconds)
        clock.now += seconds
        if clock.reply_at is not None and clock.now >= clock.reply_at and not answer_path.exists():
            answer_path.write_text(json.dumps({"payloads": [payload]}))

    real_open = open

    def read_answer(path, *args, **kwargs):
        clock.polls.append(clock.now)
        return real_open(path, *args, **kwargs)

    connector.save_progress = Mock(side_effect=progress)
    monkeypatch.setattr(module.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(module.time, "sleep", sleep)
    monkeypatch.setattr(module, "open", read_answer, raising=False)
    return SimpleNamespace(
        module=module,
        connector=connector,
        clock=clock,
        results=results,
        answer_path=answer_path,
        metadata_path=metadata_path,
        payload=payload,
        qid=qid,
        param={"destination": "U123", "question": "Proceed?"},
    )


def assert_live_until_completion(waiting):
    times = [*waiting.clock.progress, waiting.clock.now]
    assert max(later - earlier for earlier, later in zip(times, times[1:])) <= 60


def test_answer_after_six_minutes_succeeds(waiting):
    waiting.clock.reply_at = 360

    assert waiting.connector._ask_question(waiting.param) == 0

    assert waiting.clock.now == 360
    assert waiting.results[0].summary == {"response_received": True, "question_id": waiting.qid, "response": "yes"}
    assert waiting.results[0].data == [waiting.payload]
    assert not waiting.answer_path.exists()
    assert not waiting.metadata_path.exists()
    assert_live_until_completion(waiting)


@pytest.mark.parametrize("interval", [30, 301, 900])
def test_five_hour_unanswered_question_succeeds_at_full_timeout(waiting, interval):
    waiting.connector._timeout = 300
    waiting.connector._interval = interval

    assert waiting.connector._ask_question(waiting.param) == 0

    assert waiting.clock.now == 18000
    assert waiting.results[0].summary == {"response_received": False, "question_id": waiting.qid}
    assert waiting.results[0].data == []
    assert not waiting.metadata_path.exists()
    assert waiting.connector._interval == interval
    assert_live_until_completion(waiting)


@pytest.mark.parametrize("timeout,interval,expected_polls", [(1, 17, [0, 17, 34, 51, 60]), (1, 900, [0, 60])])
def test_timeout_is_not_rounded_down_or_exceeded(waiting, timeout, interval, expected_polls):
    waiting.connector._timeout = timeout
    waiting.connector._interval = interval

    assert waiting.connector._ask_question(waiting.param) == 0

    assert waiting.clock.polls == expected_polls
    assert waiting.clock.now == timeout * 60
    assert_live_until_completion(waiting)


def test_long_polling_interval_keeps_progress_without_polling_more_often(waiting):
    waiting.connector._timeout = 20
    waiting.connector._interval = 900
    waiting.clock.reply_at = 360

    assert waiting.connector._ask_question(waiting.param) == 0

    assert waiting.clock.polls == [0, 900]
    assert waiting.results[0].summary["response_received"] is True
    assert_live_until_completion(waiting)


@pytest.mark.parametrize("reply_at", [0, 60])
def test_immediate_or_final_interval_answer_is_not_lost(waiting, reply_at):
    waiting.connector._timeout = 1
    waiting.clock.reply_at = reply_at
    if reply_at == 0:
        waiting.answer_path.write_text(json.dumps({"payloads": [waiting.payload]}))

    assert waiting.connector._ask_question(waiting.param) == 0

    assert waiting.clock.now == reply_at
    assert waiting.results[0].summary["response_received"] is True


def test_late_answer_does_not_extend_timeout(waiting):
    waiting.connector._timeout = 1
    waiting.clock.reply_at = 61

    assert waiting.connector._ask_question(waiting.param) == 0

    assert waiting.clock.now == 60
    assert waiting.results[0].summary["response_received"] is False


def test_malformed_answer_is_still_an_error(waiting):
    waiting.answer_path.write_text("not json")

    assert waiting.connector._ask_question(waiting.param) == -1

    assert waiting.results[0].message == waiting.module.SLACK_ERROR_UNABLE_TO_PARSE_RESPONSE
    assert waiting.clock.sleeps == []


def test_unreadable_answer_is_an_error_not_an_unanswered_timeout(waiting, monkeypatch):
    monkeypatch.setattr(waiting.module, "open", Mock(side_effect=PermissionError("Permission denied")))

    assert waiting.connector._ask_question(waiting.param) == -1

    assert waiting.results[0].message == "Unable to read question response"
    assert waiting.clock.sleeps == []


def test_post_failure_is_still_an_error(waiting):
    def fail_post(result, *args):
        return result.set_status(-1, "Unable to send question"), None

    waiting.connector._handle_ask_question.side_effect = fail_post

    assert waiting.connector._ask_question(waiting.param) == -1

    assert waiting.results[0].message == "Unable to send question"
    assert waiting.clock.sleeps == []
