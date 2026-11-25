# 0005 · Advanced transfers paced batches and verifies both inventories

**Status** — Accepted. Shipped in v0.1.0.

## Context

Instant transfer made the unloading animation meaningless. A separate failure occurred with 45 kg in the 50 kg cabinet and a full stack of 50 seaweed items. The native estimate offered the full stack as a destination, the write moved zero items, and later attempts selected the same slot. The player wanted visible transfers at about 5 kg/s, including partial transfers when only a little room remained.

## Decision

- Give a due poll one **1.25 kg** batch budget per **0.25 game seconds** of powered unloading. Carry forward unused budget for whole items, including a stack that needs several batches to fit the budget. Bound native transfers to eight calls per poll and drop accumulated budget when unloading stops. Late callbacks do not replay multiple missed batches.
- Resolve the live, unlocked stock drawer and its inventory from its winch. Resolve the destination from the attached Advanced actor. Validate actual barge or streamed-level ownership and the destination inventory owner before writing. A detached cabinet, unknown drawer, or unrelated inventory cannot become a substitute.
- Plan using remaining weight, valid slots, the item's maximum stack size, native add and split rules, and the amount of a whole item. Fill compatible partial stacks first during paced transfer, skip full stacks, and use an empty slot when needed. If the remaining cabinet capacity is below the next item's weight, continue through later source slots. A remaining weight of exactly one item's weight is usable.
- Transfer a stack with custom instance data, or a stack the game cannot split, as a whole. Coalesce ordinary stacks only when their identity, flags, and timestamp rules allow it. Preserve protected timestamps, while allowing the native refresh of ordinary timestamps.
- Use the game's `TransferSlot` with an explicit whole-item quantity. Check both inventories afterward for the count removed and received, item identity, custom bytes and fields, flags, and changes to unrelated slots. A confirmed unchanged pair can be inspected again later. An uncertain result disables automation and stops transfers and automatic lowering. The player can inspect both inventories and re-enable the cycle. Guard the cabinet against a reentrant transfer during a native notification.

## Consequences

A typical 30 kg drawer takes about six powered game seconds of transfer, in addition to the two cycle pauses. Whole-item sizes, stack boundaries, and interruptions affect observed timing. Unmoved items remain in their original drawer slots, and the next poll works from the live inventories. The same capacity inspection supports the cabinet-blocked indication. [LED status rules](0009-cabinet-led-status.md)

## Verification

A development check on a save copy filled 5 kg of cabinet space in four seaweed batches, and a separate test with 0.1 kg free skipped heavier items and took one 0.1 kg cloth scrap. Regression coverage includes exact fit, full stacks, indivisible data, protected timestamps, powered pacing, reentrant notifications, and unexpected changes after a transfer. [Cargo implementation](../../../src/ShipNetAutomation/Scripts/shipnet/automation_cargo.lua) · [Transfer tests](../../../tests/test_automation_cargo.py) · [Unconfirmed transfer test](../../../tests/test_automation.py#L320)
