# 0012 · One verified release ZIP carries game compatibility to GitHub and Nexus

**Status** — Accepted. Shipped in v0.1.0.

## Context

A Steam update can change the game build without changing the mod's version. The game used to cook a package and the game used to validate a candidate can also differ. Publishing independently built ZIPs to GitHub and Nexus would make it harder to prove which payload was tested or recover a failed upload.

## Decision

### Record the cook and gameplay test identities

- Capture the short project version from `VoyageBlueprintLibrary.GetProjectVersion()` and the full numeric release from the active `SentrySettings.Release` when it matches the project version. The Steam app manifest supplies the BuildID. The runtime report can fall back to the project version when the game supplies only that value.
- Keep the cook identity in `native/build-manifest.json`. Record successful gameplay validation in `mod.json` against the runtime fingerprint. Each identity contains the game version, project version, Steam app ID, and BuildID. For v0.1.0, the cook and gameplay check both used game version **0.10.0.653173**, project version **0.10.0**, and Steam BuildID **25982825**.
- After exercising the candidate in-game, validate the report's mod version and installed Steam build and compare the installed runtime files with the repository candidate. The fingerprint covers runtime Lua, meshes and layouts, the mod enable file, and Unreal packages and descriptor. It normalizes the version declaration in `main.lua` so stamping the release number preserves the validated fingerprint. Runtime changes require fresh gameplay evidence. The same runtime can accumulate tested game builds after further gameplay checks.
- Require at least one matching gameplay validation record for the release ZIP. Write the cook and tested game identities into the version's changelog entry, GitHub Release notes, and the ZIP's `BUILDINFO.json`. Preserve previous tagged entries as the compatibility record for those versions.

### Publish the same artifact twice

- Start public history from the curated v0.1.0 source snapshot and tag. For later releases, plan from CI-validated `main` using Conventional Commits. `fix` and `perf` produce a patch, `feat` a minor, and a breaking change a major. An ordinary revert produces a patch. Documentation-only commits can pass CI without bumping the mod.
- Check and package the stamped candidate, publish its ZIP and SHA-256 sidecar to GitHub Releases, then have the Nexus job download that exact ZIP and verify its digest. The job uses the configured Nexus mod and file group, with the API key held in the `nexus` Actions environment.
- Publish the ZIP as the main Nexus file in the existing group and archive the previous version. The v0.1.0 bootstrap can replace an explicitly identified preview carrying the same version. On retry, reuse a confirmed main file for that version, refuse older versions if a newer main file exists, and append only changelog lines missing on Nexus. Verify an uncertain response by reading the saved entry before making any further publication attempt. An existing stable tag can be retried through the Release workflow.

## Consequences

The cook and test records can evolve independently, and the compatibility history identifies the game build on which each released payload was exercised. A packaging or publication retry uses the tagged version and the checked GitHub ZIP. The Nexus page's visibility is controlled separately from file upload.

## Verification

The v0.1.0 changelog records gameplay validation of Basic and Advanced. The first GitHub ZIP matched the locally checked candidate byte for byte, and the Nexus job verified its main file and changelog. Automated tests cover stale build reports, the version-normalized fingerprint, changelog preservation, release planning, Nexus bootstrap previews, and rejection of an older publication. [Release instructions](../releases.md) · [Gameplay record](../../../CHANGELOG.md) · [Runtime identity reader](../../../tools/game_build.py) · [Release workflow](../../../.github/workflows/release.yml) · [Release tests](../../../tests/test_release_metadata.py) · [Nexus tests](../../../tests/test_nexus_release.py)
