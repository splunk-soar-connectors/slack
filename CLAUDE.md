# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Splunk SOAR connector for Slack. Integrates with the Splunk SOAR (Security Orchestration, Automation, and Response) platform to enable Slack messaging, bot interaction, and file operations from SOAR playbooks.

## Development Commands

### Linting and Static Analysis
```bash
# Run all pre-commit hooks on staged files
pre-commit run

# Run on all files
pre-commit run --all-files

# Run a specific hook
pre-commit run ruff --all-files
pre-commit run ruff-format --all-files
pre-commit run semgrep --all-files
```

### Local Testing
The connector accepts a JSON test file via stdin when run directly:
```bash
python slack_connector.py < test_input.json
```

Test input JSON must follow the Phantom action input format with `config` and `parameters` keys.

## Architecture

### Two-Process Design
The connector runs in two distinct modes:

1. **`slack_connector.py`** — Standard synchronous SOAR connector. Handles all actions except polling. Runs in the SOAR process and returns results immediately.

2. **`slack_bot.py`** — Long-running subprocess spawned by the `on_poll` action. Uses `slack_bolt` with Socket Mode for real-time event delivery. The PID is stored in the app state file so the parent connector can manage its lifecycle. The bot process handles `act`, `run_playbook`, `get_container`, and `list` commands from Slack users.

### Action Handler Pattern
All actions follow this structure:
```python
def _handle_action_name(self, param):
    action_result = self.add_action_result(phantom.ActionResult(dict(param)))
    # ... implementation using self._make_slack_rest_call()
    return action_result.set_status(phantom.APP_SUCCESS, message)
```

`handle_action()` in `slack_connector.py` dispatches to handlers based on `self.get_action_identifier()`.

### Webhook Callback Flow
The `handle_request()` function (called by SOAR's REST infrastructure, not `handle_action`) processes interactive payload callbacks from Slack. It uses `callback_id` (JSON-encoded `{asset_id, qid}`) for routing and verifies the `verification_token` as CSRF protection. Responses are written to files in `APPS_STATE_PATH` keyed by asset ID and question ID.

### State and Token Encryption
- State is persisted as JSON at `{APPS_STATE_PATH}/{asset_id}_state.json`
- Bot/user/socket tokens are encrypted at rest via `encryption_helper` (Phantom-provided)
- `initialize()` decrypts tokens; `finalize()` re-encrypts before saving

### REST Call Helpers
- `_make_slack_rest_call()` — POST to Slack API with bot token; handles Slack-specific error responses (checks `ok` field in response JSON)
- `_make_rest_call()` — Generic call for user-token operations; used by `upload_file` and `create_channel`

### File Upload (v2.9.x+)
Uses the newer Slack API flow: `files.getUploadURLExternal` → upload to returned URL → `files.completeUploadExternal`. The legacy `files.upload` endpoint was deprecated.

## Key Constants (`slack_consts.py`)

All Slack API endpoint paths, action IDs, error message strings, and limits are defined in `slack_consts.py`. When adding new API calls or actions, add constants here rather than using inline strings.

Notable limits:
- `SLACK_MESSAGE_LIMIT = 40000` characters
- `SLACK_CONFIRMATION_MSG_LIMIT = 174` characters
- Default question timeout: 30 minutes
- Default poll interval: 30 seconds

## Linting Rules (pyproject.toml)
- **Line length**: 145 characters
- **Target Python**: 3.9 (also tested on 3.13)
- **Quote style**: Double quotes
- **Ignored rules**: RUF012, RUF001, C901 (complexity)
- **Max McCabe complexity**: 28
- Ruff handles both linting and formatting; do not add `# noqa` without checking whether the rule can be fixed

## Dependency Management
Dependencies are vendored in `wheels/` for SOAR deployment. When adding or upgrading a dependency, the pre-commit hook `package-app-dependencies` from `dev-cicd-tools` regenerates this directory. Do not edit `wheels/` manually.

## Release and CI
Merging to `main` automatically triggers the GitHub Actions workflow (`.github/workflows/call-publish.yml`) which publishes to SplunkBase. Release notes for each version must exist in `release_notes/` (validated by pre-commit) before merging.

## Contributing via Pull Request

See [`SPLUNK_SOAR_CONTRIBUTING.md`](./SPLUNK_SOAR_CONTRIBUTING.md) for the full process. Key points specific to this repo:

- Always branch off `upstream/main` (`git remote add upstream https://github.com/splunk-soar-connectors/slack.git`), not your fork's main
- Check `"app_version"` in `slack.json` on upstream to determine the correct next version before starting
- `pre-commit run --all-files` must pass before opening the PR — this validates linting, release notes, Python 3.13 compat, and more
- The PR must check **"Allow edits and access to secrets by maintainers"** — Splunk requires this explicitly
- One issue per PR; do not bundle unrelated fixes
