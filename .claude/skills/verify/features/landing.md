# Landing page

The public page at `/`. It is static HTML and CSS, rendered at build time from `web/src/features/landing/` and `web/landing.html`, and it loads no app bundle and nothing from another site. `src/cad/web/static.py` serves it with no session. Tests: `web/src/features/landing/landing.test.ts` (what the page may say), `tests/web/test_landing_facts.py` (the numbers measured in this repo) and `tests/web/test_static.py` (the route).

## Before you publish

- `DEMO_HREF` in `web/src/features/landing/site.ts` is a placeholder (`mailto:demo@example.com`). Set it to the operator's address or form link. The label, the product name, the app link and the repository link are in the same file.
- Every number on the page is in `facts.json` with its source. Add a number there first. The landing test fails on a number that no fact or brief owns.

## Retake the pictures

The pictures are real captures. `uv run python tools/landing_capture.py --dry` walks a scripted model through the brief in `capture.json` and costs nothing. `uv run python tools/landing_capture.py` does the same on one live model session: it needs Docker and a key in `~/.config/cad/anthropic.env`, runs the server on a scratch HOME at port 8791, and stops when the model usage in the server log passes `--budget` USD (1.6 by default). It writes `web/src/features/landing/assets/` and its `manifest.json`, in light and dark, and fails above 1.5 MB. Run it again after a colour change.

## Look at it

```
cd web && npm run build && cd ..
uv run cad-http --root "$(mktemp -d)" --port 8791 --opener true
```

Open `http://127.0.0.1:8791/` signed out at 375 px and 1280 px, in both themes. The main button reads "Request a demo" and links to `DEMO_HREF`. The network log shows requests to the server only. `/app/` still answers 200.
