# MC3 Stats Catalog — Check-Detection Core Structure

*Discovered 2026-07-08 via s6/s13/s14 differential analysis + live verification (build-13 payload).*

The structure previously called the "event catalog" (`0x00800878 → 0x007C9EF0`) is a
**career stats registry**: an ordered array of 16-byte tagged entries. It is the
single richest source of Archipelago location-check signals in the game.

## Entry layout

| Offset | Type | Meaning |
|---|---|---|
| +0x00 | u32 (4CC) | tag, ASCII, semantic name reads **reversed** (`LOCc` → "COL"+city scope) |
| +0x04 | u32 | index (city id, route id, vehicle id — meaning depends on tag) |
| +0x08 | u32 | meta pointer (into ELF data / profile — stat descriptor) |
| +0x0C | u32 or f32 | value |

Array terminates at uninitialized memory (`0xCDCDCDCD`).

## CRITICAL: insert-shift behavior

Entries are **inserted** when a stat first occurs (e.g. `LOCg` appeared between
`NRBg` and `POHg` when the first collectible was picked up). Every later entry
shifts by 16 bytes. **Never address catalog entries by fixed address — always
scan by tag.** This invalidates the old `player_race_position = 0x007CA044`
"confirmation" (that address is inside the catalog, on a `QS%k` entry).

## Tag suffix convention

| Suffix | Scope |
|---|---|
| `c` | per-city (index = city id 0/1/2) |
| `g` | global career |
| `k` | career counters |
| `r` | per-route records (index = **stable global route id**) |
| `v` | per-vehicle (index = vehicle id) |

## Confirmed tags (differential proof)

| Tag | Reversed | Meaning | Proof |
|---|---|---|---|
| `LOCc` | COL | collectibles per city | s6→s13: idx0 0→1 on one Rockstar logo |
| `LOCg` | COL | collectibles total | inserted with value 1 at first pickup |
| `UOTk` | TOU | **tournament wins** | s13→s14: 0→1 on tournament win |
| `NIWk`/`NIWg`/`NIWv` | WIN | race wins (career/global/per-vehicle) | s13→s14: 4→6 |
| `RACk` | — | races entered | s13→s14: 10→11 |
| `EC$k` | $CE | career earnings | s13→s14: 2900→37880 |
| `DN2k`/`DR3k` | 2ND/3RD | 2nd/3rd place finishes | stable 0 across states |
| `IT:r` | r:TI | per-route best time (f32 s) | s14 added idx 0x3E,0x3F,0x41 after tournament races |
| `PSAr` | rASP | per-route avg speed (f32) | index matches IT:r route ids |

## High-confidence hypotheses (values plausible, not yet action-verified)

| Tag | Guess | Evidence |
|---|---|---|
| `PThg` | play time (hours, f32) | 0.418→0.595 across sessions |
| `SDkc`/`SDkg`/`TSDv` | distance driven km (city/global/vehicle) | 12.558→25.440 in lockstep |
| `STvg` | top speed | 170.996 constant after fast race |
| `DJmg` | longest jump distance | 75.511 constant |
| `TAsg`/`TJsg` | air time / jump time seconds | small floats |
| `NRBg` | burnouts? | 3→6 |
| `SRTk` | tournaments started? | 1→2 when tournament played |
| `KOHk` | hookman (street racer) wins? | 1 after Vanessa arc |
| `LKSk` | skill/level? | 3 |
| `QS%k[0..6]` | per-category usage % (7 vehicle categories) | 7 entries, zeros early |
| `EA%k`/`GA%k`/`FA%k` | percentages | small floats |

## Event identity sources

1. **`IT:r` route ids** — first completion of a route inserts an `IT:r` entry with
   a stable numeric route id. Diffing the id set before/after a race identifies
   *which* route was just completed. Known ids so far: 0x01, 0x04, 0x0F, 0x16
   (Vanessa arc / early SD), 0x3E, 0x3F, 0x41 (SD autocross tournament "Ocean's
   Eleven" races).
2. **`last_event_path`** — profile+0x69 c-string, e.g.
   `...autox\med\sd_autox_med_oceanseleven_race01`. Human-readable event
   file path of the most recently played event. Two profile copies exist
   (0x007D2310, 0x007D3A00, stride 0x16F0).

## AP check-detection recipe

Poll the catalog (tag scan) once per second:

- `LOCg`/`LOCc[city]` increment → collectible check (city known from LOCc index)
- new `IT:r` index appears → route completed → race-specific check
- `NIWk` increment on same poll → it was a **win**
- `UOTk` increment → tournament completion check
- `EC$k` delta → vanilla earnings (for money reconciliation)
- wallet money `0x00800870` remains a plain confirmed field (outside catalog)

## Refuted candidates

`0x00618D24`, `0x00621708` (collectible bitset), `0x00618AD8`, `0x006145FC`
(garage ownership), `0x00615A3C` (tournament flag) — all shown to be unrelated
drift by cross-state analysis (e.g. 0x615A3C=1 in s2, long before any
tournament). Removed from consideration.
