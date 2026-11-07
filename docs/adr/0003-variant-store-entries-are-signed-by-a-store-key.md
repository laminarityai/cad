# Each variant store signs its build records with a key beside the store

A scorecard must describe the shape that was checked. The variant id re-derives from `code.py`, and `build.json` records the hash of `result.brep`, but before this decision nothing proved that `build.json` came from a build. Anyone who could write to the store could replace `result.brep`, rewrite the hash, and have the checks score a new shape under the old id (issue #11).

Each store now has one 32-byte random key in a file beside the store directory, never inside it: `~/.cad/variants.key` for the default store `~/.cad/variants`, and `<root>.key` for a store passed with `--root`. The first save creates it with mode 0600. A key that other users can read, that is a symbolic link, or that has the wrong length is refused. Each entry stores `build.mac`, an HMAC-SHA256 over the variant id and the exact bytes of `build.json`. The record is checked before it is parsed. Because the MAC covers the id, a signed record copied from another entry fails. The MAC covers `result.brep` through the hash in `build.json`, and the id covers `code.py`.

Sandboxed code cannot read the key. Build containers have no mounts, and check containers mount only the staged check sources under `~/.cad/stage/`. The MCP tools take code, a variant id that must be 16 hex digits, and a material key, so none of them can name a file.

## Consequences

An entry that fails the check is refused, not rebuilt. `score_variant` and `cad-sandbox run-checks` report `StaleVariant`, and `build_variant` reports that the store is unusable for that id. The message names the variant id and says that the operator must delete the entry. The host paths go only to the server log. A rebuild in place would need to replace a directory that another process can be reading, so phase 1 leaves that step to the operator.

Entries stored before this change are not migrated. A change under `src/cad/variants/` changes every variant id, so old entries are never opened again. They stay on disk until the operator deletes them.

The key protects against writers that cannot read the key: a store copied or shared from another host, a sync tool, or another account with write access to the store. A process that runs as the same user as the server can read the key and sign a forged record. Protection against that process needs a key that the operating system holds, such as the macOS keychain, and is out of scope for phase 1. If the key is lost, every stored entry is refused, and the operator deletes the store.
