# MC3 — Dealer Purchase Flow, Static Analysis Breakthrough

**Date:** 2026-07-08
**Target:** SLUS-21355, CRC 0x60A42FF5
**Method:** static xref + MIPS disassembly over cached ELF image (`tools/static_xref.py`,
`tools/mips_disasm.py`), anchored on the public cheat "Money Doesn't Decrease When Buying
Cars" (`0x00337A9C`) and the money-writer lead from LAYER3_STATUS. No debugger, no gameplay.

## TL;DR

- **Garage ownership is SOLVED and live-verified.** Static array at `0x006E0900`
  (30 × 0x104-byte carCfg slots), count u8 at `0x006E08FC`, vehicle name c-string at
  slot+0xDF. Empty slots hold the literal name `"blank"`. Verified live: count=2,
  slot 0 = `vp_d_scion_tc_05`. Exposed as `MC3Game.garage_count` / `garage_vehicles()`.
- **The full dealer purchase-confirm flow is mapped**, with two safe JAL hook sites:
  one for purchase *detection* and one for purchase *denial* (AP Vehicle Permit gate).
- The game UI is **Flash/Scaleform-style** (`toplevel.swf`); native code exchanges named
  events/properties with it (`oktobuy`, `Fortune`, `CurrentVehicle`, `choice1` …). The
  showroom "Locked" display state is pushed into the UI when the list is built — that
  writer is the one remaining unknown for the availability override.

## Confirmed structures (live-verified)

| What | Address | Notes |
|---|---|---|
| Garage manager struct | `0x006E0398` | static, not heap |
| Garage count | `0x006E08FC` (u8) | = mgr+0x564, cap 30 (checked in buy path) |
| Garage slots | `0x006E0900` | = mgr+0x568, `carCfg[30]`, stride **0x104** |
| carCfg vehicle name | slot+**0xDF** | c-string `vp_*`; `"blank"` when empty |
| Per-vehicle career records | `0x006E87F4` | = mgr+0x845C, stride **0x1BC**, indexed by catalog index; +0x04 updated by SpendMoney with the spend delta |
| Shop wallet alias | `[[0x00619E00]+0xC]+0xAC0` | == `0x00800870` (known wallet) |

Note: the currently equipped vehicle (starter car) is NOT in a garage slot — count=2 but
only the tC name appears. The active car's carCfg lives in the profile (MC3CarRandomizer's
`profile→carCfg` path).

## Function map (static, high confidence)

| Address | Role |
|---|---|
| `0x00337610` | **"shop" screen native handler** (huge; buy confirm, money, memcard save, test drive). Strings: `shop`, `oktobuy`, `Fortune`, `updateMoney`, `CurrentClass`, `CurrentVehicle`, `choice1`, `selected1/2`, `fromshop`, `fromtestdrive`, `toplevel.swf` … |
| `0x00337378` | **SpendMoney(shopCtx, newTotal)**: reads wallet, delta = old−new, updates per-vehicle career record (+0x04), sets save-dirty flag; caller then stores newTotal to the wallet at **`0x00337A9C`** (`sw a3,0xAC0(v0)`) — exactly the instruction the public cheat NOPs. |
| `0x003331E8` | **oktobuy tri-state sender**: UI list-item state 3 = owned → `ID_Error_Owned`; `[0x006E08FC]` ≥ 30 → `ID_Error_Too_Many_Owned` (oktobuy=2); else `CF_Purchase_Showroom` confirm (oktobuy=1); `ctx+0x734` ≠ 0 (busy/saving) → oktobuy=0. |
| `0x003325C8` | **Purchase commit**: copies selected carCfg `[ctx+0x71C+sel*4]` into garage slot via `0x004ADDE0`, sets dirty, requests career save. |
| `0x001B00B8` | **RequestSaveCareerData** (career event 101, string `SaveCareerData`). NOT a lock predicate — `ctx+0x734=1` just means "memcard save in progress". |
| `0x004AF870` | carCfg/record → vehicle catalog index. |
| `0x004ADC10` / `0x004ADDE0` | carCfg constructor (0x104 bytes) / carCfg copy. |
| `0x0032F0F0` | DisplayPerformance (perf bars; special-cases the five AMG/prize cars by name). |
| `0x00538E58` | Career struct updater containing the other wallet writer (`0x00538FBC`); sole JAL caller `0x003A074C`. |
| `0x00320848` etc. | Flash-UI property API family: `0x00320848` set-bool/int, `0x00320968` set-string, `0x00320A88` get-int, `0x00320AC8` get-string, `0x00320A10` get-list-item. |

## Buy-confirm control flow (in `0x00337610`)

```text
UI event: choice1 == 3 (player pressed Buy on the confirm prompt)
  └─ 0x0033784C: if garage count [0x006E08FC] < 30
       ├─ sb 1, 0x006179BD          ; purchase-pending flag
       ├─ JAL 0x00334AA0            ; update UI text (vehicle name, "%s_short")
       └─ send "oktobuy" = 1        ; UI proceeds with purchase animation/flow
UI then sends back "Fortune" = "$<new total>"
  └─ 0x00337A54: read "Fortune", sscanf "$%d"
     0x00337A7C: JAL 0x00337378     ; SpendMoney(ctx, newTotal)   ← DETECT HOOK
     0x00337A9C: sw a3, 0xAC0(v0)   ; wallet = newTotal           ← cheat NOPs this
Garage insertion: fn 0x003325C8 copies selected carCfg into slot, requests save
```

Selected vehicle identity at any of these points:
`name = *(char*)([ctx + 0x71C + [ctx+0x72C]*4] + 0xDF)`; catalog index via `0x004AF870`.

## AP enforcement plan enabled by this

1. **Purchase detect (ready to build):** JAL trampoline at `0x00337A7C` → emit
   `PURCHASE(vehicle_index, amount)` to the mailbox. Clean call-site hook, same pattern
   as the verified SetCarCfg hook.
2. **Vehicle Permit deny gate (ready to design):** trampoline at `0x003378A8` (the JAL
   inside the buy-confirm branch): read selected vehicle name, check AP permit bitset;
   if denied, skip the pending-flag write and send `oktobuy=2` with the game's own
   error-text path (`txtError_limitslots` mechanism) — a native, softlock-free deny.
3. **Ownership checks (DONE, no hook needed):** poll `0x006E0900` slots — already
   exposed via `MC3Game.garage_vehicles()`. Enables "Vehicle Purchased/Owned — <id>"
   AP locations immediately.
4. **Vehicle Grant (future, primitives known):** write a carCfg into a free slot
   (`0x004ADC10`-style init or copy a template via `0x004ADDE0`), bump `0x006E08FC`,
   request save via `0x001B00B8(career, 1, 0, …)`.
5. **Dealer availability override (one unknown left):** the showroom Locked/Available
   state is computed natively and pushed into the Flash UI list when built (read back
   via `0x00320A10`, item state 3 = owned). Next static target: the list *builder* —
   follow `0x00320A10`-family setters from the showroom-enter path (`fn 0x00324E18`
   constructs the shop context; `fn 0x003346E0` = "InShowroom" navigation).

## Corrections to prior docs

- LAYER3_STATUS §5 said the next step "requires the PCSX2 debugger" — it did not; the
  cheat anchor + static xref reached the purchase flow without runtime tracing.
- LAYER3/FINAL report's garage layout (profile+0x410, stride 0x120, name +0x0BF) does
  not match the authoritative garage: the real owned-vehicle array is the static one at
  `0x006E0900` (stride 0x104, name +0xDF). The profile-side copies are likely
  save-serialization images, not the live garage.
- `0x006E08FC` in NEXT_STEP_PLAN was unexplained; it is the garage count (u8, cap 30).
