# 0001 · Basic automates the lever and Advanced automates the fishing cycle

**Status** — Accepted. Shipped in v0.1.0.

## Context

The original automator combined hauling, unloading, and redeploying the net. That saved the player repeated trips to the winch and justified a late-game recipe and a substantial power load. An earlier upgrade could remove the need to watch the net while retaining manual collection as part of progression.

## Decision

Both variants operate the stock fishing winch and share the same live haul threshold, on-device automation switch, and native electrical connection. Each has a separate Engineering skill, item recipe, and built actor. The variant determines who unloads the stock drawer.

| | Basic | Advanced |
| --- | --- | --- |
| Engineering unlock | Character level 6, 1 skill point | Character level 10, 2 skill points |
| Alloy Frame / Conduit Wiring / Magnetic Coil / Logic Chip / Display Screen / Connector Ports | 2 / 2 / 1 / 1 / 1 / 1 | 4 / 3 / 2 / 2 / 1 / 1 |
| Base fabrication time | 20 s | 30 s |
| Catch storage | Stock winch drawer | Stock drawer feeds the built-in 50 kg cabinet |
| Operating load | 500 W | 500 W standby, 4 kW while automatically hauling or lowering, or transferring catch |
| Unload indication | Amber lamp while a raised and accessible drawer has catch and the powered cycle is waiting for the player | Cabinet LED gauge shows actual fill, transfer activity, and storage blockage |

Basic waits for the player to remove all items using the stock inventory. A partial unload leaves the drawer up. Advanced moves the catch with native inventory operations and can resume a blocked automatic unload after the player makes room. Both variants use the same rule for deciding when to haul. [Haul threshold](0003-live-net-capacity-and-haul-delay.md) · [Cycle completion](0004-manual-and-automatic-haul-completion.md)

## Consequences

Basic retains manual collection and stays viable with an early-game power supply. Advanced pays a higher construction and operating cost for unattended transfer. The two recipes and the shared Lua cycle let balance changes target the intended variant without duplicating the winch logic.

## Verification

The v0.1.0 gameplay check recorded both variants working. The Basic regression checks that partial unloading leaves the drawer up and verifies the 500 W load. The Advanced tests cover partial transfer and resumption after space becomes available. [Player guide](../../gamers/guide.md) · [Recipe definitions](../../../tools/construction_packages.py) · [Variant definitions](../../../src/ShipNetAutomation/Scripts/shipnet/variants.lua) · [Cycle tests](../../../tests/test_automation.py) · [v0.1.0 changelog](../../../CHANGELOG.md)
