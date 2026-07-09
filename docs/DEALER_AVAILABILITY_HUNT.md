# Dealer Availability Display — Narrowed Target + Catalog Correction

**Date:** 2026-07-08
**Status:** narrowed & downgraded (no longer correctness-critical — see §3)

## 1. Catalog stride correction (important)

The runtime vehicle catalog at `[0x006E0170]` has a **0x1C (28) byte** stride,
**not 0x54**. Live-verified: 0x1C yields exactly 94 sequential entries
terminated by a null name pointer, in the game's natural order
(`vp_eclipse_04`, `vp_jetta_03`, `vp_srt4_04`, …). The prior 0x54 value was
`3 x 0x1C`, so `vehicles()` read every 3rd entry and walked off the array end.

Symptom this explains: the Scion tC was reported at "catalog index 23" in
earlier docs. 23 = 69 / 3 — an artifact of the 3x stride. **True indices:**

| Vehicle | true index (0x1C) | old wrong index (0x54) |
|---|---:|---:|
| `vp_is300_04` | 4 | 12 |
| `vp_d_scion_tc_05` | 69 | 23 |

mcVehicle entry layout (partial, 0x1C bytes):
- `+0x00` u32 name pointer (`vp_*`)
- `+0x04` u32 (small int — category-ish: 0,1,2,…)
- `+0x08` u32 class/rank (is300=0, tC=0, some=5/6)

**Why it matters for the deny gate:** the game resolves a purchase's vehicle to
an index via `0x004AF870` → `0x004B2AE0(name)`, which returns the index into
*this* 0x1C array. The permit table is indexed the same way, so `vehicles()`
had to use 0x1C or `set_vehicle_permits` would have written the wrong permit
byte. Fixed in `mc3api/vehicles.py`.

## 2. Availability display — where the lock state is computed

"Locked" strings (`0x0065134D`, `0x0065137B`, …) have **no lui/addiu code
xref** — they're pulled from a text table by the renderer, confirming the
showroom Locked/Available/Owned state is computed and pushed into the Flash UI
(`toplevel.swf`), not stored as a flag (matches LAYER3_STATUS).

Narrowed to the showroom item-display function:

| Address | Role |
|---|---|
| `0x00329480` | **Showroom item-detail updater.** Resolves the selected vehicle via `0x004AF870` → 0x1C catalog entry `[0x006E0170]+idx*0x1C`; reads attribute fields (`+0x08` class/rank); dispatches on screen-mode `[ctx+0x1B4]` (values 24/25/31/39); calls UI helpers `0x004AF2D0` and `0x004B5B08` to push per-item strings/state into the Flash list. |
| `0x004AF2D0` / `0x004B5B08` | UI list/property helpers used to populate showroom items. |
| `0x003346E0` | "InShowroom" navigation handler (reads garage count, `oktobuy`, `selected2`). |
| `0x00324E18` | Shop-context constructor (allocates `ctx+0x71C` record array, `ctx+0x720`, etc.). |
| `0x003331E8` | Reads the *selected* item's UI state back (state 3 = owned) — a consumer, not the producer. |

The exact predicate ("is vehicle N purchasable for this player") is computed
from the mcVehicle class/rank (`entry+0x08`) plus career progression, then a
UI string/state is set per item. Pinning the precise branch and a safe hook
point is the remaining work; it is a good candidate for a live write-watch on
the `0x004B5B08` call with the dealer open (the one place a debugger trace still
helps), or deeper static work through `0x004AF2D0`.

## 3. Why this is now downgraded (not blocking)

With the **purchase deny gate** built (`0x003378BC`, permit table), AP can
already prevent *buying* a non-permitted car through the game's own cancel path
(`oktobuy=0`), even while that car still visually shows as purchasable. So the
availability-display override is **cosmetic polish**, not AP correctness:

- Correctness (can't acquire a locked car): handled by the deny gate. ✅
- Detection (knowing a purchase happened): handled by the detect hook. ✅
- Ownership checks: handled by `garage_vehicles()`. ✅
- Display (locked car shown greyed-out instead of buyable-then-cancelled):
  this hunt. Nice-to-have.

Recommended sequence: graduate the deny gate live first (it delivers the actual
lock); return to the display override only if the buyable-then-cancelled UX is
worth the extra hook.
