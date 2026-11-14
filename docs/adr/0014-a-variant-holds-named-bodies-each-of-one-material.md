# A variant holds named bodies, each of one material

Status: Accepted, 2026-11-13. Every rule below was the design's pick. The operator accepted the ADR on 2026-11-13, chose the word "body", and chose that the stress check solves one body alone. Nothing here is built yet.

The operator wants models coloured the way CAD models are, by part and by area, and gave the example of gray gears beside black carbon fibre ([issue 285](https://github.com/laminarityai/cad/issues/285)). Colouring areas of one body is presentation only and needs no decision. Gears beside a plate is one model in two materials, and that reaches the checks. Today a variant is one solid of one material. `closed_solid` passes only on one solid, `mass` reads one density, and `fea` reads one modulus and one strength. This ADR records how a variant comes to hold several bodies, and why the checks still decide.

The design note [multi-material-models.md](../design/multi-material-models.md) has the evidence and the build order.

## The decision

### A body is one or more solids with a name and one material

A variant's `result` holds 1 to 12 bodies. A body is the solids that share a name, and it has exactly one material. A variant with one unnamed solid has one body, and no verdict on it changes. No stored variant, result or scorecard is migrated.

GLOSSARY.md defines "Body". "Assembly" stays avoided. A supplied part stays outside `result`, as ADR-0012 says. ADR-0012 calls `result` "the agent's body". It now holds the agent's bodies, and ADR-0012's rules apply to each one.

### The build names bodies, and a name only selects solids

Build code labels each solid of `result`. The server parses the names into a typed, bounded record and refuses a build of more than one solid in which any solid has no name, and a build whose names are malformed. A check reads the solids from the BREP itself. It uses a name only to learn which solids to measure, and it never takes geometry or a number from the record.

### A body's material is confirmed by the person or chosen by the agent

The agent states each body's material key when it builds. A confirmed `made_of` that names the body pins the key. A confirmed `made_of` that names no body pins every body. A build that differs is refused. Otherwise the key is the agent's material choice for that body, with a one-line reason, labelled agent-chosen on the scorecard. This is the existing rule for a variant's one material, applied per body. Every value a check reads still comes from the tables by that exact key, or from research under ADR-0009.

### A requirement names a body by an exact name the person confirmed

A requirement applies to the whole variant unless it names a body. A body name a requirement uses is listed on the proposal with the person's words that state it, and the person confirms it on the card. A build for that brief must produce every confirmed name, or it is refused. No name is ever matched by its wording.

### Each check reads each body's own material

`mass` is the sum over bodies of volume times that body's density, and it is unknown when any one density is unknown. `closed_solid`, `holes` and `min_wall` read each body. `interference` fails two bodies that share volume. `extents` and `fit` read the whole result. Each changed check gets a new version.

### The stress check solves one named body alone, and the joint is listed as not checked

A load case on a variant of more than one solid names one body of one solid. The check solves that body alone in its own material. No check knows how two bodies are joined. So every scorecard of a variant of more than one solid lists "How the bodies are joined is not checked" under the requirements no check covers, and it counts in coverage.

## What this accepts

The agent chooses which solid carries which name. A person may confirm "the plate is carbon fibre", and the agent decides which solid is the plate. No rule can check that choice. The guard is what the person sees: each body's name beside its volume, mass, material and colour on the card and the scorecard, and the body alone in the viewer. This is the same trust the product already places in the agent's code, which decides the whole shape.

It also chooses which solid a load case on a named body acts on. ADR-0007 rejected build code that tags faces for a load, and a body name is a coarser tag of the same kind. The supports and the load inside that body still come from ADR-0007's fixed rules, so the agent picks the solid and never the faces.

## What it rules out

- A stress verdict across a joint. A bonded solve needs its own reference cases and its own decision.
- A colour as an input to any verdict. A body name selects solids and their material, and nothing else.
- A material written in build code. It is a typed argument, resolved by exact key before a container starts.
- Whole-assembly checks that include supplied parts. ADR-0012 keeps them as later work.
