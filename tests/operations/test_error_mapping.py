import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Final

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.testclient import TestClient

import cad
from cad.accounts.principal import AccountId, PersonSession
from cad.confirmations.waiting import Door
from cad.context_parts.ingest import ingest
from cad.operations.model import Audience, Input, Tenant, operation
from cad.operations.routes import Served, person_route
from cad.operations.tenants import open_tenant
from cad.operations.tools import agent_facing
from cad.records.roots import Roots

type Answer = tuple[str | None, str | None]

# For every exception class cad defines: the HTTP status and message form a route answers with,
# and the form of the agent's tool error. None means the exception is not mapped and propagates.
EXPECTED: Final[dict[str, Answer]] = {
    "cad.accounts.clerk.ClerkMisconfigured": (None, None),
    "cad.accounts.lease.LeaseHeld": (None, None),
    "cad.accounts.principal.NotAnAccount": (None, None),
    "cad.agent_measurements.run.MeasurementRefused": ("400 named", "named"),
    "cad.auto.model.RunNotHeld": ("400 named", "named"),
    "cad.auto.model.RunRefused": ("400 named", "named"),
    "cad.auto.model.RunStopped": ("400 named", "named"),
    "cad.auto.model.TamperedRun": ("400 named", "named"),
    "cad.auto.model.UnknownRun": ("404 named", "named"),
    "cad.briefs.edits._Unreadable": (None, None),
    "cad.briefs.source.WordsRefused": ("400 named", "named"),
    "cad.briefs.store.BadProposal": ("400 named", "named"),
    "cad.briefs.store.BriefRefused": ("400 named", "named"),
    "cad.briefs.store.TamperedBrief": ("400 named", "named"),
    "cad.briefs.store.UnknownBrief": ("404 named", "named"),
    "cad.chat.model.ModelUnavailable": (None, None),
    "cad.checks.container.inputs.Undeclared": (None, None),
    "cad.checks.lanes.Superseded": (None, None),
    "cad.context_parts.store.BadContextPart": ("400 named", "named"),
    "cad.conversations.model.ModeRefused": ("400 named", "named"),
    "cad.conversations.model.NotAConversation": (None, None),
    "cad.conversations.model.UnknownConversation": ("404 named", "named"),
    "cad.errors.NotFound": ("404 named", "named"),
    "cad.errors.Refused": ("400 named", "named"),
    "cad.errors.Unavailable": ("503 plain", "plain"),
    "cad.geometry.exports.model.UnknownExport": ("404 named", "named"),
    "cad.geometry.model.UnknownMesh": ("404 named", "named"),
    "cad.knowledge.corpus.InvalidCorpus": (None, None),
    "cad.projects.model.ProjectBusy": ("400 named", "named"),
    "cad.projects.model.ProjectRefused": ("400 named", "named"),
    "cad.projects.model.TamperedProject": ("400 named", "named"),
    "cad.projects.model.UnknownProject": ("404 named", "named"),
    "cad.records.signed.Contended": (None, None),
    "cad.records.signed.StoreUnusable": ("503 plain", "plain"),
    "cad.records.signed.Tampered": (None, None),
    "cad.research.fetch._Refused": (None, None),
    "cad.sandbox.meter.AccountLimitReached": ("503 plain", "plain"),
    "cad.sandbox.meter.NoMeter": (None, None),
    "cad.sandbox.outcome.SandboxUnavailable": ("503 plain", "plain"),
    "cad.scorecard.material.MaterialPinned": ("400 named", "named"),
    "cad.scorecard.requirements.NoDecidingResult": (None, None),
    "cad.scorecard.score.NotScored": ("400 named", "named"),
    "cad.selections.model.SelectionRefused": ("400 named", "named"),
    "cad.selections.model.UnknownSelection": ("400 named", "named"),
    "cad.tables.fasteners.UnknownFastener": (None, None),
    "cad.tables.materials.InvalidTable": (None, None),
    "cad.tables.materials.UnknownMaterial": (None, None),
    "cad.variant_sets.model.MaterialMissing": ("400 named", "named"),
    "cad.variant_sets.model.SetBusy": ("400 named", "named"),
    "cad.variant_sets.model.SetFull": ("400 named", "named"),
    "cad.variant_sets.model.SetRefused": ("400 named", "named"),
    "cad.variant_sets.model.SlotRefused": ("400 named", "named"),
    "cad.variant_sets.model.TamperedSet": ("400 named", "named"),
    "cad.variants.entry.NotBuilt": ("400 named", "named"),
    "cad.variants.entry.OutdatedVariant": ("400 named", "named"),
    "cad.variants.entry.StaleVariant": ("400 named", "named"),
    "cad.variants.entry.UnknownVariant": ("404 named", "named"),
    "cad.variants.entry.VariantRefused": ("400 named", "named"),
    "cad.variants.store.RebuildFailed": ("400 named", "named"),
}


def defined_in_cad() -> dict[str, type[BaseException]]:
    found: dict[str, type[BaseException]] = {}
    for module in pkgutil.walk_packages(cad.__path__, "cad."):
        for value in vars(importlib.import_module(module.name)).values():
            if (
                inspect.isclass(value)
                and issubclass(value, BaseException)
                and value.__module__ == module.name
            ):
                found[f"{value.__module__}.{value.__qualname__}"] = value
    return found


def an_instance(kind: type[BaseException]) -> BaseException:
    error = kind.__new__(kind)
    error.args = ("why",)
    return error


def form(message: str, error: BaseException) -> str:
    if message == f"{type(error).__name__}: {error}":
        return "named"
    return "plain" if message == str(error) else f"unexpected: {message}"


class Nothing(Input):
    pass


class Never(BaseModel):
    pass


class Raising:
    """A person route whose operation raises whatever `error` holds when it is called."""

    def __init__(self, tmp_path: Path) -> None:
        self.error: BaseException = Exception()
        account = AccountId("user_alice")
        roots = Roots(briefs=tmp_path / "briefs", projects=tmp_path / "projects")
        tenant = open_tenant(
            account, roots, tmp_path / "variants", tmp_path / "geometry", None, Door(), ingest
        )
        one = operation(
            name="raise",
            audience=Audience.PERSON,
            description="raises",
            input=Nothing,
            output=Never,
            run=self._run,
        )
        route = person_route(
            Served("/raise"),
            one,
            lambda _token: PersonSession(account=account, session_id="s"),
            lambda _account: tenant,
        )
        self.client = TestClient(Starlette(routes=[route]))

    def _run(self, tenant: Tenant, arguments: Nothing) -> Never:
        del tenant, arguments
        raise self.error

    def over_http(self, error: BaseException) -> str | None:
        self.error = error
        try:
            answer = self.client.get("/raise")
        except BaseException:
            return None
        return f"{answer.status_code} {form(answer.json()['error'], error)}"


def to_the_agent(error: BaseException) -> str | None:
    try:
        with agent_facing():
            raise error
    except ToolError as refused:
        return form(str(refused), error)
    except BaseException:
        return None


def test_every_exception_maps_to_the_status_and_tool_error_it_always_has(tmp_path: Path) -> None:
    route = Raising(tmp_path)
    answers = {
        name: (route.over_http(an_instance(kind)), to_the_agent(an_instance(kind)))
        for name, kind in defined_in_cad().items()
    }
    assert answers == EXPECTED
