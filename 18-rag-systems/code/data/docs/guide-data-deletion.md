---
id: guide-data-deletion
title: Handling data deletion requests
kind: guide
team: data
acl: eng
version: 2
---
# Handling data deletion requests

## Scope
A data-subject deletion request must be completed within 30 days across every store that holds the person's data: databases, the warehouse, backups on their normal expiry, search indexes, caches and embedding stores.

## Procedure
File the request in the privacy tracker. Each store owner confirms deletion. Derived copies count: a search index or vector store that holds a chunk of the person's data must delete it too.
