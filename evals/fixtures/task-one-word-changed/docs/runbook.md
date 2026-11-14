# Runbook

Before you start, drain the queue and confirm that no jobs are running.

Rotate the signing keys first; after that, restart the workers one at a time so that the
dashboard never shows fewer than two healthy nodes during the rollout.

Finally, record the new key fingerprint in the audit log.
