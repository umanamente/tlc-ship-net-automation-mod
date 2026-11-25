# 0003 · Automatic haul follows live net capacity after the catch settles

**Status** — Accepted. Shipped in v0.1.0.

## Context

A nominal 30 kg net could stop at about 29.9 kg, leaving an exact-full trigger waiting indefinitely. Net capacity may also change between saves or while playing, including through other mods. A fixed 29 kg trigger would reproduce the problem at different capacities. The delay gives the net a chance to keep catching and preserves the intended pacing.

## Decision

1. While the enabled cycle observes a deployed net, read the stock inventory's total weight and current maximum weight. The ordinary weight poll uses the inventory's aggregate readings, without enumerating slots or depending on the winch actor's cached weight.
2. Start a 3-game-second confirmation window when catch is positive and at or above `max(0, capacityKg - 1)`. This yields 29 kg for a 30 kg net and 299 kg for a 300 kg net. At a positive capacity of 1 kg or less, a net still needs a positive catch before the timer starts.
3. Restart the window on any measured increase over the preceding reading, including a fractional increase on the deadline. A decrease that leaves a positive catch at or above the current threshold keeps the window. An empty net, a reading below threshold, missing or invalid measurements, and a nonpositive capacity clear it.
4. After the window, use fresh readings and the live winch state. Advanced also requires a valid cabinet with room for some of the current catch. Either variant requires operating power before requesting a haul.
5. Keep the margin and delay in shared Lua constants. Recalculate the threshold from current data every check. Loading a save or restarting the cycle begins with a fresh observation window.

## Consequences

A single rule handles both variants and nonstandard net sizes. Display rounding does not affect the trigger. Repeated growth intentionally postpones hauling. Loss of valid input leaves the cycle waiting for a new qualifying reading.

## Verification

The tests cover capacity changes in both directions, fractional growth at the deadline and while waiting for power, a decrease within the window, empty and small nets, missing readings, and a fresh timer after reload. The cargo tests check that the weight poll reads live aggregates without walking the inventory. [Cycle code](../../../src/ShipNetAutomation/Scripts/shipnet/automation.lua) · [Cycle tests](../../../tests/test_automation.py) · [Cargo tests](../../../tests/test_automation_cargo.py)
