# Each variant store signs its build records with a key beside the store

A scorecard must describe the shape that was checked. The variant id re-derives from `code.py`, and `build.json` records the hash of `result.brep`, but before this decision nothing proved that `build.json` came from a build. Anyone who could write to the store could replace `result.brep`, rewrite the hash, and have the checks score a new shape under the old id (issue #11).

Each store now has one 32-byte random key in a file beside the store directory, never inside it: `~/.cad/variants.key` for the default store `~/.cad/variants`, and `<root>.key` for a store passed with `--root`. The first save creates it with mode 0600. A key that other users can read, that is a symbolic link, or that has the wrong length is refused. Each entry stores `build.mac`, an HMAC-SHA256 over the variant id and the exact bytes of `build.json`. The record is checked before it is parsed. Because the MAC covers the id, a signed record copied from another entry fails. The MAC covers `result.brep` through the hash in `build.json`, and the id covers `code.py`.

Sandboxed code cannot read the key. Build containers have no mounts, and check containers mount only the staged check sources under `~/.cad/stage/`. The MCP tools take code, a variant id that must be 16 hex digits, and a material key, so none of them can name a file.

## Consequences

An entry that fails the check is refused, not rebuilt. `score_variant` and `cad-sandbox run-checks` report `StaleVariant`, and `build_variant` reports that the store is unusable for that id. The message names the variant id and says that the operator must delete the entry. The host paths go only to the server log. A rebuild in place would need to replace a directory that another process can be reading, so phase 1 leaves that step to the operator.

Entries stored before this change are not migrated. A change under `src/cad/variants/` changes every variant id, so old entries are never opened again. They stay on disk until the operator deletes them.

The key protects against writers that cannot read the key: a store copied or shared from another host, a sync tool, or another account with write access to the store. A process that runs as the same user as the server can read the key and sign a forged record. Protection against that process needs a key that the operating system holds, such as the macOS keychain, and is out of scope for phase 1. If the key is lost, every stored entry is refused, and the operator deletes the store.

## Amended 2026-11-07

A stale entry is one whose id no longer re-derives from its `code.py`. Every deploy that changes `TRUST_DIGEST` or the sandbox image tag makes every stored entry stale. The product is hosted, so a refusal at that point breaks users' saved variants through no action of theirs. PR #70 (issue #45) changes how `score_variant` handles a stale entry, and this amendment records the change.

`build.json` now records `code_sha256`, the SHA-256 of `code.py`. The MAC covers it with the rest of the record. If an entry is stale, its MAC verifies, and its `code.py` matches `code_sha256`, then `score_variant` builds the stored code again through `build_variant` and scores the new variant. The scorecard gives the new id as `variant_id` and the old id as `rebuilt_from`. The rebuild writes a new entry under the new id and leaves the old entry unchanged. So it does not replace a directory that another process can be reading, which was the reason this ADR gave for leaving rebuilds to the operator.

The trust model does not change. The rebuild runs only code whose hash the store key signed, so a writer without the key cannot have its own code built and scored under a stored id. These entries are still refused:

- An entry whose MAC fails, or that has no MAC.
- An entry whose record has no `code_sha256`, because it was stored before PR #70.
- An entry whose `code.py` does not match `code_sha256`.

`cad-sandbox run-checks` does not rebuild, and it still reports a stale entry as `StaleVariant`. A rebuild that does not build is refused as `RebuildFailed`, with the build outcome. The server deletes no entry, old or new. Only the operator deletes entries.

## Amendment (2026-11-11): builds that read supplied parts

[ADR-0012](0012-a-supplied-part-is-read-by-the-build-and-never-graded.md) lets build code read a part the person supplied, and place and copy a component. A variant is then more than its code, so the id and the signed record cover the parts too. The variant id hashes the image tag, `TRUST_DIGEST`, the code, and for each part the build read its id, the SHA-256 of its BREP and its placements. `build.json` records the same list, and the MAC covers it with the rest of the record.

A rebuild of a stale entry reads that list and fetches each part's BREP from the project store by its SHA-256, not by the part's id. A part that kept its id under newer geometry therefore rebuilds the old variant with the old geometry. A BREP whose bytes no longer match the recorded SHA-256 refuses the rebuild as `RebuildFailed`.

The parts reach the build on stdin, after the code. "Build containers have no mounts" stands.
