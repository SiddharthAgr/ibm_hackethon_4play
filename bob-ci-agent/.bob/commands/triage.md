---
description: Triage a CI pipeline failure by run ID
argument-hint: <run-id>
---
Call run_pipeline with ref=$1. If status is failed, spawn the triage subagent with the failure payload. Show the recommendation and store the result.
