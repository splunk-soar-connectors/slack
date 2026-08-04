**Unreleased**

* Preserve backslashes and Unicode text verbatim when sending Slack messages.
* Encode email lookup values as a single Slack API query parameter.
* Return clean action errors for non-object Slack JSON responses.
* Treat non-2xx or unsuccessful Slack JSON responses as action failures.
* Bound Slack cursor pagination when responses repeat or stop making progress.
* Retrieve all cursor-paginated channel and thread messages in get history.
* Return clean action errors when ask-question callback metadata exceeds Slack's limit.
* Stop and restart only the Slack bot process belonging to the current asset.
