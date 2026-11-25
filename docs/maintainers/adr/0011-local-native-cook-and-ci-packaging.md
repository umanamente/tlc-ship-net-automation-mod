# 0011 · Unreal assets are cooked locally and CI packages them with Lua

**Status** — Accepted. Shipped in v0.1.0.

## Context

Voyage's native catalogue, research, construction, and visual assets are built against specific game templates and a matching JMAP. Cooking depends on a local Steam installation and the Voyage-compatible tools. The public repository also needs to produce an installable ZIP from a clean checkout and detect when a hand-edited Blender master, generated export, or cooked package is stale.

## Decision

Keep the editable Blender masters in `3d_models/`. Commit the exported meshes and markings atlas, the cooked Unreal package set, its plugin descriptor, and `native/build-manifest.json`. Native resources supply the catalogue, research, and construction definitions. Lua implements live automation, device interaction, and diagnostics. The player ZIP carries both layers from the same checkout.

| Stage | Inputs and outputs | When to repeat it |
| --- | --- | --- |
| Blender export | Both `.blend` masters, part-detail and export scripts, and the marking layout and atlas builder. Produces four `.snm` meshes and a shared PNG atlas. | When an export input changes. Identical output hashes can preserve the current cook if the rest of its inputs and provenance still match. |
| Unreal cook | Exports, layout and palettes, icons, descriptor, recipe and construction builders, game templates and reflection data. Produces a matching `.pak`, `.utoc`, and `.ucas` set. | When a native input, reference game, JMAP, or recorded toolchain changes, an output is stale or missing, or a rebuild is forced. |
| ZIP assembly | Current Lua, runtime meshes and layouts, verified native packages and descriptor, install documentation and build metadata. | For a distributable candidate or release. Lua-only and documentation changes can use the checked-in cook. |

Track per-file SHA-256 fingerprints for both stages' repository inputs and outputs. The `.pak` holds the catalogue asset registry, while the IoStore index and data live in `.utoc` and `.ucas`. A given cook can reproduce some of the previous files byte for byte. The workflow still verifies them as a complete set. The manifest records the actual game identity used for the cook, hashes of the selected game indexes and JMAP, and tool versions or executable hashes. Tool binaries, extracted game files, and reflection dumps stay in the local environment.

Run the local rebuild in a scratch tree using a matching runtime version report. Before accepting the new outputs, confirm that Steam BuildID and repository inputs stayed stable during the build. CI runs the asset checker and reports the exact path for a missing or stale entry. The packer repeats the manifest check, uses stable ZIP entry metadata, and rereads the ZIP to verify member contents.

## Consequences

CI can produce and verify a player ZIP without a Steam installation. Asset contributors carry the source changes, affected generated outputs, and updated manifest together. Compatibility testing an existing package on a newer Steam build can expand its supported build record while retaining the original cook provenance. [Release compatibility decision](0012-release-compatibility-and-distribution.md)

## Verification

Initial release preparation verified a byte-identical ZIP from a clean clone. The manifest regression detects an edited Blender input and a missing binary. The documented check and rebuild commands use the same fingerprint rules. [Asset pipeline](../asset-pipeline.md) · [Local rebuild](../development.md) · [Asset verifier](../../../tools/native_assets.py) · [ZIP builder](../../../tools/package_mod.py) · [Manifest test](../../../tests/test_native_manifest.py)
