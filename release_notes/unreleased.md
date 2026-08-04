**Unreleased**

* Preserve backslashes and Unicode text verbatim when sending Slack messages.
* Encode email lookup values as a single Slack API query parameter.
* Return clean action errors for non-object Slack JSON responses.
* Treat non-2xx or unsuccessful Slack JSON responses as action failures.
* Bound Slack cursor pagination when responses repeat or stop making progress.
