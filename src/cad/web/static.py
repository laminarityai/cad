"""Serves the built landing page at `/` and the built web app under `/app`.

The landing page is `landing.html` in `dist`. It is public and static, so it needs no session,
and it links to its own assets under `/app/assets`. It is not cached, like the app's page.

A path with a file extension is an asset: it is served from `dist` or it is 404, so a missing
script never answers with the page. Any other path under `/app` is a route of the app, and gets
`index.html`. Vite names built assets by content hash, so they are cached for good and the page is
not.
"""

from pathlib import Path
from typing import Final

from starlette.requests import Request
from starlette.responses import FileResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Route

ROOT: Final = Path(__file__).resolve().parents[3]
DIST: Final = ROOT / "web" / "dist"
PREFIX: Final = "/app"
LANDING: Final = "landing.html"
ASSET_CACHE: Final = "public, max-age=31536000, immutable"
PAGE_CACHE: Final = "no-cache"
NOT_BUILT: Final = "The web app is not built. Run `npm run build` in web/, or `uv run verify`."


def web_routes(dist: Path = DIST) -> list[Route]:
    base = dist.resolve()

    async def to_app(_: Request) -> Response:
        return RedirectResponse(f"{PREFIX}/", status_code=307)

    async def landing(_: Request) -> Response:
        page = base / LANDING
        if not page.is_file():
            return PlainTextResponse(NOT_BUILT, status_code=503)
        return FileResponse(page, headers={"Cache-Control": PAGE_CACHE})

    async def serve(request: Request) -> Response:
        index = base / "index.html"
        if not index.is_file():
            return PlainTextResponse(NOT_BUILT, status_code=503)
        name: str = request.path_params.get("path", "")
        found = _inside(base, name)
        if found is not None and found.is_file():
            long_lived = found != index
            return FileResponse(
                found, headers={"Cache-Control": ASSET_CACHE if long_lived else PAGE_CACHE}
            )
        if "." in name.rsplit("/", 1)[-1]:
            return PlainTextResponse("not found", status_code=404)
        return FileResponse(index, headers={"Cache-Control": PAGE_CACHE})

    return [
        Route("/", landing, methods=["GET", "HEAD"]),
        Route(PREFIX, to_app, methods=["GET"]),
        Route(f"{PREFIX}/", serve, methods=["GET", "HEAD"]),
        Route(f"{PREFIX}/{{path:path}}", serve, methods=["GET", "HEAD"]),
    ]


def _inside(base: Path, name: str) -> Path | None:
    """The file `name` names under `base`, or None when it would leave `base`."""
    if name == "":
        return None
    candidate = (base / name).resolve()
    return candidate if candidate.is_relative_to(base) else None
