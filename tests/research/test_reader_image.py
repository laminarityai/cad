from pathlib import Path

from cad.checks import report
from cad.geometry import job as mesh_job
from cad.research import pdf
from cad.sandbox import image
from cad.variants import entry

READER_CODE = ("cad/research/pdf.py", "cad/research/pdf_reader.py")


def test_no_reader_file_feeds_a_check_version_the_mesh_version_or_a_variant_id() -> None:
    """Reading PDFs edits no file that a check version, the mesh version or a variant id hashes,
    so every one of them keeps its value."""
    src = Path(pdf.__file__).parents[2]
    assert all((src / path).exists() for path in READER_CODE)
    hashed = set(report.DEPENDENCIES.files) | set(mesh_job.SOURCES.files)
    hashed |= set(mesh_job.SERVED.files)
    assert not hashed & set(READER_CODE)
    trusted = {entry.SOURCE / name for name in entry.TRUSTED_FILES}
    assert not trusted & {src / path for path in READER_CODE}


def test_the_reader_image_is_its_own_and_no_variant_or_check_image_hashes_it() -> None:
    assert pdf.READER not in image.IMAGES
    assert pdf.READER.base is None
    reader_dir = pdf.READER.directory
    for one in image.IMAGES:
        assert all((one.directory / name).parent != reader_dir for name in one.context)
    assert pdf.READER.repository == "cad-reader"
    assert image.image_tag(pdf.READER).startswith("cad-reader:")
