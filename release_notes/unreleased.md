**Unreleased**

* Added **ask question channel with blocks** action. Posts a channel question whose message body is rendered from caller-supplied Block Kit `blocks` (same JSON format as `send message`) and returns a question ID that `get response` can retrieve.
* If the blocks already contain a `type: actions` block, each button's `action_id` becomes a valid response choice and the actions block is tagged with `block_id = soar_qid:<qid>:<asset_id>` so clicks correlate back to the pending question. Additional actions blocks get a numeric suffix so each block ID is unique.
* If the blocks do not contain an actions block, one is appended with Block Kit buttons derived from the `responses` parameter (defaults to `yes,no`).
* In Socket Mode, `replace_on_response` updates the posted message after a click by removing every actions block and showing the response and responder. Set it to `false` to keep the buttons. In Interactivity Request URL mode, the answer is saved for `get response`, but the buttons remain visible.
* Clicks are routed through either Socket Mode (`slack_bot.block_actions_handler`) or the Interactivity Request URL (`handle_request`'s new `block_actions` branch). Both paths validate the click against the pending question's choices and write the answer file consumed by `get response`.
