# Asset pipeline

## Blender exports

The two masters in **3d_models/** contain the near geometry, pivots and source lettering. `tools/export_rail_model.py` generates an LOD0 and LOD1 **.snm** per controller. A second export with **SHIPNET_MARKINGS_DIR** enabled emits the letter contours. `tools/build_markings.py` bakes them into **artwork/models/winch-markings.png** using the placement in **printed_labels.layout**. The master files remain editable and the scripts write generated files.

## Unreal packages

`tools/build_construction.py` reads the exports, layout files, catalogue icons, palette, native recipe definitions and local game templates. It creates the mod's cooked packages using the Voyage build tools and reads the serialized resources back for verification.

- The **.pak** contains the catalogue's **AssetRegistry.bin**.
- The **.utoc** contains the IoStore index and the **.ucas** contains the packaged resource data.
- The **.uplugin** is a text descriptor shipped with the package set.

The builder extracts selected templates locally, then verifies the allowlist of output packages. Keep extracted game files and the full game type dump out of the repository. The output includes derived Unreal resources, including construction assets built from game templates. Review those resources and the media before their first public distribution.

## Manifest and game identity

`native/build-manifest.json` stores individual SHA-256 fingerprints for inputs and outputs of both stages. It also records the project version and Steam BuildID used for the cook, hashes of the relevant game indexes and JMAP, Blender version, Python/Pillow/cityhash versions and hashes of the tool executables.

UE4SS reads the short project version from **VoyageBlueprintLibrary.GetProjectVersion()** on the game thread. The active **SentrySettings.Release** object carries the full release string. The mod reads that local metadata and records the numeric release when it matches the project version. For the reference build, the report contains **0.10.0.653173**, project version **0.10.0**, and Steam BuildID **25982825**. If the running game exposes only the project version, the report records that value after a short retry period. [Channel37 release notes](https://steamcommunity.com/app/1783560/discussions/0/564797030489213918/)

When Steam updates, capture the new identity and regenerate the JMAP if you are recooking. The wrapper checks the BuildID at the start and end of the cook. A gameplay check with the existing packages can document compatibility with a newer build in **mod.json**, while the manifest continues to report the original build provenance.

## Verification

Run `python tools/native_assets.py check` on any clean clone. A changed Blender input requires a local export. When the exported files are unchanged, the wrapper can retain the packages. A changed Unreal input or game source triggers local regeneration of the package set. Lua-only, README and media changes use the checked-in packages. The ZIP packer verifies the manifest and the contents of the completed archive.
