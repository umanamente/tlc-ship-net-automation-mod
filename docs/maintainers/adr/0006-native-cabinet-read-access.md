# 0006 · The Advanced cabinet uses the stock inventory with Read access

**Status** — Accepted. Shipped in v0.1.0.

## Context

The Advanced cabinet is the destination for the catch. The player asked to keep it from becoming a target for the stock bulk-deposit shortcuts. An in-game check showed that Voyage's `Read` access hides and blocks both bulk actions while the game's individual-item interaction can still put an item into the cabinet. The player accepted individual deposits to keep the stock inventory window and its native interaction rules.

## Decision

- On binding the built Advanced actor, resolve its own native weight-limited inventory and set `Access` to `EVoyageInventoryAccessType::Read`.
- Route interaction with the casing to the stock inventory opened for that exact actor. The standard window owns backpack binding, item movement, and withdrawal.
- Treat **Deposit All** and **Deposit Similar** as unavailable. Keep **Take All**, individual withdrawals, and individual deposits through the game's normal window.
- Use the native slot-transfer path for automatic catch delivery. The cabinet can receive catch from the stock drawer while its player-facing inventory stays in Read mode.

## Consequences

Players can empty the cabinet quickly and continue using the base game's inventory controls. Read access expresses the bulk-deposit policy. Individual deposits consume the same real cabinet capacity as catch and affect the next automatic transfer. A strict output-only inventory would require a separate decision about the game's individual-item path.

## Verification

The stock-window check demonstrated that the bulk deposit commands were blocked while an individual item could still be deposited. A separate game check transferred 19 items weighing 8.5 kg into a Read cabinet, preserved its existing contents, and completed the fishing cycle. The storage tests check native inventory ownership and that player interaction opens the corresponding inventory. [Storage implementation](../../../src/ShipNetAutomation/Scripts/shipnet/device_storage.lua) · [Storage tests](../../../tests/test_device_storage.py) · [Transfer decision](0005-paced-and-verified-cargo-transfer.md)
