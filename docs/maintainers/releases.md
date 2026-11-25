# Releases

## First release

1. Prepare the public source snapshot and confirm the intended asset and media inventory.
2. Use [local development setup](development.md) to recook assets and run the clean-clone checks. Build the candidate ZIP.
3. Install the candidate and complete the [gameplay checks](testing.md). Record the verified game identity with `python tools/game_build.py --game-root $game --record-tested`. The command checks the runtime report against the candidate version, the installed runtime files and the local Steam manifest and updates the first release changelog entry while it is a draft.
4. Rebuild the ZIP and verify its checksum. Amend the local initial commit with the final compatibility record before tagging it. The compatibility record is included in `BUILDINFO.json` in the ZIP.
5. After authorization to publish, create the empty GitHub repository `umanamente/tlc-ship-net-automation-mod`, configure the Nexus environment below, then push the initial commit and annotated tag `v0.1.0` together. CI publishes the checked ZIP and SHA-256 to GitHub Releases, then uploads the verified ZIP to Nexus. Use the **Release** workflow with an existing tag to retry a failed publication.

## Subsequent releases

CI validates the asset manifest, runs tests and builds the ZIP. After passing CI on main, the release workflow uses Conventional Commits and semantic-release to plan a patch for `fix`/`perf`, a minor for `feat`, and a major for a breaking change. The release workflow writes the build and gameplay-test identities into the new changelog section, reruns the checks on the stamped release, and publishes that section as the GitHub Release notes with the ZIP and checksum.

Every release entry lists the full game version and Steam BuildID used to build the native packages and the full versions and BuildIDs used for gameplay testing. The ZIP includes the same data in BUILDINFO.json. Tagged entries record the compatibility of that release.

The release keeps test results linked to the Lua and Unreal payload that was installed for testing. A SemVer stamp leaves this fingerprint unchanged. If the runtime payload changes, record a new gameplay check before release. A newer Steam BuildID can be added after testing the existing packages. A new native cook records its own BuildID and project version in the build manifest.

## Nexus Mods

Set `NEXUSMODS_API_KEY` as a secret in the GitHub Actions environment `nexus`. Set `NEXUSMODS_MOD_ID` and `NEXUSMODS_FILE_ID` from **Files → Advanced** on the [Nexus mod](https://www.nexusmods.com/thelastcaretaker/mods/454). For the initial release, `NEXUSMODS_BOOTSTRAP_PREVIEW_ID` identifies the existing preview that has the same version label.

The Nexus job checks the downloaded GitHub ZIP against its SHA-256. It uploads the same ZIP to the existing main file group and archives the previous version. It verifies the uploaded version and fills in missing changelog lines without repeating lines already present. The mod page has its own publication control. [Nexus launch media](../../artwork/branding/nexus/) is tracked separately from the player ZIP.
