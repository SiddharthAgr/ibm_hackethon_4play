# /triage

**Description:** Trigger the CI pipeline and triage failures for a specific run ID.

**Usage:** `/triage <run-id>`

## Instructions for Bob
When the user invokes this command with a `<run-id>`, you must execute the following workflow:
1. Invoke the `run_pipeline` tool via the MCP server using the provided `<run-id>`.
2. Wait for the pipeline tool to return the execution payload.
3. If the payload indicates a pipeline failure, you must immediately hand off the structured failure payload to the **Triage Subagent**.
4. Do not attempt to mutate or fix the code yourself; rely entirely on the Triage Subagent's output.