# 0010 · Both models use two authored LODs and one printed-markings atlas

**Status** — Accepted. Shipped in v0.1.0.

## Context

The model review found substantial visible geometry in printed lettering, fasteners, and hinges. Basic's five printed labels alone took 4,336 triangles in dev.37. The model needs to preserve its mechanical silhouette, readable markings, lit display, and moving parts while reducing geometry and material sections at normal playing distances.

## Decision

- Keep editable lettering and near-model detail in the two Blender masters. Use part-specific export rules for LOD0 and LOD1 so the silhouette, hinge and drive pivots, and visible mounting surfaces survive simplification. Reduce screws, rings, and hinge details where their thickness is below the useful projected size.
- Bake the printed lettering from Blender contours into one **512 × 256** shared atlas with mipmaps that preserve ink coverage. Apply it on both LODs. The five Basic markings use 10 triangles, and the Advanced power marking uses two. The live LCD retains the dynamic text, readouts, and control.
- Cook both meshes into the construction preview's native Unreal `StaticMesh`. The preview uses Unreal's LOD selection with the LOD1 screen-size threshold at 0.25.
- Built devices render procedurally. Estimate their projected size from the actual camera, field of view, and viewport aspect ratio. Prepare the distant geometry below 0.36, switch when it is ready and the size drops below 0.22, and return to near geometry above 0.28. The different thresholds avoid repeated switching at the boundary. Close screen interaction forces the near LOD. Preserve pose, collision and interaction geometry, world screen, and indicators across the visual swap. Keep the near model usable if the distant upload fails.

## Consequences

The dev.38 review measured the following triangle counts for the visible operating device with a live LCD. The stock socket and cable were counted separately.

| Device | dev.37 | LOD0 | LOD1 |
| --- | ---: | ---: | ---: |
| Basic | 16,586 | 8,102 | 4,044 |
| Advanced | 22,791 | 15,780 | 6,304 |

Both distant models use seven visible draw sections. The geometry and section reductions are reproducible. A short game run on an RTX 5090 Laptop showed lower median frame times for the Advanced samples but a worse distant p95. The observations establish the geometry savings and leave performance on midrange hardware unmeasured.

## Verification

Both transitions and the close-view display were checked in-game on a save copy. Automated tests inspect the cooked LOD buffers and material sections, preserve pose and targeting across swaps, and exercise fallback after a failed distant upload. [Blender exporter](../../../tools/export_rail_model.py) · [Atlas builder](../../../tools/build_markings.py) · [Cooked geometry](../../../tools/build_construction_mesh.py) · [Runtime LOD](../../../src/ShipNetAutomation/Scripts/shipnet/model.lua) · [Construction meshes](../../../tests/test_construction_mesh.py) · [Runtime model tests](../../../tests/test_rail_model.py)
