---
id: pm-2026-031-flag-misconfig
title: Postmortem 2026-031: Bad flag default took down search
kind: postmortem
team: platform
acl: eng
version: 1
---
# Postmortem 2026-031: Bad flag default took down search

Severity: SEV2.

## Summary
A new flag shipped with default on in production instead of off and enabled an unfinished search backend.

## Root cause
The flag service had no environment-specific defaults review.

## Action items
Require two-person review for production flag defaults. The kill switch worked and restored service in 6 minutes.
