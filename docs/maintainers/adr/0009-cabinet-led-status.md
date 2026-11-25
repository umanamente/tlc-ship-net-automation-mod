# 0009 · The cabinet LED gauge shows fill, transfer, and blockage

**Status** — Accepted. Shipped in v0.1.0.

## Context

The filling strip needs to communicate the cabinet's weight independently of the catch in the net shown on the LCD. An actual blockage can occur below 100% when the cabinet has free weight but the remaining catch is too heavy, all compatible stacks are full, or no appropriate slot is available. An exact-full indicator would leave the player with a raised drawer and little indication of the cause.

## Decision

| Gauge state | Condition and display |
| --- | --- |
| Fill | Green segments show the ratio of actual cabinet weight to its current weight limit. |
| Transfer | During unloading, the lit segments turn yellow and a fading sweep runs left to right within the filled segment range. |
| Alarm | All segments pulse red if the cabinet has at most 2 kg of capacity left, or if the net is fully raised, the drawer is accessible, and none of its remaining catch fits. Red takes priority over transfer and fill. |

Calculate the first alarm threshold as the live cabinet capacity minus the 2 kg margin. For the stock 50 kg cabinet it begins at 48 kg. Use the cargo planner's live capacity assessment for the second condition, including weight, slots, and whether an item or stack can be split. This lets the blockage alarm work after a manual raise with the automation switch off.

Use the stock player-box LED material for the weight segments, the stock emissive pulse material for the alarm, and a panning material and light-trail texture for the transfer sweep. Lua selects the state and updates the filled segment range. The materials animate the pulse and sweep using GPU time. The separate Basic amber lamp reports that the powered cycle is waiting for the player to collect from the stock drawer. [Gauge implementation](../../../src/ShipNetAutomation/Scripts/shipnet/cargo_meter.lua) · [Alarm conditions](../../../src/ShipNetAutomation/Scripts/shipnet/fit.lua)

## Consequences

The player can identify a cabinet that needs attention while the net is still down or with a partial catch waiting on deck. The alarm clears when both conditions clear. The same fit rules drive the wait behavior and the indicator, and the cabinet's physical gauge keeps its role at either model LOD.

## Verification

The gauge tests check the sweep bounds on lit segments, red priority, a shared pulse material, fill geometry across weight steps, and a steady red fallback if the pulse material is unavailable. The cargo tests include full stacks, exact fits, and later items that fit after a heavier item is skipped. [Gauge tests](../../../tests/test_cargo_meter.py) · [Cargo tests](../../../tests/test_automation_cargo.py) · [Transfer decision](0005-paced-and-verified-cargo-transfer.md)
