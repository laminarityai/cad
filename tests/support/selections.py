import hashlib
from dataclasses import dataclass

from cad.geometry import job, store
from cad.geometry.container.wire import EdgeFacts, FaceFacts, TopologyWire
from cad.geometry.model import Tessellated, TessellationFailed
from cad.operations.briefs import (
    CreateBriefInput,
    ProposeRequirementsInput,
    RequirementDraft,
    create_brief,
    propose_requirements,
)
from cad.operations.confirmation import AskToConfirmInput, ask_to_confirm
from cad.operations.model import Tenant
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Build, Built
from cad.variant_sets import store as variant_sets
from cad.variants import entry
from tests.support.rows import RAIL

TEXT = "A plate under 150 g"
UNDER_150 = RequirementDraft.model_validate(
    {
        "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
        "quote": "under 150 g",
    }
)
RAIL_SHA = hashlib.sha256(RAIL).hexdigest()
BOX = {"xmin": -5.0, "xmax": 5.0, "ymin": -10.0, "ymax": 10.0, "zmin": 0.0, "zmax": 6.0}
NORMALS = [
    (-1.0, 0.0, 0.0),
    (1.0, 0.0, 0.0),
    (0.0, -1.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, -1.0),
    (0.0, 0.0, 1.0),
]
TOP = 5


def cube() -> TopologyWire:
    """A box: faces -X +X -Y +Y -Z +Z as 0 to 5, and its 12 edges, one for each pair of faces
    that are not opposite."""
    pairs = [(a, b) for a in range(6) for b in range(a + 1, 6) if a // 2 != b // 2]
    faces: list[FaceFacts] = [
        {
            "type": "PLANE",
            "area": 100.0,
            "center": normal,
            "normal": normal,
            "radius": None,
            "axis": None,
            "edges": [n for n, pair in enumerate(pairs) if index in pair],
        }
        for index, normal in enumerate(NORMALS)
    ]
    edges: list[EdgeFacts] = [
        {
            "type": "LINE",
            "length": 10.0,
            "center": (float(a), float(b), 0.0),
            "direction": (0.0, 0.0, 1.0),
            "radius": None,
            "faces": [a, b],
        }
        for a, b in pairs
    ]
    return {"faces": faces, "edges": edges}


def stored_mesh(tenant: Tenant, mesh: Tessellated | TessellationFailed | None = None) -> None:
    store.write(tenant.geometry, mesh or tessellated())


def tessellated() -> Tessellated:
    return Tessellated.model_validate(
        {
            "brep_sha256": RAIL_SHA,
            "version": job.VERSION,
            "shapes": {
                "version": 3,
                "id": "/variant",
                "name": "variant",
                "parts": [],
                "loc": [[0, 0, 0], [0, 0, 0, 1]],
                "normal_len": 0,
                "bb": BOX,
            },
            "topology": cube(),
        }
    )


def failed() -> TessellationFailed:
    return TessellationFailed(brep_sha256=RAIL_SHA, version=job.VERSION, reason="a bad BREP")


@dataclass(frozen=True)
class Project:
    project: str
    brief: str


async def confirmed(tenant: Tenant) -> Project:
    created = create_brief(tenant, CreateBriefInput(text=TEXT))
    propose_requirements(
        tenant, ProposeRequirementsInput(brief_id=created.brief_id, requirements=[UNDER_150])
    )
    answer = await ask_to_confirm(tenant, AskToConfirmInput(project_id=created.project_id))
    assert answer.status == "answered"
    return Project(created.project_id, created.brief_id)


def joined(tenant: Tenant, brief: str, code: str, slot: int | None = None) -> str:
    vid = entry.variant_id(code, image_tag(BUILD))
    entry.save(tenant.variants, vid, code, Build(outcome=Built(), output=""), RAIL)
    key = variant_sets.confirmed_key(tenant.roots, brief)
    variant_sets.join(tenant.roots.projects, key, code, entry.VariantId(vid), slot)
    return vid
