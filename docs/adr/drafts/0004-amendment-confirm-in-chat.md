<!-- DRAFT on proto/project-workspace for the operator's review. Not on main. It becomes an
amendment at the end of docs/adr/0004-a-person-confirms-on-a-local-page-not-through-mcp-elicitation.md
only after the operator approves it. -->

## Amendment (draft, 2026-11-10): the person confirms in the chat

The person works in one place, the project workspace. Its chat is where they say what they want. Sending them to a separate confirmation page breaks that, and the friction walk of 2026-11-10 found that the person then came back and typed "I confirmed", 4 times out of 4 (#203). This amendment moves the page into the chat (#196). The rules of this ADR do not change. Only the person can answer. Only a request handler for a signed-in person writes the answer. The projects key signs each `PageAnswer`, and status is derived from signed records.

### The page draws the card, not the agent

When something waits on the person in the project, the web app draws a confirmation card in the chat from `GET /v1/projects/{project_id}/waiting`. Agent text never draws it. The agent's words cannot add a row, change a row or press a button. Each row shows what will be checked in plain words and the brief words it was taken from. A context part shows by its name. A row starts as accepted. The person can decline a row, or edit its text, which declines that row with a note that the agent reads before it proposes again. One press of Confirm answers every row.

The material is not a row. When the brief names no material, the agent chooses one (#200), and the workspace labels it "chosen by the agent". The person changes it by saying so in the chat.

### The answer is the same signed record

Confirm posts to the same person-only handler as the page, with the same CSRF token bound to the card's snapshot. An item added or replaced after the card was drawn records nothing, and the card redraws. `PageAnswer` is unchanged. It records the account, the session and each row's answer. No MCP tool answers it, and no agent token is accepted on the handler.

### The agent carries on by itself

Recording an answer starts the conversation's next turn, with the answer as a driver event, so the person types nothing (#203). Once a brief's requirements are confirmed, the server moves the conversation out of planning. The person never chooses a mode. The confirmation answer flow stays model-checked by the `protocol models` step.

### Outside clients

An MCP client other than the web app still gets URL-mode elicitation, or "waiting in the web app", as the 2026-11-08 amendment says. Its URL opens the project's workspace with the card in the chat. The standalone page at `/projects/<pid>/confirm` stays as a fallback until the card ships, then redirects to the workspace.

### The guarantee and its gap

They are unchanged. An agent that reaches the server only through MCP cannot answer the card. A process that drives the person's signed-in browser could still press Confirm, which this ADR already accepts.

### Considered options

- **Keep the separate page and link to it from the chat.** It changes nothing in the guarantee, but the person leaves the conversation and has to come back and say they confirmed.
- **Let the agent render the confirmation as Markdown with buttons.** Rejected. Then the agent's text would decide which rows the person sees, and a row could say something different from what the check reads.
