# 0013 · Advanced hauls when catch can fill the cabinet and redeploys with room in the net

**Status** — Accepted.

## Context

Another mod can increase the stock net's capacity while the Advanced cabinet still holds 50 kg. With a 300 kg net, the near-full trigger in [ADR 0003](0003-live-net-capacity-and-haul-delay.md) can make a player wait for 299 kg of catch before a cabinet that started empty receives anything. The original completion rule in [ADR 0004](0004-manual-and-automatic-haul-completion.md) can then hold up a net that still has room to fish.

## Decision

- While Advanced is enabled and the net is deployed, read the stock drawer's live weight and capacity and the mounted cabinet's remaining weight space. When the cabinet has positive free weight at or below the catch weight, confirm that at least one item actually fits and request a powered haul on that poll. This trigger also accepts equal weights. The near-full trigger retains its three-game-second confirmation window and checks that some catch fits before hauling.
- When the raised stock drawer is accessible, transfer fitting items in verified batches at 5 kg/s under [ADR 0005](0005-paced-and-verified-cargo-transfer.md). Continue until the drawer is empty or no remaining item fits. Whole items, stack limits, and available slots determine whether the cabinet can reach its exact weight limit.
- If automation is enabled, redeploy when the drawer is empty or when no remaining item fits and the catch is below its live near-full threshold (`max(0, capacityKg - 1)` for a positive catch). Leave any remainder in the stock drawer. Apply the normal lowering delay and power check. If a transfer becomes possible again before lowering, resume it first.
- If catch remains at or above the near-full threshold and the cabinet cannot receive it, keep the net raised and resume unloading when there is room. Use current inventory measurements after reload. Unavailable inventories and unconfirmed transfers keep their existing protective behavior.
- The same completion rule applies after an automatic or manual haul while Advanced is enabled. An observed manual haul with automation off still transfers what fits and leaves the drawer raised. Basic continues using the near-full trigger and requires the player to empty the drawer before lowering.

## Consequences

An Advanced unit with 55 kg of catch in a 300 kg net can fill an empty 50 kg cabinet and then return to fishing with 5 kg still in the stock drawer. A full cabinet prevents another haul for that catch until there is room for a transfer.

## Verification

Automated regression coverage includes the exact cabinet-space boundary, a blocked transfer despite free weight, redeployment with a remainder, the live near-full threshold, and the power check before redeployment. [Cycle tests](../../../tests/test_automation.py) · [Cargo tests](../../../tests/test_automation_cargo.py)

On an isolated save using game version `0.10.0.653173` (Steam BuildID `25982825`, UE4SS `527a483b`), a net set to 300 kg hauled 55.5 kg, filled the 50 kg cabinet, and lowered with 5.5 kg left. Stock fishing then added 0.5 kg of copper scrap while the cabinet stayed full. In a second run on the same save, a raised net at 299.5 kg waited for cabinet space, unloaded 5 kg when space became available, and lowered with 294.5 kg left.
