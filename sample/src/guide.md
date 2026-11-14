# Deployment Guide

Always run the migration script before restarting the
service; otherwise the cache will hold stale schema
entries for up to ten min-
utes.

The “safe mode” flag disables background workers — it does not
disable the HTTP API.
