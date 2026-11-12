# Viewer tools: measure, section, pull apart, and the size check's dimensions

This note says how to build the viewer tools: a readout of measurements for the selection, a section through the part, a way to pull a context part away from the variant, and the `extents` check's numbers drawn as dimensions. [ADR-0013](../adr/0013-a-viewer-measurement-is-information-on-screen-never-a-check.md) records what a number on screen may and may not do. This note assumes that ADR.

Each fact carries one of three labels:

- **Measured** means a prototype run on 2026-11-12 produced it.
- **Read** means it comes from the code, the library's source and types, or git history.
- **Inferred** means neither, and a build step must confirm it.

## How the prototype ran

The run used a worktree at `8ff531d`. It turned the library flags on in `web/src/features/viewer/engine.ts` and exposed the viewer on `window`, then started `cad-http` and drove the workspace in headless Chromium as `.claude/skills/verify/SKILL.md` describes. Screens were 1440 × 900 and 390 × 900. The readout and the dimension lines in the screenshots are HTML and SVG injected into the page, not app code. No prototype code is committed.

The part is an L bracket: a 60 × 40 × 5 mm plate, a 60 × 5 × 70 mm upright, a 6 mm fillet at the bend, and two 5.5 mm holes 36 mm apart. It has 11 faces and 27 edges. Every check on its scorecard passed. A second brief, a cap that slides over the upright, used the bracket as its context part, so the viewer drew the bracket as the fit ghost. The cap was never scored.

## What three-cad-viewer 5.1.3 offers

`web/package.json` pins `"three-cad-viewer": "5.1.3"`. The facts below are read from `web/node_modules/three-cad-viewer/dist`, its `.d.ts` files and its `Readme.md`, unless marked otherwise.

### Measure

- The `measureTools` option adds Distance and Properties buttons to the library's toolbar. `viewer.activateTool("distance", true)` turns one on.
- `viewer.meshBackend` is a `MeshMeasureBackend`. The `Viewer` constructor always creates it, whatever the flags say. `properties(path)` describes one face or edge, and `distance(path1, path2, center)` gives the distance and the angle between two.
- Its types say the values are exact for planar faces and straight edges, and within the tessellation deflection for curved ones. The geometry type comes from the server's face and edge types, so it is exact. A circle's radius comes from a circle fitted to the polyline.
- `externalMeasurementBackend: true` sends the selected ids to the app through `notifyCallback`, and the app answers with `handleBackendResponse`. That is a route for exact numbers from the server. This design does not use it.
- The library shows a hover line, `tcv_status_line`, with mesh numbers such as "plane: area ≈ 1692.50". No flag turns it off. Hover preselection runs unless the model is GDS or studio mode is on.

### Section

- The library has three clipping planes. `setClipNormal(i, normal)` and `setClipSlider(i, value)` place one. `setClipIntersection`, `setClipObjectColorCaps`, `setClipPlaneHelpers` and `resetClip` change how they show.
- Clipping works only while the library's "clip" tab is active. `setActiveTab("clip")` sets `renderer.localClippingEnabled`, and the stencil caps fill the cut faces.
- **Measured.** `setActiveTab("clip")`, `setClipNormal(0, [-1, 0, 0])` and `setClipSlider(0, 0)` cut the bracket at x = 0 with filled caps while the library's toolbar stayed hidden ([screenshot](../review/viewer-tools-section-x.png)).

### Explode

- The `explodeTool` option adds a button. `setExplode(true)` calls `explode(duration = 2, speed = 1, multiplier = 2.5)`. It moves each object group away from the centre of the bounding box and plays the move as an animation with a slider bar.
- Turning explode on turns any measure tool off, and copying the point under the cursor stops working while the model is exploded.
- **Measured.** On the single-part bracket, explode moved nothing and drew the library's animation bar ([screenshot](../review/viewer-tools-explode-single-part.png)). With the cap and the bracket ghost on screen, it also moved nothing visible ([screenshot](../review/viewer-tools-explode-with-context-part.png)). The run did not find out why.

### What the library does not offer

`index.d.ts` exports `Viewer`, `Display`, the environment manager, a timer, a logger, material presets and types. The arrow class the library uses for its own distance lines is internal and not exported. `viewer.onAfterRender` exists and runs after each frame. Dimension lines are therefore our own drawing.

## Why each tool is off today

**Read.** The commit that added the viewer, "the React shell with a 3D viewer and live scorecards" (`fdd33a1`, PR #173), set `tools`, `measureTools`, `selectTool`, `explodeTool` and every other tool flag to `false`, and called `display.showTools(false)` and `display.showInfo(false)`. Neither the commit nor the PR says why. **Inferred.** The shell needed only a view of the part.

**Read.** The PR that lets a person point at part of a design and ask for a change (`e12572e`, PR #222) turned the library's pick handler off with `viewer.setPickHandler(false)`. It added the app's own `pointerdown`, `click` and `dblclick` handlers, which pick with `viewer.idPicker.pickAt` and a 4 px slop. Since then a click on the canvas changes the selection and does nothing else.

**Measured.** Turning the flags back on does not give working tools:

- `display.showTools(true)` draws the library's toolbar and its Tree, Clip and Material tabs over the canvas. The toolbar covers the Download button ([screenshot](../review/viewer-tools-library-toolbar.png)).
- With the distance tool active, a click went to the app's handler. It replaced the selection with one face, and the library's Distance panel stayed empty ([screenshot](../review/viewer-tools-library-distance.png)).

No issue or PR since has asked for the tools.

## What the tools need that the mesh lacks

**Read.** The browser holds two descriptions of the part. Both come from the geometry route.

- **The mesh.** `src/cad/geometry/container/tessellate.py` tessellates with a deflection of `max(extent × 0.0005, 0.001 mm)` and an angular tolerance of 0.1. For the 70 mm bracket the deflection is 0.035 mm.
- **The topology.** `Tessellated.topology` carries the kernel's facts for every face (type, area, centre, normal, radius, axis, edges) and every edge (type, length, centre, direction, radius, faces). These are the same facts `read_selection` gives the agent.

**Measured.** The run compared the two on the bracket.

| Quantity | Topology (kernel) | Mesh backend |
| --- | --- | --- |
| Area of the 300, 3540 and 4200 mm² planes | exact | exact |
| Area of planes bounded by the fillet arc | exact | within 2e-5, relative |
| Length of a straight edge | exact | exact |
| Area of a hole's cylinder face | exact | within 1e-4, relative |
| Radius of a hole's cylinder face | 2.75 mm | none given |
| Radius of a circle edge | 2.75 mm and 6 mm | 2.7499997 mm and 6.0000002 mm |
| Length of a circle edge | 17.2788 mm | 17.2078 mm, 0.16% to 0.41% short |
| Hole centre to hole centre | not a field | 35.9999999 mm |
| Plate top to plate bottom | not a field | 5.0 mm, angle 180° |
| Top of the upright to top of the plate | 65.00 mm between the planes | 65.28 mm between closest points |

The holes check reported 2 × 5.5 mm, which matches the topology's radius.

What follows from the table:

- **One pick needs no new data.** The readout shows the topology's facts, which are exact and already in the browser. There is no server call.
- **Two picks use the mesh**, except for two parallel planes. For those, the readout shows the gap between the planes, computed from the two centres and normals in the topology. Two faces that do not overlap show why both numbers matter: 65.00 mm between the planes against 65.28 mm between closest points. The readout names which one it shows.
- **An exact distance between two curved picks needs the kernel**, which means a server call. ADR-0013 defers it.

## How the tools live with picking, the fit ghost and the held and pushed faces

### Picking

**Read.** `web/src/features/viewer/selection.ts`: a click replaces the selection, a shift-click adds or removes a pick, a double-click picks the whole part, and Esc clears.

The readout follows the selection, so no click gains a new meaning and there is no measure mode. One face or edge shows its facts. Two show their distance and angle. Three or more, or the whole part, show no readout, and the size dimensions cover the whole part.

**Measured.** The readout fits above the selection hint at 1440 px ([screenshot](../review/viewer-tools-readout-two-faces.png)) and at 390 px ([screenshot](../review/viewer-tools-readout-two-faces-phone.png)). Both shots had the measure flag on, and both show the library's hover line under the hint. The app on `main` already draws that line, half hidden behind the hint ([screenshot from the selection PR](../review/select-1-face.png)). Step 1 hides it with one CSS rule on `.tcv_status_line`.

### The fit ghost

**Read.** `withFit` in `web/src/features/workspace/Stage.tsx` adds the context part's meshes under paths that start with `/fit`, coloured `#9aa7b4` at 0.22 opacity. `pickOf` ignores `/fit` paths, so a person cannot pick the context part, and the readout cannot measure from the variant to it. The clearance between the two belongs to the `fit` check.

**Measured.** With the ghost on, the viewer redraws the whole model on every render of the stage. Over 6 s with the cap and its ghost on screen, the viewer's draw counter (`data-draws`) went up by 8. With the ghost off, it went up by 0. On the scored bracket alone, it also went up by 0. A section set by script was gone within 0.5 s, because each redraw calls `viewer.clear()`.

**Read.** The cause is in `Stage.tsx`. `withFit` and `splitFaces` build a new `Shapes` object on each render, and `ViewerCanvas` calls `show()` whenever the object is new. The page renders each time a scorecard poll returns, about once a second.

Step 3 fixes both sides. `Stage` memoizes the shapes on the mesh, the ghost and the held and pushed faces. `show()` puts the section back after a real redraw.

### The held and pushed faces

**Read.** `splitFaces` in `web/src/features/viewer/where.ts` draws the faces where the stress check held and pushed on the part as two extra parts, `/variant/support` and `/variant/load`, each with the whole vertex set and only its own faces.

- **Inferred.** A section clips them with the part, because the clipping planes apply to the whole scene. Their stencil caps may draw wrong, because each one is a few faces and not a closed solid. Step 3 tests this. If the caps draw wrong, the overlays draw without caps.
- **Inferred.** The library's explode would move the overlays away from the part they belong to, because it moves each object group. The pull-apart in step 4 moves only the `/fit` group, so the overlays stay on the part.

### Picking while a section is on

The run did not test whether `idPicker.pickAt` returns faces that the section has cut away. Step 3 tests it. If it does, the engine ignores a hit on the cut-away side of the plane.

## What pulling apart means

**A single-part variant has nothing to pull apart.** It gets no control.

**A variant shown with a context part** gets a "Pull apart" toggle while the ghost is on. The toggle moves the context part away from the variant along the line between their box centres, by their overlap plus a gap, and fits the camera to both.

**Measured.** Moving the `/fit/variant/part` group 40 mm down in z and calling `viewer.update(true)` separated the cap from the bracket. The camera did not refit, so the bracket ran off the bottom of the canvas ([screenshot](../review/viewer-tools-pull-apart-context-part.png)).

**Measured.** A section often shows a fit better than pulling apart. The prototype cap was placed wrong in y. A section at x = 0 showed the cap's wall passing through the upright ([screenshot](../review/viewer-tools-section-with-context-part.png)). The `fit` check would report that as interference. The cap was never scored.

The library's explode is not used. It did nothing visible on either model, and it animates with its own slider bar.

## Where the extents numbers come from and how they are drawn

**Read.** `src/cad/checks/container/extents.py` measures the box with `BRepBndLib.AddOptimal(useTriangulation=False, useShapeTolerance=False)`. It reports `extent:x`, `extent:y` and `extent:z`, and `sorted_extent:smallest`, `middle` and `largest`, in mm. It reports sizes and no corner positions. It needs `closed_solid` to pass. The web app reads the result from `/v1/variants/{variant_id}/scorecard`, and `valueOf` in `web/src/features/workspace/cards.ts` shows it as "60 × 40 × 70 mm" in the "Size" row.

**Read.** The mesh's box, `shapes.bb`, comes from build123d's `bounding_box()` in `tessellate.py`. That is different code from the check's. Whether the two agree on curved outer surfaces is not settled.

**Measured.** On the bracket, the mesh box ran from (−30, 0, 0) to (30, 40, 70). That is 60 × 40 × 70 mm, the same as the check.

The lines are SVG over the canvas, with the numbers as DOM text. Each line runs along an edge of the mesh box, offset outward by 12% of the largest size. After each frame, `viewer.onAfterRender` projects the six end points to the screen again. DOM text stays sharp at any zoom, and a screen reader can reach it. **Measured.** A mock-up of this drew 60, 40 and 70 mm lines that followed the part as the camera moved ([screenshot](../review/viewer-tools-extents-dimensions.png)).

The rules:

- The numbers are the `extents` result's, never the mesh box's. The box only places the lines.
- The lines show only when the result for the variant on screen has passed. Pending, unknown or failed shows no lines.
- A caption reads "Size check". A "Dimensions" toggle in the stage's toolbar turns the lines on, and they start off.

## Controls

The stage's toolbar today holds the ghost toggle ("With bracket") and Download. The tools add:

- a **Dimensions** toggle, built like the ghost toggle, with `aria-pressed`;
- a **Section** toggle, which opens a small panel with the axis (x, y or z) and a slider for the plane's position;
- a **Pull apart** toggle, shown only while the ghost is on.

The panel uses base-ui's toggle group and slider, from `@base-ui/react` 1.9.0. Each gets one wrapper in `web/src/components/ui`, as the curated list requires. No new library is needed.

The engine stays the only module that touches the library. `Mounted` in `engine.ts` gains `section(plane | null)`, `pullApart(on)` and a way to project points after each frame. The readout's rules live in one pure function in `web/src/features/viewer/`, with unit tests.

## Accessibility and phone width

The readout is DOM text in a `role="status"` region, so a screen reader hears it when the selection changes. The dimension text is DOM text too, and the Checks card already lists the same size. Every control is a base-ui part with a visible label and keyboard support, and the slider moves with the arrow keys. **Measured.** At 390 px the readout fits above the hint. **Inferred.** Three more toolbar buttons will not fit beside Download at 390 px as text, so they need icons with labels, or they move into a menu. A phone has no shift key, so a person on a phone can reach only the one-pick readout. That limit belongs to the selection, not to these tools.

## Build steps

Each step is one PR and ends in something a person can see.

1. **The readout for the selection.** Hide the library's hover line. Add the pure function that turns one or two picks into lines, with the "≈" rule, the plane-gap rule and the "Measured on screen. Not a check." line. Draw it under the selection hint. Done when picking one face shows its area, and picking two parallel faces shows the gap between them, in the app and in a screenshot.
2. **The size check's dimensions.** Add the projection hook to the engine, the SVG overlay and the Dimensions toggle. Draw only on a passed `extents` result. Done when the bracket shows 60, 40 and 70 mm lines that follow the camera, and an unscored variant shows none.
3. **Sections.** Memoize the stage's shapes, and make `show()` keep the section across a redraw. Add `section()` to the engine, and the Section toggle and panel. Test picking while cut, and caps on the held and pushed faces. Done when a section through the cap and its ghost stays on screen while the page polls, and a click on a cut-away face does not select it.
4. **Pull apart.** Add `pullApart()`, the toggle and the camera fit. Done when the cap and the bracket separate and both stay in view.

Step 4 is the one to drop if the section in step 3 shows fits well enough.

## What the run did not settle

- Whether build123d's `bounding_box()` and the check's `AddOptimal` agree on a part with curved outer faces.
- Whether `idPicker` picks faces a section has cut away.
- Whether stencil caps draw right for the held and pushed faces.
- Why the library's explode moved nothing with a context part on screen.
- How three more buttons fit the toolbar at 390 px.
