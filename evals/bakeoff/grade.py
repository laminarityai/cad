"""Kernel-neutral grader: loads STEP with OCP only and checks it against the reference and oracles."""
import json
import math
import sys
from functools import cache
from pathlib import Path

import yaml
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepGProp import BRepGProp
from OCP.Bnd import Bnd_Box
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.GProp import GProp_GProps
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_FACE, TopAbs_IN, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Pnt, gp_Vec

ROOT = Path(__file__).parent
DEFAULT_BBOX_TOL = 0.1
DEFAULT_VOLUME_TOL = 0.02
RADIUS_TOL = 0.05


@cache
def oracles():
    return {p["id"]: p for p in yaml.safe_load((ROOT / "prompts.yaml").read_text())}


def load_step(path):
    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != 1:
        return None
    reader.TransferRoots()
    return reader.OneShape()


def solids(shape):
    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    out = []
    while exp.More():
        out.append(TopoDS.Solid_s(exp.Current()))
        exp.Next()
    return out


def extents(shape):
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    x0, y0, z0, x1, y1, z1 = box.Get()
    return sorted([x1 - x0, y1 - y0, z1 - z0])


def mass_props(shape):
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass(), props.CentreOfMass()


def cylinder_axes(shape):
    """{radius: set of distinct (axis, axial position) keys}.

    A face split at its seam shares both, so it counts once; coaxial holes in
    different walls differ in axial position, so they count separately.
    """
    axes = {}
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        surf = BRepAdaptor_Surface(TopoDS.Face_s(exp.Current()))
        if surf.GetType() == GeomAbs_Cylinder:
            cyl = surf.Cylinder()
            d = cyl.Axis().Direction()
            raw = [d.X(), d.Y(), d.Z()]
            dv = [-c for c in raw] if next(c for c in raw if abs(c) > 1e-6) < 0 else raw
            p = cyl.Axis().Location()
            vmid = (surf.FirstVParameter() + surf.LastVParameter()) / 2
            mid = [a + vmid * b for a, b in zip([p.X(), p.Y(), p.Z()], raw)]
            s = sum(a * b for a, b in zip(mid, dv))
            foot = [a - s * b for a, b in zip(mid, dv)]
            key = tuple(round(c, 2) for c in dv + foot) + (round(s, 1),)
            axes.setdefault(round(cyl.Radius(), 3), set()).add(key)
        exp.Next()
    return axes


def count_axes(axes, radius):
    return sum(len(keys) for r, keys in axes.items() if abs(r - radius) <= RADIUS_TOL)


def ring_inside(solid, center, axis, radius, n=1440):
    axis = gp_Vec(*axis).Normalized()
    helper = gp_Vec(1, 0, 0) if abs(axis.X()) < 0.9 else gp_Vec(0, 1, 0)
    u = axis.Crossed(helper).Normalized()
    v = axis.Crossed(u).Normalized()
    classifier = BRepClass3d_SolidClassifier(solid)
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n
        p = gp_Pnt(center.XYZ())
        p.Translate(u * (radius * math.cos(a)) + v * (radius * math.sin(a)))
        classifier.Perform(p, 1e-6)
        out.append(classifier.State() == TopAbs_IN)
    return out


def check_gear(solid, axes_by_radius, center, oracle):
    """Teeth = runs of solid on a ring between pitch and tip; OD = ring just outside tip must be empty."""
    bore = next((keys for r, keys in axes_by_radius.items() if abs(r - 4.0) <= RADIUS_TOL), None)
    if not bore:
        return "no bore axis found"
    axis = next(iter(bore))[:3]
    tip_r = oracle["outer_diameter"] / 2
    ring = ring_inside(solid, center, axis, tip_r - 1.0)
    teeth = sum(1 for i in range(len(ring)) if ring[i] and not ring[i - 1])
    if teeth != oracle["teeth"]:
        return f"teeth {teeth} != {oracle['teeth']}"
    if any(ring_inside(solid, center, axis, tip_r + 0.2, n=720)):
        return f"material beyond OD {oracle['outer_diameter'] + 0.4}"
    if not any(ring_inside(solid, center, axis, tip_r - 0.2, n=720)):
        return f"no material at OD {oracle['outer_diameter'] - 0.4}"
    return None


@cache
def reference(part_id):
    shape = load_step(ROOT / "reference" / f"{part_id}.step")
    return extents(shape), mass_props(shape)[0]


def grade(part_id, step_path):
    oracle = oracles()[part_id]
    step_path = Path(step_path)
    if not step_path.exists():
        return {"pass": False, "category": "no_output", "detail": "no out.step"}
    shape = load_step(step_path)
    if shape is None or shape.IsNull():
        return {"pass": False, "category": "no_output", "detail": "unreadable STEP"}

    found = solids(shape)
    if len(found) != 1:
        return {"pass": False, "category": "invalid_solid", "detail": f"{len(found)} solids"}
    solid = found[0]
    if not BRepCheck_Analyzer(solid).IsValid():
        return {"pass": False, "category": "invalid_solid", "detail": "BRepCheck invalid"}

    ref_ext, ref_vol = reference(part_id)
    ext = extents(solid)
    vol, center = mass_props(solid)
    measured = {"extents": [round(e, 3) for e in ext], "volume": round(vol, 2)}

    bbox_tol = oracle.get("bbox_tol", DEFAULT_BBOX_TOL)
    if any(abs(a - b) > bbox_tol for a, b in zip(ext, ref_ext)):
        return {"pass": False, "category": "bbox", "measured": measured,
                "detail": f"extents {measured['extents']} vs {[round(e, 3) for e in ref_ext]}"}

    vol_tol = oracle.get("volume_tol", DEFAULT_VOLUME_TOL)
    if abs(vol - ref_vol) > vol_tol * ref_vol:
        return {"pass": False, "category": "volume", "measured": measured,
                "detail": f"volume {vol:.1f} vs {ref_vol:.1f} ({(vol / ref_vol - 1) * 100:+.1f}%)"}

    axes = cylinder_axes(solid)
    for feat in oracle.get("features", []):
        n = count_axes(axes, feat["radius"])
        if n < feat["min_count"]:
            return {"pass": False, "category": "features", "measured": measured,
                    "detail": f"{n} cylinders at r={feat['radius']}, need {feat['min_count']}"}

    if "gear" in oracle:
        problem = check_gear(solid, axes, center, oracle["gear"])
        if problem:
            return {"pass": False, "category": "features", "measured": measured, "detail": problem}

    return {"pass": True, "category": "pass", "measured": measured, "detail": ""}


if __name__ == "__main__":
    print(json.dumps(grade(sys.argv[1], sys.argv[2])))
