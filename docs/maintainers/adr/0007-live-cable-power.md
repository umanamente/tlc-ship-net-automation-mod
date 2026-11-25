# 0007 · The working cycle requires live power through the stock cable

**Status** — Accepted. Shipped in v0.1.0.

## Context

A saved electrical cable could still be attached when the native grid had yet to restore supply. In isolated cold loads, restoration took about 20–31 seconds, and reconnecting a plug in the player's game appeared to wake the device. A charged receiver with a loose cable or an exhausted source could also give a misleading indication of available power. The automator needs evidence of delivery through the live network before it spends power on work.

## Decision

- Use the stock `POWER IN` socket and native electricity receiver. The receiver references its own variant's catalogue item so the socket tooltip uses the device name.
- Validate the receiver, its owner, and the reciprocal cable connection. Record energy received on that route as credit and authorize an interval only when the native debit succeeds for the required amount. A saved buffer keeps the display available but supplies no initial work credit for a new route. If a full stale buffer would prevent delivery, free only the headroom needed for the interval so the source can demonstrate supply. Route accounting also works through passive junctions.
- Use the 250 ms game-thread scheduler and bill by elapsed game time. Cap the billed interval at one second so an unload, map transition, or long callback gap does not cause a large backdated debit. The first observation opens the receiver for supply. Basic draws 0.5 kW during an enabled cycle. Advanced draws 0.5 kW in standby and 4 kW in active mode. Follow actual cable travel when deciding whether the motor is still lowering the net.
- Once both plugs are recognized, wait 0.5 seconds of game time without incoming energy before requesting `ConnectionsChanged()` on the receiver and its initialized upstream neighbour. Request the native refresh once for that route and keep the cable attached. The original delay was three seconds. The shorter grace interval reduces an avoidable startup wait, while actual delivery still depends on the game's grid. Log the connection wait, refresh, and confirmed supply as distinct events.
- Enable automation on newly fabricated devices and use the saved state for devices loaded from a save. With the switch off, an empty receiver may accept supply to restore the display. After it receives charge, the idle receiver stops accepting energy again. An observed manual Advanced haul can still draw power to transfer catch under its own cycle rule. [Manual haul completion](0004-manual-and-automatic-haul-completion.md) · [Display recovery](0008-world-space-lcd.md)

## Consequences

A disconnected or dead source leaves the cycle waiting even when the receiver contains charge. A brownout pauses powered work, and recovery continues from actual winch and inventory state. A connected but unpowered route can request a native recheck without repeated refreshes or a mandatory cable replug.

## Verification

An isolated dev.17 cold load regained supply through the saved cable, and an induced upstream interruption caused a single refresh. Automated regressions cover delayed connection, passive junctions, an empty source, stale buffer headroom, brownout, off-state display recovery, and independent devices. [Power code](../../../src/ShipNetAutomation/Scripts/shipnet/automation_power.lua) · [Power tests](../../../tests/test_automation_power.py) · [Cycle timing](../../../src/ShipNetAutomation/Scripts/shipnet/automation.lua)
