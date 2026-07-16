**Unreleased**

* Reject get response question IDs that resolve outside the Slack app state directory.
* Verify TLS certificates for direct Slack Web API requests used to create channels, look up users, and invite users.
* Encrypt Slack credential fields before any mid-action connector state write.
* Bound Slack channel and user name-resolution pagination and reject repeated cursors.
