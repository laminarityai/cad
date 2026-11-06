# The MCP server is the product; the web app is its first client

Every capability (making variants, running checks, reading tables and the knowledge base, exporting to Onshape) is a tool on one MCP server, and our own web app's agent reaches it through the same MCP interface as Claude Code or any other client, with no private shortcuts. We chose this so the trust boundary sits in one place: checks run server-side, so any agent that connects can do the engineering but cannot grade its own work. It also lets us design through Claude Code before the web app exists.

## Consequences

Modes and Auto mode's stopping rules are agent behavior, so we can ship them as guidance alongside the server but cannot enforce them on outside clients; only the checks are guaranteed. Outside clients mostly cannot show a 3D view, so tools return rendered images and a link to the viewer. Running FEA for anyone who connects means accounts and usage limits are part of the server, not the web app.
