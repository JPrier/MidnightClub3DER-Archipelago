# Reverse Engineering Checklists

Living document.  Each area graduates from "unknown" to "high confidence"
only after all checklist items are ✅ and graduation criteria are met.

---

## 1. Current Event ID

**Goal:** Map every race/tournament/club event to a stable `EventId`.

| Step | Status |
|---|---|
| Start in free roam, search memory for 0 | ⬜ |
| Select known event, search for changed values | ⬜ |
| Filter candidates across event type changes | ⬜ |
| Locate event pointer or metadata block | ⬜ |
| Hook event selection / race load | ⬜ |
| Log route name, city, race type, opponent | ⬜ |
| Generate EventId hash from stable fields | ⬜ |
| Verify same event → same hash (5+ boots) | ⬜ |
| Verify different events → different hash | ⬜ |
| Build event_catalog.json | ⬜ |
| Add EventIdCollisionTest | ⬜ |

**Graduation:** 100% curated events have stable IDs. Zero collisions. Race finish resolves current event.

---

## 2. Player Won/Lost

**Goal:** Emit check only on win.

| Step | Status |
|---|---|
| Hook known race finish (0x3EDAC8) | ⬜ |
| Log race context on win/loss/retry/quit | ⬜ |
| Compare memory diffs between win and loss | ⬜ |
| Identify reward-granted / completion-flag branch | ⬜ |
| Probe: win emits RaceResult(won=True) | ⬜ |

**Graduation:** 20 wins/losses correctly classified. Quit/retry never emits check. Tournament intermediate screens handled.

---

## 3. Event Start Gate

**Goal:** Block locked events without corrupting state.

| Step | Status |
|---|---|
| Find "Start Race" confirmation function | ⬜ |
| Patch return via debugger to block start | ⬜ |
| Identify safe failure path (return to menu) | ⬜ |
| Hook with CanStartEvent(event_id) | ⬜ |
| Display message if possible | ⬜ |
| Validate no softlock in each city/race type | ⬜ |

**Graduation:** Locked event cannot start from any UI path. Blocked start = stable state. Unlocked events unchanged.

---

## 4. City Travel

**Goal:** Block travel to locked cities.

| Step | Status |
|---|---|
| Find current city ID in memory | ⬜ |
| Set write breakpoint on city ID | ⬜ |
| Trigger city travel, trace to function | ⬜ |
| Hook travel request | ⬜ |
| Block travel if city not allowed | ⬜ |
| Handle savestate in locked city | ⬜ |

**Graduation:** Travel blocked from menu and map. Allowed travel unchanged. Locked-city savestate cannot progress.

---

## 5. Vehicle Purchase/Use

**Goal:** Enforce per-vehicle permits, category/class gates, grants.

| Step | Status |
|---|---|
| Use known vehicle list pointer (0x006E0170) | ⬜ |
| Determine mcVehicle struct layout | ⬜ |
| Identify dealer inventory function | ⬜ |
| Identify purchase confirmation function | ⬜ |
| Identify garage select/equip function | ⬜ |
| Use SetCarCfg hook as final guard | ⬜ |
| Implement fallback vehicle | ⬜ |
| Implement direct garage grant | ⬜ |

**Graduation:** Locked vehicle cannot be bought/equipped/raced. AP grant appears once per instance. Garage-full deterministic.

---

## 6. Part Purchase/Equip

**Goal:** Full part coverage.

| Step | Status |
|---|---|
| Extract part data from ASSETS.DAT | ⬜ |
| Search memory for money changes during part purchase | ⬜ |
| Break on writes to car config after equip | ⬜ |
| Identify part ID / category / tier fields | ⬜ |
| Hook purchase and equip | ⬜ |
| Garage-exit legality repair | ⬜ |
| Race-start legality repair | ⬜ |
| Build part catalog with stable PartId | ⬜ |

**Graduation:** Every curated part has stable ID. Locked parts blocked. Illegal parts repaired. No legal part blocked.

---

## 7. Ability Activation

**Goal:** Gate Zone/Agro/Roar.

| Step | Status |
|---|---|
| Use cheat code to confirm ability flags | ⬜ |
| Search for activation meter value | ⬜ |
| Activate ability, trace branch/function | ⬜ |
| Hook activation function | ⬜ |
| Block if not AP-allowed | ⬜ |
| Suppress vanilla unlock if AP-controlled | ⬜ |

**Graduation:** Each ability blocked before AP item, works after. UI state does not bypass.

---

## 8. Collectibles (Rockstar Logos)

**Goal:** 36 individual checks.

| Step | Status |
|---|---|
| Use public map to visit known logo | ⬜ |
| Search collectible count before/after pickup | ⬜ |
| Search bitset (collect logo on clean save) | ⬜ |
| Compare saves before/after pickup | ⬜ |
| Identify pickup function / flag write | ⬜ |
| Hook pickup | ⬜ |
| Assign stable IDs by city + index + position | ⬜ |
| Suppress vanilla 12/24/36 rewards unless AP-granted | ⬜ |

**Graduation:** All 36 logos individually detected. No duplicate checks. Tier rewards AP-controlled.

---

## 9. Vanilla Reward Suppression

**Goal:** No vanilla progression bypasses AP.

| Step | Status |
|---|---|
| Win race that unlocks vehicle/city/cosmetic | ⬜ |
| Break on write to unlock flag | ⬜ |
| Identify reward application function | ⬜ |
| Hook reward function | ⬜ |
| Classify as AP-controlled or vanilla-allowed | ⬜ |
| Suppress AP-controlled rewards | ⬜ |
| Emit location check for original action | ⬜ |
| Repair pass after reward screen | ⬜ |

**Graduation:** No AP-controlled unlock survives without item. AP unlocks persist. Non-AP rewards work.

---

## 10. Save-State / Save-File

**Goal:** No AP state loss or duplication.

| Step | Status |
|---|---|
| Treat AP state as authoritative | ⬜ |
| On profile load: read profile hash | ⬜ |
| On payload attach: resend full desired state | ⬜ |
| Savestate rollback: checked locations persist | ⬜ |
| Prevent checks while Python disconnected | ⬜ |

**Graduation:** Python/PCSX2 restart does not lose items/checks. Savestate cannot duplicate progress.

---

### Summary

| # | Area | Confidence | Checklist Items | Graduated |
|---|---|---|---|---|
| 1 | Current Event ID | medium | 11 | ⬜ |
| 2 | Player Won/Lost | medium | 5 | ⬜ |
| 3 | Event Start Gate | medium | 6 | ⬜ |
| 4 | City Travel | medium | 6 | ⬜ |
| 5 | Vehicle Purchase/Use | medium | 8 | ⬜ |
| 6 | Part Purchase/Equip | low-medium | 8 | ⬜ |
| 7 | Ability Activation | low-medium | 6 | ⬜ |
| 8 | Collectibles | medium | 8 | ⬜ |
| 9 | Vanilla Reward Suppression | low-medium | 8 | ⬜ |
| 10 | Save-State / Save-File | medium | 5 | ⬜ |