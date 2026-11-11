"""The errors a route or a tool answers with. Derive a feature's exception from one of these and
the HTTP routes and the MCP tools report it; an exception that derives from none propagates.

`cad.operations.routes.refusal` turns one into its HTTP response and
`cad.operations.tools.agent_facing` into the agent's tool error.
"""


class Refused(Exception):
    """The request is understood and will not be done: HTTP 400, named in the tool error."""


class NotFound(Refused):
    """The request names something that does not exist: HTTP 404, named in the tool error."""


class Unavailable(Exception):
    """The server cannot do it now: HTTP 503, and the tool error is the message alone."""
