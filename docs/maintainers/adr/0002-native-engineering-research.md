# 0002 · Construction requires native Engineering research

**Status** — Accepted. Shipped in v0.1.0.

## Context

Development builds dev.7–11 placed one Advanced build recipe directly in the character's Vault to make the fabrication workflow testable. Removing the automatic grant from the current Lua code would leave previously granted recipes in old saves. The progression decision was to require research before the next build on those characters as well, while keeping already-built devices usable with their contents.

## Decision

- Cook a registered Voyage Skill and Item for each variant. The native Engineering skill grants the item recipe through the game's ordinary research and Build menus. Basic requires level 6 and 1 skill point. Advanced requires level 10 and 2 points.
- Treat the local character's learned skill as the authority for construction. Check it during placement and again when confirming fabrication. A legacy Vault entry or stale selection cannot authorize another build.
- Reconcile the Vault only when its owning player state, world, registered assets, and inventory are ready. Remove the old recipe entry when the skill is absent. Restore a missing recipe if the skill is already learned. Leave a matching skill and recipe pair untouched. Recheck the local player after asset resolution because loading an asset can dispatch callbacks or change the world.
- Load and validate the registry through catalogue reconciliation. The placement callback queries the already-resolved skill without synchronously loading a package inside the Blueprint VM.

## Consequences

The character pays the intended progression cost for future construction. Reconciliation repairs recipe knowledge without touching placed automators, their operating state, or their inventory. The cooked Skill and Item are required together for native progression.

## Verification

Registry tests check independent Skill and Item enumeration for both variants. Catalogue tests cover a fresh player, old-save and Vault load ordering, a missing skill or Vault, and travel during asset resolution. The gameplay checklist covers learning and building both recipes. [Catalogue code](../../../src/ShipNetAutomation/Scripts/shipnet/build_catalog.lua) · [Placement checks](../../../src/ShipNetAutomation/Scripts/shipnet/build_placement.lua) · [Catalogue tests](../../../tests/test_build_catalog.py) · [Registry tests](../../../tests/test_skill_registry.py) · [Gameplay checklist](../testing.md)
