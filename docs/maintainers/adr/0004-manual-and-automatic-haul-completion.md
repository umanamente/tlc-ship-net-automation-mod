# 0004 · Manual and automatic hauls have different completion conditions

**Status** — Accepted. Shipped in v0.1.0.

## Context

The stock lever remains available for pulling up an early catch or taking over the winch. A player-requested raise should let Advanced help with unloading even if automation is off. An unattended automatic haul should wait for cabinet space when some catch stays in the drawer.

## Decision

Recognize an observed stock-lever raise separately from acknowledgement of a command sent by the automator. On a manual raise, adopt the operation and wait for the real drawer even if the net still appears deployed on that poll. Treat a manual lowering action as the player's override and pause enabled automation. Resume it through the device switch.

The stock drawer is ready only when the net reports `FullyRaised`, the drawer permits interaction, and the lock is open. Advanced waits `BEFORE_UNLOAD_SECONDS` (1 game second) after observing that ready state before starting transfer. Basic waits for the player's unload. Automatic lowering uses a separate `BEFORE_LOWER_SECONDS` (1 game second) when the cycle reaches its lowering step. For an automatic Advanced haul, a cabinet-space wait can overlap this delay after the drawer empties. Loss of drawer access clears the corresponding observation timers. The next automatic action still requires power. [Cycle implementation](../../../src/ShipNetAutomation/Scripts/shipnet/automation.lua)

| Scenario | Completion |
| --- | --- |
| Basic enabled | Wait for the accessible stock drawer to be empty. A partial unload keeps it raised. |
| Basic disabled | The player operates the lever and collects independently of the automator. |
| Advanced after an automatic haul | Transfer the fitting catch. If some remains and none fits, hold the net up and resume when the player makes room. An empty drawer can redeploy once the cabinet has space for the next cycle. |
| Advanced after an observed manual haul, automation on | Transfer the fitting catch. The net can redeploy with a remainder when no further catch fits. The remainder stays in the stock inventory. |
| Advanced after an observed manual haul, automation off | Use power while transferring the fitting catch, then leave the drawer raised. A disabled cabinet loaded beside an already raised drawer waits for a new manual haul. |

## Consequences

The player can call for a collection at any catch weight. A manual haul can end with catch still in the stock drawer, which is intentional. For automatic hauling, a full or blocked cabinet is a wait condition. Recovery uses the actual drawer and cabinet contents after reload.

## Verification

The tests exercise manual raises with automation on and off, manual lowering, both delays and their reset on lost drawer access, reload in the raised position, and redeploying after a manual haul with leftover items. [Cycle tests](../../../tests/test_automation.py) · [Manual haul with remainder](../../../tests/test_automation_cargo.py#L123)
