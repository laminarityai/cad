# Chat and mode switcher (NOT YET BUILT)

The person chats with our own agent in the web app. The agent runs in the server process and reaches the MCP tools through the in-memory transport, with an `AgentToken` built per turn from the person's session. A change asked for in chat becomes the slot's next revision, and the viewer and scorecard update without a reload. The person switches between Plan, Design and Auto mode. `set_mode` is a person-only operation.

Design: `docs/design/phase-4.md` §1a, §2.2 (a change asked for in chat), §2.4 (our own chat agent needs no Clerk token) and §2.5 (modes are conversation state). Unit 8 of §4, the first phase 4 exit.

## The check §4 gives unit 8

- Playwright asks in chat for a change to a variant, and the viewer and scorecard update to the slot's new revision without a reload. The time to the new mesh is printed and not gated. A video is attached.
- A headless scripted-model run goes through Plan, Design and Auto mode.

## Proof to write when it lands

- A Playwright recipe on the one-Chromium daemon: sign in locally, type "make the wall 4 mm" for a built variant, and wait on the same page for the slot's revision number, the viewer and the scorecard to change. Record a video (Playwright's `record_video_dir` on the context) and the printed time to the new mesh. Cost: live + docker + browser.
- Under Plan mode, show `build_variant` refused for that conversation, and `auto_start` refused under a token whose mode is not Auto.
- The headless scripted-model run replaces `claude_session.py` for the in-process agent, because that agent is not a Claude Code session. Write its driver with the unit.

## Until then

The agent is an outside MCP client. [Test mode](../test-mode.md) and the live recipes in each feature file prove what it does.
