import pytest

from cad.checks.container.calculix import Material, SolveFailed, deck, read_frd
from cad.checks.container.mesher import (
    MIN_SIZE_MM,
    Mesher,
    MeshFailed,
    MeshPair,
    MeshSizes,
    OverCap,
    TetMesh,
    mesh_pair,
    mesh_sizes,
)

TET = TetMesh(
    nodes=(
        (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
        (0.5, 0.0, 0.0), (0.5, 0.5, 0.0), (0.0, 0.5, 0.0),
        (0.0, 0.0, 0.5), (0.5, 0.0, 0.5), (-1.2246467991473532e-16, 0.5, 0.5),
    ),
    tets=((0, 1, 2, 3, 4, 5, 6, 7, 8, 9),),
    faces=(),
    surfaces=(),
)  # fmt: skip


# Negative values run into the field before them.
FRD = """\
    1PSTEP                         1           1           1
  100CL  101 1.000000000          10                     0    1           1
 -4  DISP        4    1
 -5  D1          1    2    1    0
 -5  ALL         1    2    0    0    1ALL
 -1         1 0.00000E+00 0.00000E+00 0.00000E+00
 -1         2 0.00000E+00 0.00000E+00 0.00000E+00
 -1         3 0.00000E+00 0.00000E+00 0.00000E+00
 -1         4-1.18824E-04-1.18824E-04-1.51464E-04
 -3
    1PSTEP                         2           1           1
  100CL  101 1.000000000          10                     0    1           1
 -4  STRESS      6    1
 -5  SXX         1    4    1    1
 -1         1-1.54286E+01-1.54286E+01-3.60000E+01-1.24071E-06-1.13780E+00-1.13780E+00
 -1         2 1.02857E+01 1.02857E+01 2.40001E+01-1.24071E-06-9.10241E-01 2.04804E+00
 -1         3 1.02857E+01 1.02857E+01 2.40001E+01-1.24071E-06 2.04804E+00-9.10241E-01
 -1         4-3.59546E+00-3.59546E+00-3.60000E+01 4.55119E-01 6.67584E-15 1.48392E-14
 -3
9999
"""


def test_the_frd_reader_takes_each_nodes_fixed_width_values() -> None:
    read = read_frd(FRD, 4, 1)
    assert not isinstance(read, SolveFailed), read
    (field,) = read
    assert field.displacement[3] == (-1.18824e-04, -1.18824e-04, -1.51464e-04)
    assert field.stress[0] == (-15.4286, -15.4286, -36.0, -1.24071e-06, -1.1378, -1.1378)
    assert field.stress[3][5] == 1.48392e-14


def test_the_frd_reader_fails_closed_on_a_missing_step_or_node() -> None:
    assert isinstance(read_frd(FRD, 4, 2), SolveFailed)
    assert isinstance(read_frd(FRD, 5, 1), SolveFailed)


def test_every_deck_field_fits_the_20_characters_calculix_reads() -> None:
    text = deck(TET, Material(200_000.0, 0.3), frozenset({0, 1, 2}), ({3: (0.0, 0.0, -1e-7)},))
    data = [line for line in text.splitlines() if not line.startswith("*")]
    assert max(len(field.strip()) for line in data for field in line.split(",")) <= 20
    assert "4, 3, -1.000000000000e-07" in text.splitlines()


def test_the_mesh_rule_clamps_the_size_and_refines_by_the_fine_ratio() -> None:
    sizes = mesh_sizes(5.0, 200.0)
    assert (sizes.coarse, sizes.fine) == (5.0, pytest.approx(5.0 / 1.5))
    assert mesh_sizes(10.0, 100.0).coarse == 5.0
    assert mesh_sizes(0.01, 100.0).coarse == MIN_SIZE_MM


SIZES = MeshSizes(3.0, 2.0)
OVER = "has 900000 nodes, above the cap of 150000"


def mesher(over_cap_below: float) -> Mesher:
    """Each mesh holds one node that records the size and floor it was made at. Without a floor,
    a size under `over_cap_below` is over the cap."""

    def mesh(size_mm: float, floor_mm: float) -> TetMesh | MeshFailed:
        if not floor_mm and size_mm < over_cap_below:
            return OverCap(OVER)
        return TetMesh(((size_mm, floor_mm, 0.0),), (), (), ())

    return mesh


def made_at(pair: MeshPair | MeshFailed) -> tuple[tuple[float, float], tuple[float, float]]:
    assert isinstance(pair, MeshPair), pair
    (coarse,), (fine,) = pair.coarse.nodes, pair.fine.nodes
    return coarse[:2], fine[:2]


def test_meshes_under_the_node_cap_keep_the_curvature_rule() -> None:
    pair = mesh_pair(mesher(over_cap_below=0.0), SIZES)
    assert made_at(pair) == ((3.0, 0.0), (2.0, 0.0))
    assert isinstance(pair, MeshPair) and pair.over_cap is None


def test_a_fine_mesh_over_the_cap_floors_both_meshes_at_half_the_coarse_size() -> None:
    pair = mesh_pair(mesher(over_cap_below=2.5), SIZES)
    assert made_at(pair) == ((3.0, 1.5), (2.0, 1.5))
    assert isinstance(pair, MeshPair) and pair.over_cap is not None
    assert pair.over_cap.reason == f"the mesh at 2 mm {OVER}"


def test_a_floored_mesh_still_over_the_cap_fails_naming_both_meshes() -> None:
    def always_over(size_mm: float, floor_mm: float) -> TetMesh | MeshFailed:
        return OverCap(OVER)

    failed = mesh_pair(always_over, SIZES)
    assert failed == MeshFailed(
        f"the mesh at 3 mm {OVER}; the mesh at 3 mm with no element under 1.5 mm {OVER}"
    )


def test_a_mesh_that_fails_for_another_reason_is_not_meshed_again() -> None:
    def broken(size_mm: float, floor_mm: float) -> TetMesh | MeshFailed:
        return MeshFailed("gmsh failed: RuntimeError: boom")

    failed = mesh_pair(broken, SIZES)
    assert failed == MeshFailed("the mesh at 3 mm failed: gmsh failed: RuntimeError: boom")
