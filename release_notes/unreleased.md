**Unreleased**

* Added the optional `allow_missing_response` parameter to the `get response` action. When enabled, the action succeeds with `response_received` set to false if the question has not been answered yet, instead of failing. If the question can no longer be answered (expired, timed out, or an unknown question ID), the action still fails. Defaults to false, so existing behavior is unchanged.
* Added the `expire question channel with blocks` action. It closes an unanswered question asked with `ask question channel with blocks`: it marks the question expired so later clicks are rejected, then edits the posted message to remove the buttons and show a timeout message. The question metadata is removed only after the edit succeeds, so a failed edit can be retried. If the question was already answered, the message is left unchanged.
* `get response` now fills `summary.question_id` and `summary.response` when a response is available.
* `ask question channel with blocks` now also stores `message_ts` and the posted `blocks` in the question metadata, for use by `expire question channel with blocks`.
