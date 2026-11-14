import hashlib
import threading

import httpx2
import pytest
from starlette.applications import Starlette

from cad.accounts.local import LocalIssuer
from cad.accounts.principal import AccountId
from cad.geometry.exports import job, store
from cad.geometry.exports.lane import Exports
from cad.geometry.exports.model import Exported, ExportFailed
from cad.operations import exports
from cad.operations.briefs import (
    CreateBriefInput,
    ProposeRequirementsInput,
    RequirementDraft,
    create_brief,
    propose_requirements,
)
from cad.operations.confirmation import AskToConfirmInput, ask_to_confirm
from cad.operations.model import Download, Tenant
from cad.operations.tenants import Tenants
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Areas, Build, Built
from cad.variant_sets import store as variant_sets
from cad.variant_sets.model import Option
from cad.variants import entry
from tests.support.hosted import BASE

pytestmark = pytest.mark.anyio

ALICE, BOB = AccountId("user_alice"), AccountId("user_bob")
BREP = b"CASCADE Topology V3, a rail\n"
SHA = hashlib.sha256(BREP).hexdigest()
MADE = job.Made(step=b"ISO-10303-21;\n", stl=b"binary stl", threemf=b"PK zip")
EXPORTED = job.Ran(Exported(key=SHA, version=job.VERSION), True, MADE)
FORMATS = ("step", "stl", "3mf")
UNDER_150 = RequirementDraft.model_validate(
    {
        "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
        "quote": "under 150 g",
    }
)


def url(format: str, name: str | None = None) -> str:
    asked = "" if name is None else f"?name={name}"
    return f"/v1/exports/{job.VERSION}/{SHA}.{format}{asked}"


def client(app: Starlette, local: LocalIssuer, account: str) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url=BASE,
        cookies={"__session": local.mint_person(account)},
    )


class Gated:
    def __init__(self, ran: job.Ran) -> None:
        self.ran = ran
        self.calls = 0
        self.gate = threading.Event()

    def __call__(self, brep: bytes, key: str, areas: Areas) -> job.Ran:
        assert (brep, key, areas) == (BREP, SHA, ())
        self.calls += 1
        self.gate.wait(5)
        return self.ran


async def a_confirmed_set(tenant: Tenant, name: str | None) -> tuple[str, str, str]:
    """A confirmed brief with one built option, in slot 1, built twice: (brief, first, second)."""
    created = create_brief(tenant, CreateBriefInput(text="A plate under 150 g", name=name))
    propose_requirements(
        tenant, ProposeRequirementsInput(brief_id=created.brief_id, requirements=[UNDER_150])
    )
    answer = await ask_to_confirm(tenant, AskToConfirmInput(project_id=created.project_id))
    assert answer.status == "answered"
    key = variant_sets.set_key(tenant.roots, created.brief_id)
    ids: list[str] = []
    for code in ("result = 1", "result = 2"):
        vid = entry.variant_id(code, image_tag(BUILD))
        entry.save(tenant.variants, vid, code, Build(outcome=Built(), output=""), BREP)
        option = Option(label="Wide base!", differs="a wider foot")
        variant_sets.join(tenant.roots.projects, key, code, entry.VariantId(vid), 1, option=option)
        ids.append(vid)
    return created.brief_id, ids[0], ids[1]


async def test_each_format_is_sent_from_the_store_under_the_name_in_the_url(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    store.write(tenants.of(ALICE).geometry, EXPORTED)
    async with client(app, local, "user_alice") as http:
        sent = {one: await http.get(url(one, "desk-box-wide-base-rev2")) for one in FORMATS}
    assert {one: r.content for one, r in sent.items()} == {
        "step": MADE.step,
        "stl": MADE.stl,
        "3mf": MADE.threemf,
    }
    assert sent["3mf"].headers["Content-Disposition"] == (
        'attachment; filename="desk-box-wide-base-rev2.3mf"'
    )
    assert "immutable" in sent["stl"].headers["Cache-Control"]


async def test_an_unnamed_download_is_called_part_and_a_name_is_cleaned_to_one_the_header_keeps(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    store.write(tenants.of(ALICE).geometry, EXPORTED)
    async with client(app, local, "user_alice") as http:
        plain = await http.get(url("stl"))
        odd = await http.get(url("stl", "%22%0d%0aX:%20Y%20Desk%20Box"))
    assert plain.headers["Content-Disposition"] == 'attachment; filename="part.stl"'
    assert odd.headers["Content-Disposition"] == 'attachment; filename="x-y-desk-box.stl"'


async def test_a_file_not_exported_failed_stale_or_another_accounts_is_404_and_never_immutable(
    app: Starlette, local: LocalIssuer, tenants: Tenants, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with client(app, local, "user_alice") as mine:
        missing = await mine.get(url("step"))
        store.write(
            tenants.of(ALICE).geometry,
            job.Ran(ExportFailed(key=SHA, version=job.VERSION, reason="x"), True),
        )
        failed = await mine.get(url("step"))
        store.write(tenants.of(ALICE).geometry, EXPORTED)
        old = url("step")
        monkeypatch.setattr(job, "VERSION", "b" * 12)
        stale = await mine.get(old)
        malformed = await mine.get(f"/v1/exports/{job.VERSION}/{SHA}.obj")
    async with client(app, local, "user_bob") as theirs:
        other = await theirs.get(url("step"))
    assert [one.status_code for one in (missing, failed, stale, other)] == [404] * 4
    assert all("Cache-Control" not in one.headers for one in (missing, failed, stale, other))
    assert malformed.status_code == 422


async def test_an_agent_token_cannot_download(app: Starlette, local: LocalIssuer) -> None:
    transport = httpx2.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {local.mint_agent('user_alice')}"}
    async with httpx2.AsyncClient(transport=transport, base_url=BASE, headers=headers) as http:
        refused = [
            await http.get(url("step")),
            await http.get("/v1/variants/0123456789abcdef/exports/step?brief_id=x"),
        ]
    assert [one.status_code for one in refused] == [401, 401]


async def test_an_export_is_pending_then_ready_with_the_name_the_page_shows(
    confirming_tenants: Tenants, monkeypatch: pytest.MonkeyPatch
) -> None:
    alice = confirming_tenants.of(ALICE)
    brief, first, second = await a_confirmed_set(alice, "  Desk box ")
    run = Gated(EXPORTED)
    monkeypatch.setattr(exports, "EXPORTS", Exports(run))
    asked = exports.ExportInput(variant_id=second, brief_id=brief, format="stl")
    assert exports.export(alice, asked) == exports.ExportPreparing()
    assert exports.export(alice, asked) == exports.ExportPreparing()
    run.gate.set()
    ready: exports.ExportView = exports.ExportPreparing()
    for _ in range(100):
        ready = exports.export(alice, asked)
        if ready != exports.ExportPreparing():
            break
        threading.Event().wait(0.05)
    assert ready == exports.ExportReady(
        url=f"/v1/exports/{job.VERSION}/{SHA}.stl?name=desk-box-wide-base-rev2",
        filename="desk-box-wide-base-rev2.stl",
    )
    older = exports.export(alice, asked.model_copy(update={"variant_id": first, "format": "3mf"}))
    assert older == exports.ExportReady(
        url=f"/v1/exports/{job.VERSION}/{SHA}.3mf?name=desk-box-wide-base-rev1",
        filename="desk-box-wide-base-rev1.3mf",
    )
    assert run.calls == 1


async def test_a_failed_export_says_why_and_a_variant_outside_the_brief_is_refused(
    confirming_tenants: Tenants, monkeypatch: pytest.MonkeyPatch
) -> None:
    alice = confirming_tenants.of(ALICE)
    brief, _, second = await a_confirmed_set(alice, None)
    run = Gated(job.Ran(ExportFailed(key=SHA, version=job.VERSION, reason="too big"), True))
    run.gate.set()
    lane = Exports(run)
    monkeypatch.setattr(exports, "EXPORTS", lane)
    asked = exports.ExportInput(variant_id=second, brief_id=brief, format="step")
    lane.read(alice.geometry, entry.open_entry(alice.variants, second, image_tag(BUILD)), 5)
    assert exports.export(alice, asked) == exports.ExportFailure(reason="too big")
    stray = entry.variant_id("result = 3", image_tag(BUILD))
    entry.save(alice.variants, stray, "result = 3", Build(outcome=Built(), output=""), BREP)
    with pytest.raises(entry.UnknownVariant):
        exports.export(alice, asked.model_copy(update={"variant_id": stray}))


def test_the_download_record_keeps_a_name_from_breaking_the_header() -> None:
    assert Download(filename="a-b.step", data=b"").filename == "a-b.step"
    for bad in ('a"b.step', "a\r\nb.step", "../a.step", ""):
        with pytest.raises(ValueError):
            Download(filename=bad, data=b"")
