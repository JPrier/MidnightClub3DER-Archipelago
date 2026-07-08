# Midnight Club 3: DUB Edition Remix Archipelago Integration — Full-Coverage Design Doc

**Target game:** Midnight Club 3: DUB Edition Remix, PlayStation 2, NTSC-U  
**Target build:** `SLUS-21355`, CRC `0x60A42FF5`  
**Target runtime:** stock/current PCSX2 emulation, using an external Python client plus memory/mailbox bridge. A PCSX2 fork is optional research/quality-of-life only, not a baseline requirement.  
**Design goal:** full-game Archipelago coverage: races, tournaments, city progression, individual vehicles, vehicle classes/categories, performance parts, visual/customization parts, special abilities, money, prize cars, collectibles, cosmetic rewards, and all irreversible/milestone-style checks.

---

## 1. Research-grounded facts

### 1.1 Archipelago constraints

Archipelago integrations have two major parts:

1. **Game modification / client** — detects in-game checks, receives items, grants items, reconnects/resyncs, and reports goal completion.
2. **World** — Python generator/server integration defining items, locations, options, logic, datapackage, and docs.

Official AP docs say new games need both a client and a world. They also say the world must be written as a Python package under `/worlds/{game}`, with item/location ID mappings, regions, items, and a completion condition. The World API further states AP worlds are Python 3, while clients can be in any language that supports WebSockets.

AP protocol facts that shape this design:

- Packets are JSON lists of command objects.
- Clients receive ordered `ReceivedItems` packets with an `index`.
- If the received item index does not match what the client expects, the client should resync using `Sync` and then `LocationChecks`.
- If `ReceivedItems.index == 0`, the packet represents a full inventory replacement and the client should abandon its previous inventory.
- Duplicate `LocationChecks` are safe and should be used for resync.
- The client must keep a received-item index, receive items sent while offline, and handle arbitrary copies of items.

### 1.2 Existing Midnight Club 3 modding facts

The strongest public prior art is `MC3CarRandomizer`, an open-source PS2 randomizer for Midnight Club 3: DUB Edition Remix. It targets **MC3 Remix US / `SLUS-21355` / CRC `0x60A42FF5`**. Its README says it is loaded by putting `MC3CarRandomizer.elf` in the `PLUGINS` directory of a PCSX2 fork with plugins.

It documents these game hook concepts:

- vehicle configuration application
- career data loading
- career data saving
- save creation
- race finish
- race-over screen

Its source exposes important known addresses for the Remix US build:

```c
loc_4AE100  = SetCarCfg call site
loc_1B0C20  = OnLoadCareerDataDone call site
loc_1AE8A0  = OnSaveData_1 call site
loc_1AF4F8  = OnSaveData_2 call site
loc_1AF098  = OnCreateSavegame call site
loc_3EE860  = OnRaceOver call site
loc_3EDAC8  = OnRaceFinished call site
ppVehList   = 0x006E0170
pVehCount   = 0x006E0174
pProfile    = 0x00619B14
```

It also says the vehicle list is built by the game from `tune/vehicle/vehicle.lst`, and the vehicle count sits beside the vehicle list pointer.

Public MC3 asset modding also exists. Nexus vehicle mods document an `ASSETS.DAT` workflow using `dave.py` to extract/rebuild and `apache_ps2` to inject the rebuilt archive into the ISO. PCSX2 texture replacements are also used under the `textures/SLUS-21355/replacements` path.

### 1.3 Game coverage facts

Public game data sources indicate:

- Remix has **94 vehicles**, compared with 69 in the original release.
- Vehicles are grouped into seven categories: import tuners, luxury sedans, SUVs/trucks, exotics/concepts, classic/muscle cars, sports bikes, and choppers.
- Vehicles are also grouped into classes D, C, B, and A.
- The game has Rockstar logo collectibles. Public cheat/unlock references say collecting 12, 24, and 36 Rockstar logos unlocks additional cosmetic/garage/race-start rewards.
- Race types include ordered races, circuit races, autocross, tournaments, club races, track races, and unordered races.

### 1.4 What public research did **not** find

I did not find a public Midnight Club 3 Archipelago world, full career randomizer, full item/location randomizer, or public address map covering:

- current event pointer
- current selected race pointer
- player win/loss result field
- race-start permission function
- city travel function
- dealer purchase function
- garage ownership array layout
- garage slot structure
- individual part catalog
- part purchase/equip functions
- collectible pickup function
- collectible bitset address
- special ability activation function
- vanilla reward function
- in-game message/UI notification function
- full save data layout

Therefore all of those are treated as **unknowns with explicit reverse-engineering checklists**.

---

## 2. Design position

We do **not** simplify by removing features. We simplify by making the design **data-driven, declarative, and layered**.

The system must support every coverage category:

- every race/checkable event
- every tournament
- every club race
- city unlocks
- class unlocks
- individual vehicle unlocks
- vehicle category unlocks
- vehicle purchase/ownership checks
- prize cars
- garage slots
- performance upgrades
- visual/customization upgrades
- special abilities
- money
- collectibles
- collectible reward tiers
- cosmetics
- traps
- final goal

The core design decision:

> **The game payload does not know Archipelago. The Archipelago client does not know MC3 memory internals. Both speak through contracts.**

---

## 3. System architecture

```text
Archipelago server
  ^
  | JSON WebSocket AP protocol
  v
Archipelago adapter
  ^
  | domain events
  v
MC3AP application service
  ^
  | pure reducer over seed contract + item log + check set
  v
DesiredGameState snapshot
  ^
  | binary mailbox ABI
  v
PCSX2 runtime adapter
  ^
  | command/event rings
  v
Injected PS2 EE payload
  ^
  | function hooks + memory reads/writes
  v
Midnight Club 3 game runtime
```

### 3.1 Layering rule

Dependency direction:

```text
domain -> nothing
application -> domain + ports
adapters -> ports + external systems
payload hooks -> payload app -> payload domain + game adapter + mailbox
```

No layer reaches sideways:

- AP adapter cannot read PCSX2 memory.
- PCSX2 adapter cannot parse AP packets.
- Payload cannot connect to AP.
- Domain cannot know WebSockets, process memory, or hook addresses.
- APWorld cannot know runtime memory addresses except as optional generated metadata for the client.

---

## 4. Repository layout

```text
mc3-ap/
  README.md
  docs/
    design.md
    reverse_engineering_checklists.md
    validation_plan.md
    user_setup.md

  worlds/mc3/
    __init__.py
    items.py
    locations.py
    options.py
    regions.py
    rules.py
    slot_data.py
    catalog.py
    docs/
      setup_en.md
      en_Midnight Club 3 DUB Edition Remix.md
    data/
      static_catalog/
      generated_catalog/
      schema/

  client/mc3ap/
    domain/
      ids.py
      model.py
      seed_contract.py
      catalog.py
      reducer.py
      invariants.py
      gates.py
      item_semantics.py
      check_semantics.py

    application/
      client_service.py
      reconciliation_service.py
      ap_event_service.py
      game_event_service.py
      validation_service.py

    ports/
      ap_server_port.py
      game_runtime_port.py
      persistence_port.py
      seed_contract_port.py
      logger_port.py
      clock_port.py

    adapters/
      archipelago/
        ap_client_adapter.py
        packet_mapper.py
      pcsx2/
        process_memory_bridge.py
        mailbox_adapter.py
        payload_probe_adapter.py
      storage/
        sqlite_event_store.py
        json_state_store.py
      fake/
        fake_ap_server.py
        fake_game_runtime.py

    validation/
      scenario_runner.py
      scenarios/
      schemas/

  payload/
    include/
      mailbox.h
      generated_mailbox.h
      mc3ap_contract.h
    src/
      app/
        command_processor.c
        event_emitter.c
        reconcile.c
      domain/
        gate_eval.c
        desired_state.c
        idempotency.c
      game_adapter/
        mc3_memory.c
        mc3_catalog_runtime.c
        mc3_garage.c
        mc3_events.c
        mc3_rewards.c
        mc3_collectibles.c
        mc3_parts.c
        mc3_abilities.c
        mc3_messages.c
      hooks/
        hook_install.c
        race_finish_hook.c
        race_over_hook.c
        career_load_hook.c
        career_save_hook.c
        save_create_hook.c
        car_config_hook.c
        event_select_hook.c
        event_start_gate_hook.c
        city_travel_hook.c
        dealer_purchase_hook.c
        garage_exit_hook.c
        part_purchase_hook.c
        part_equip_hook.c
        ability_activate_hook.c
        collectible_pickup_hook.c
        vanilla_reward_hook.c
      mailbox/
        mailbox.c
        mailbox_abi.c
      selftest/
        payload_selftest.c

  tools/
    extract_assets.py
    extract_vehicle_catalog.py
    extract_part_catalog.py
    extract_event_catalog.py
    probe_runtime_addresses.py
    generate_mailbox_abi.py
    generate_pnach_debug.py
    build_seed_contract.py

  tests/
    unit/
    contract/
    integration/
    emulator/
    e2e/
```

---

## 5. Language decisions

### 5.1 Required

| Component | Language | Reason |
|---|---|---|
| APWorld | Python | Archipelago worlds are Python 3 packages |
| AP client | Python initially | easiest integration with AP and test harnesses |
| Injected EE payload | C with small assembly where needed | PS2/MIPS EE runtime, ABI control, no allocator required |
| Optional PCSX2-native bridge/upstream patch | C++ | only if we later add a first-class emulator-side IPC/debug API; not required for baseline |
| Validation suite | Python | fast fake AP/fake runtime/property tests |

### 5.2 Optional future replacements

The AP client could later be Rust/C#/C++ because AP clients only need WebSocket support. But Python is the lowest-friction v1 because it shares code/types with the APWorld and validation suite.

The EE payload should stay C. Avoid Rust in the payload until there is a proven PS2 EE toolchain, reliable linker script, no-std setup, and known calling convention compatibility.

---

## 6. Core contracts

### 6.1 SeedContract

Generated by APWorld and loaded by the Python client.

```python
@dataclass(frozen=True)
class SeedContract:
    schema_version: int
    game: str
    expected_serial: str
    expected_crc: int
    seed_name: str
    slot: int
    slot_name: str
    catalog_hash: str
    item_table: Mapping[int, ItemDefinition]
    location_table: Mapping[int, LocationDefinition]
    event_table: Mapping[int, EventDefinition]
    collectible_table: Mapping[int, CollectibleDefinition]
    vehicle_table: Mapping[int, VehicleDefinition]
    part_table: Mapping[int, PartDefinition]
    gate_table: Mapping[int, GateDefinition]
    goal_definition: GoalDefinition
    options: MC3Options
```

### 6.2 GameCatalog

A canonical static description of MC3 content.

```python
@dataclass(frozen=True)
class GameCatalog:
    vehicles: Mapping[VehicleId, VehicleDefinition]
    parts: Mapping[PartId, PartDefinition]
    races: Mapping[EventId, EventDefinition]
    tournaments: Mapping[TournamentId, TournamentDefinition]
    clubs: Mapping[ClubId, ClubDefinition]
    cities: Mapping[CityId, CityDefinition]
    collectibles: Mapping[CollectibleId, CollectibleDefinition]
    abilities: Mapping[AbilityId, AbilityDefinition]
    reward_rules: Mapping[RewardId, RewardDefinition]
```

Catalog values are generated by combining:

1. extracted `ASSETS.DAT`/`vehicle.lst` metadata,
2. runtime probes,
3. manually curated metadata,
4. public guide validation where appropriate,
5. checksum/hash validation.

### 6.3 DesiredGameState

The Python client computes this from the seed contract, received AP item log, local check set, and persisted state.

```python
@dataclass(frozen=True)
class DesiredGameState:
    schema_version: int
    sequence: int
    state_hash: str

    seed_hash: str
    slot: int
    profile_hash: int

    checked_locations: FrozenSet[LocationId]

    allowed_cities: FrozenSet[CityId]
    allowed_events: FrozenSet[EventId]
    allowed_vehicle_classes: FrozenSet[VehicleClass]
    allowed_vehicle_categories: FrozenSet[VehicleCategory]
    allowed_vehicles: FrozenSet[VehicleId]
    granted_vehicles: FrozenSet[GrantedVehicleInstance]
    allowed_parts: FrozenSet[PartId]
    allowed_part_categories: FrozenSet[PartCategoryId]
    allowed_abilities: FrozenSet[AbilityId]
    allowed_cosmetics: FrozenSet[CosmeticId]

    total_ap_money: int
    garage_slot_limit: int
    collectible_reward_tiers: FrozenSet[CollectibleTier]

    pending_traps: Tuple[TrapEvent, ...]
    goal_completed: bool
```

### 6.4 RuntimeActualState

The payload exposes a normalized snapshot of what it observes.

```python
@dataclass(frozen=True)
class RuntimeActualState:
    game_crc: int
    payload_build: int
    profile_hash: int
    current_city: Optional[CityId]
    current_event: Optional[EventId]
    current_vehicle: Optional[VehicleId]
    owned_vehicles: FrozenSet[VehicleId]
    equipped_parts: FrozenSet[PartId]
    owned_parts: FrozenSet[PartId]
    collected_collectibles: FrozenSet[CollectibleId]
    money: int
    active_abilities: FrozenSet[AbilityId]
    vanilla_unlock_flags: FrozenSet[VanillaFlagId]
    last_hook_observed: Mapping[HookId, int]
```

The payload does not need to expose every byte of game state, only enough to validate and reconcile.

---

## 7. Item model: full coverage

This design supports coarse and fine itemization. Full coverage means every item type exists in the catalog, even if options allow players to collapse them into progressive groups.

### 7.1 City items

```text
City Permit: San Diego
City Permit: Atlanta
City Permit: Detroit
City Permit: Tokyo
```

San Diego may be starting or randomized depending on options.

### 7.2 Event access items

```text
Event Permit: <event_id>
Tournament Permit: <tournament_id>
Club Permit: <club_id>
```

These let individual races/tournaments/clubs be locked by AP.

### 7.3 Vehicle items

For every vehicle:

```text
Vehicle Permit: <vehicle_id>    # may buy/use vehicle
Vehicle Grant: <vehicle_id>     # directly grants garage instance
Vehicle Voucher: <vehicle_id>   # one-time claim without money cost
```

The APWorld can choose one mode:

```text
vehicle_item_mode:
  - permits_only
  - direct_grants
  - permits_plus_vouchers
```

Support all modes in the design. Do not hard-code one.

### 7.4 Vehicle group items

```text
Vehicle Class License: D/C/B/A
Vehicle Category Permit: Tuner/Muscle/Luxury/SUV/Exotic/SportBike/Chopper
Manufacturer Permit: optional
```

These are group gates layered with individual vehicle gates.

### 7.5 Garage items

```text
Progressive Garage Slot
Prize Car Claim: <prize_id>
Duplicate Vehicle Allowance
```

Garage capacity is important because public data indicates a 30-vehicle garage limit. If the game converts prize cars to cash when full, AP must prevent accidental loss of AP-granted vehicles.

### 7.6 Performance part items

For each performance part:

```text
Part Permit: <part_id>
Part Grant: <part_id>
Part Category Permit: Engine/Transmission/Nitrous/Tires/Suspension/etc.
Progressive Performance Tier
```

The catalog must not assume part categories until extracted/reversed. It should support unknown categories as data.

### 7.7 Visual/customization items

For every visual customization feature that can be locked/unlocked:

```text
Visual Part Permit: <part_id>
Rim Permit: <rim_id>
Paint Permit: <paint_id>
Vinyl Permit: <vinyl_id>
License Plate Permit: <plate_id>
Hydraulic/Airbag/Neon Permit: <feature_id>
```

Some of these may be cosmetic-only. They can be marked:

```python
classification = useful | filler | progression
```

depending on options.

### 7.8 Special ability items

```text
Ability Permit: Zone
Ability Permit: Agro
Ability Permit: Roar
Ability Meter Upgrade: optional if such state exists
```

The game has known cheat codes for unlocking Zone, Agro, and Roar, which proves these are distinct runtime unlock concepts even if the exact memory flags are not yet known.

### 7.9 Money items

```text
Money Pack: $500
Money Pack: $1,000
Money Pack: $5,000
Money Pack: $10,000
Money Pack: $50,000
```

Money is tracked as total AP money, not incremental commands.

### 7.10 Collectible reward items

```text
Rockstar Logo Reward: Flags
Rockstar Logo Reward: Rockstar Plates
Rockstar Logo Reward: Race Starter Riders
```

Public cheat/unlock references indicate 12/24/36 logo thresholds. The mod should support both vanilla reward thresholds and AP-randomized reward grants.

### 7.11 Trap items

```text
Trap: Forced Rental Car
Trap: Police Heat
Trap: Traffic Surge
Trap: Nitrous Drain
Trap: Wrong-Way Overlay
Trap: Cosmetic Scramble
```

Trap effects must be unique-event-id based and idempotent.

---

## 8. Location/check model: full coverage

A “location” is anything the player can check. Full coverage means every irreversible/milestone-style action becomes a possible AP location.

### 8.1 Race checks

Each race/event:

```text
Location: Race Win — <event_id>
```

Detection:

1. payload captures selected/current event ID,
2. race finish hook fires,
3. payload validates player won,
4. payload maps event ID to AP location ID,
5. payload emits `LocationChecked`.

### 8.2 Tournament checks

Two possible models:

```text
Location: Tournament Complete — <tournament_id>
Location: Tournament Race Win — <tournament_id>/<race_index>
```

The APWorld should support both. Fullest coverage enables race-level and completion-level checks. To avoid duplicate progression, completion-level checks can be event locations marked as “meta checks.”

### 8.3 Club checks

```text
Location: Club Race Win — <club_id>/<race_id>
Location: Club Complete — <club_id>
```

### 8.4 City progression checks

```text
Location: City Unlocked — Atlanta/Detroit/Tokyo
Location: City Champion Defeated — <city>
Location: All Street Racers Defeated — <city>
```

These are derived from game flags or race completion.

### 8.5 Vehicle checks

```text
Location: Vehicle Purchased — <vehicle_id>
Location: Vehicle Owned — <vehicle_id>
Location: Vehicle Won — <prize_vehicle_id>
Location: Vehicle Category Complete — <category_id>
Location: Vehicle Class Complete — <class_id>
```

Important: “Purchased” and “Owned” are different. A direct AP-granted vehicle should check “Owned” but not necessarily “Purchased,” depending on options.

### 8.6 Part checks

```text
Location: Part Purchased — <part_id>
Location: Part Equipped — <part_id>
Location: Full Performance Tier Equipped — <vehicle_id>/<tier>
Location: Full Visual Kit Equipped — <vehicle_id>/<kit_id>
```

Part purchase/equip checks require part catalog extraction and hook discovery.

### 8.7 Collectible checks

```text
Location: Rockstar Logo Collected — <city>/<logo_index>
Location: 12 Logos Collected
Location: 24 Logos Collected
Location: 36 Logos Collected
```

Individual logo checks are essential for full coverage. Tier checks can be optional meta locations.

### 8.8 Money/economy checks

Usually money should be an item, not a location. But full coverage can include milestones:

```text
Location: Earned $X Total
Location: Spent $X Total
```

These should be optional because they are grindable and can distort AP logic.

### 8.9 Cosmetic checks

```text
Location: Cosmetic Unlocked — <cosmetic_id>
Location: Cosmetic Purchased — <cosmetic_id>
```

Cosmetic checks are filler/useful, not progression, unless options make cosmetics required.

---

## 9. Lock/unlock enforcement model

### 9.1 Principle

The game must be forced to match `DesiredGameState`.

There are three enforcement points:

1. **Prevent** illegal action before it happens.
2. **Suppress** vanilla rewards that would bypass AP.
3. **Repair** illegal state if it appears anyway.

### 9.2 City enforcement

Prevent:

- city travel to locked city
- event start in locked city
- map/menu selection of locked city

Suppress:

- vanilla city unlock reward if AP has not granted the city

Repair:

- if player is in locked city due to savestate or vanilla flag, allow return to allowed city or free-roam soft state but block events/purchases.

### 9.3 Event enforcement

Prevent:

- starting locked events
- entering tournaments without required permit
- starting club races without required category/class/club permit

Suppress:

- vanilla unlocking of subsequent event chain if AP has not granted it

Repair:

- hide or mark locked event entries if UI hook is found
- always block actual event start even if UI displays it

### 9.4 Vehicle enforcement

Prevent:

- buying locked vehicle
- selecting/equipping locked vehicle
- starting race in locked vehicle
- keeping AP-forbidden prize vehicle as usable

Suppress:

- vanilla vehicle unlocks and prize awards if AP owns those gates

Repair:

- if current car is illegal, force fallback legal vehicle or garage lock
- if direct grant item received, add to garage exactly once per AP item instance

### 9.5 Part enforcement

Prevent:

- buying locked part
- equipping locked part
- race start with locked part if equip hook missed

Suppress:

- vanilla part unlocks if AP controls them

Repair:

- downgrade illegal parts on garage exit or race start
- maintain a legal configuration shadow copy

### 9.6 Ability enforcement

Prevent:

- activation of locked Zone/Agro/Roar

Suppress:

- vanilla ability unlock flag if AP has not granted it

Repair:

- if ability is present but not AP-granted, block activation and optionally clear UI flag

### 9.7 Collectible enforcement

Do **not** prevent collecting logos unless AP item gating explicitly says “Collectible Scanner/Logo Access” is required. Default behavior:

- detecting a collectible pickup sends an AP check
- vanilla threshold rewards are suppressed unless AP grants them as items
- collected logos remain collected to avoid breaking the base game map

### 9.8 Money enforcement

Money must be ledgered.

Bad:

```text
GrantMoney(5000)
```

Good:

```text
SetTotalAPMoney(25000)
```

Payload computes:

```text
delta = desired_total_ap_money - already_applied_ap_money
```

Then applies only the delta.

### 9.9 Vanilla reward enforcement

A full randomizer must not let vanilla rewards bypass AP. Required strategy:

1. hook vanilla reward function if found,
2. suppress AP-controlled rewards,
3. still allow non-AP rewards or convert them into AP checks,
4. run a repair pass at menu transitions.

---

## 10. Runtime integration in detail

### 10.1 EE payload responsibilities

The payload:

- installs hooks,
- exposes mailbox,
- normalizes MC3 events,
- applies desired-state snapshots,
- enforces gates,
- emits self-test results,
- never speaks AP protocol.

### 10.2 Python client responsibilities

The Python client:

- connects to AP,
- receives items,
- sends checks,
- persists event log and AP item index,
- computes `DesiredGameState`,
- sends snapshots to payload,
- reads game events,
- performs reconciliation,
- runs validation.

### 10.3 Mailbox ABI

Use two ring buffers:

```text
game -> python: EventRing
python -> game: CommandRing
```

Plus snapshots and heartbeat.

```c
typedef struct {
    uint64_t magic;
    uint16_t abi_version;
    uint16_t sizeof_mailbox;
    uint32_t game_crc;
    uint32_t payload_build_id;

    uint32_t heartbeat_game;
    uint32_t heartbeat_python;

    uint32_t game_state;
    uint32_t profile_hash;
    uint32_t seed_hash;
    uint32_t slot;

    RingHeader event_ring;
    MC3AP_Event events[128];

    RingHeader command_ring;
    MC3AP_Command commands[128];

    DesiredStateHeader desired_header;
    uint8_t desired_blob[MAX_DESIRED_STATE_BLOB];

    RuntimeSnapshotHeader snapshot_header;
    uint8_t snapshot_blob[MAX_RUNTIME_SNAPSHOT_BLOB];

    uint32_t error_code;
    char last_error[128];
} MC3AP_Mailbox;
```

### 10.4 Command types

```text
HELLO_ACK
SET_CONNECTED
SET_SEED_CONTRACT
SET_DESIRED_STATE
REQUEST_RUNTIME_SNAPSHOT
REQUEST_SELF_TEST
DEBUG_SIMULATE_EVENT_COMPLETE
DEBUG_SIMULATE_COLLECTIBLE_PICKUP
DEBUG_SIMULATE_RECEIVE_ITEM
SHOW_MESSAGE
RESET_PAYLOAD_STATE
```

### 10.5 Event types

```text
HELLO
PROFILE_LOADED
RUNTIME_SNAPSHOT
LOCATION_CHECKED
GOAL_COMPLETED
SELF_TEST_RESULT
GATE_BLOCKED
ITEM_APPLIED
VANILLA_REWARD_SUPPRESSED
ERROR
LOG
```

### 10.6 Mailbox discovery

Payload writes a magic marker and version into EE RAM. Python scans PCSX2 process memory for:

```text
magic
abi_version
sizeof_mailbox
game_crc == 0x60A42FF5
heartbeat_game increments
```

Do not rely on fixed PC process addresses.

Baseline distribution should not require a PCSX2 fork. Process-memory discovery plus the stock PCSX2 debugger/patching ecosystem is the default plan. A PCSX2 fork/local IPC API is only an optional future improvement if it becomes clearly better and maintainable.


### 10.7 PCSX2 fork policy

The baseline design must work with stock/current PCSX2. The previous wording that implied a plugin-capable fork was too strong and should be treated as historical context from MC3CarRandomizer, not as a requirement for MC3AP.

Supported baseline strategy:

```text
stock PCSX2
  + AP Python client running outside the emulator
  + process-memory bridge that discovers EE RAM/mailbox dynamically
  + optional `.pnach` patches for bootstrap/debug/small hooks
  + optional ISO/asset patching for seed-specific data if needed
```

Design rule:

```text
No user-facing requirement may depend on a custom PCSX2 executable unless the stock path is proven impossible for that feature.
```

The role of an optional fork is limited to developer convenience or long-term hardening, such as exposing a stable local IPC/debug API. It must not be part of the normal installation path unless a future spike proves stock PCSX2 cannot provide reliable memory access, patching, or payload bootstrapping.

Validation impact:

- Add a `stock_pcsx2_runtime` validator lane.
- Treat any fork-only test as non-blocking research.
- CI/local release checklist must verify the bridge against at least one current PCSX2 stable build and one current nightly build.
- The setup guide should instruct users to install official PCSX2, not a fork.

---

## 11. Known hooks and missing hooks

### 11.1 Known from MC3CarRandomizer

| Need | Known public basis |
|---|---|
| vehicle config application | `SetCarCfg` call-site hook exists |
| career load | `OnLoadCareerDataDone` call-site hook exists |
| career save | two save hooks exist |
| save creation | save creation hook exists |
| race finish | race finish hook exists |
| race-over screen | race-over hook exists |
| vehicle list | pointer exists |
| vehicle count | pointer exists beside vehicle list |
| profile | profile pointer exists |

### 11.2 Unknowns that must be resolved

| Area | Confidence now | Must discover |
|---|---:|---|
| current selected event ID | medium | event pointer/struct or stable hash |
| player won/lost field | medium | race result field/return path |
| event start gate | medium | function to block race start cleanly |
| city travel | medium | travel/menu function |
| vehicle purchase | medium | dealer purchase confirmation |
| garage ownership | medium-low | vehicle array/slots/ownership flags |
| parts catalog | low-medium | part IDs/categories/tiers |
| part purchase/equip | low-medium | garage function hooks |
| ability activation | low-medium | activation function/flags |
| collectibles | medium | pickup hook and collected bitset |
| vanilla reward writes | low-medium | reward function/flag writes |
| message UI | low-medium | string display function |

---

## 12. How to resolve low-confidence areas

Every unknown gets a discovery checklist and graduation criteria.

### 12.1 Generic reverse-engineering workflow

For each unknown:

1. Identify a visible in-game value or observable transition.
2. Search memory in PCSX2 debugger.
3. Change the value/trigger transition.
4. Filter memory search results.
5. Add read/write breakpoint or logpoint.
6. Identify function/call site in R5900 disassembly.
7. Import labels/symbols into PCSX2.
8. Open corresponding code in Ghidra/IDA if needed.
9. Determine call arguments and structure layout.
10. Write a non-mutating probe hook.
11. Run probe across 10+ scenarios.
12. Convert probe hook into enforcement hook.
13. Add payload self-test.
14. Add emulator validation scenario.
15. Mark confidence high only after reproducible tests pass.

### 12.2 Current event ID checklist

Goal: map every race/tournament/club event to a stable `EventId`.

Steps:

- Start in free roam.
- Select a known event.
- Use memory search for changing menu-selected event values.
- Enter/exit different events and filter candidates.
- Locate event pointer or event metadata block.
- Hook event selection or race load.
- Log route name, city, race type, opponent, tournament/club ID, and any string pointers.
- Generate event hash from stable metadata.
- Verify same event always yields same hash across boot, save/load, and emulator restart.
- Verify different events never collide.
- Build `event_catalog.json`.
- Add `EventIdCollisionTest`.

Graduation criteria:

- 100% of curated events produce stable IDs.
- zero collisions across full catalog.
- race finish can resolve current event without menu state ambiguity.

### 12.3 Player won/lost checklist

Goal: emit check only on win.

Steps:

- Hook known race finish function.
- Log race context pointer and nearby fields on win/loss/retry/quit.
- Compare memory diffs between win and loss.
- Search for result text or reward path.
- Identify branch that triggers reward save/update.
- Prefer using “reward granted” or “completion flag write” over race-end screen.
- Add probe: win race emits `RaceResult(won=True)`, loss emits `won=False`.

Graduation criteria:

- 20 wins/losses across race types correctly classified.
- quitting/retry never emits check.
- tournament intermediate screens correctly handled.

### 12.4 Event start gate checklist

Goal: block locked events without corrupting state.

Steps:

- Find function called when selecting “Start Race.”
- Patch return temporarily via debugger/PNACH to block start.
- Identify safe failure path that returns to menu/free roam.
- Hook with `CanStartEvent(event_id)`.
- Display message if possible.
- Validate no softlock when blocked in each city/race type.

Graduation criteria:

- locked event cannot start from any UI path.
- blocked start leaves player in stable state.
- unlocked event behavior unchanged.

### 12.5 City travel checklist

Goal: block travel to locked cities.

Steps:

- Search current city ID.
- Trigger city travel.
- Break on writes to current city.
- Identify travel function and menu path.
- Hook travel request.
- Block travel if city not allowed.
- Repair state if savestate loads player into locked city.

Graduation criteria:

- travel blocked from menu and map.
- allowed city travel unchanged.
- locked-city savestate cannot progress AP checks.

### 12.6 Vehicle purchase/use checklist

Goal: enforce per-vehicle permits, category/class permits, vouchers, and direct grants.

Steps:

- Use known vehicle list pointer.
- Determine `mcVehicle` struct layout enough for name/category/class.
- Identify dealer inventory function.
- Identify purchase confirmation function.
- Identify garage selection/equip function.
- Use known `SetCarCfg` hook as final guard.
- Implement fallback vehicle.
- Implement direct garage grant using ownership/garage structure.
- Prevent prize-car loss when garage full.

Graduation criteria:

- locked vehicle cannot be bought.
- locked vehicle cannot be equipped.
- locked vehicle cannot start race.
- AP-granted vehicle appears once per item instance.
- duplicate AP vehicle item creates duplicate only when allowed by options and garage space.
- garage-full behavior is deterministic.

### 12.7 Part purchase/equip checklist

Goal: full part coverage.

Steps:

- Extract part data from assets if possible.
- Search for money changes during part purchase.
- Break on writes to car config after equipping part.
- Identify part IDs and category/tier fields.
- Hook purchase and equip.
- Add garage-exit legality repair.
- Add race-start legality repair.
- Build part catalog with stable `PartId`.

Graduation criteria:

- every curated part has a stable ID.
- locked part cannot be purchased.
- locked part cannot be equipped.
- illegal parts are repaired without save corruption.
- no legal part is blocked.

### 12.8 Ability activation checklist

Goal: gate Zone/Agro/Roar.

Steps:

- Use known cheat-code unlock behavior to find ability flags.
- Search for activation meter value.
- Activate abilities and trace branch/function.
- Hook activation function.
- Block if ability not AP-allowed.
- Suppress vanilla unlock flag if AP-controlled.

Graduation criteria:

- each ability blocked before AP item.
- each ability works after AP item.
- UI state does not allow bypass.

### 12.9 Collectible checklist

Goal: individual Rockstar logo checks.

Steps:

- Use public maps to visit known logo.
- Search collectible count before/after pickup.
- Search bitset by collecting a known logo on clean save.
- Compare saves before/after pickup.
- Identify pickup function or collected flag write.
- Hook pickup.
- Assign stable collectible IDs by city + index + position.
- Build collectible catalog.
- Suppress vanilla 12/24/36 rewards unless AP-granted.

Graduation criteria:

- all 36 logos individually detected.
- duplicate pickups never emit duplicate checks.
- tier rewards do not bypass AP.

### 12.10 Vanilla reward checklist

Goal: prevent vanilla progression from bypassing AP.

Steps:

- Use known unlocks from guides as test cases.
- Win a race/tournament that normally unlocks vehicle/city/ability/cosmetic.
- Break on write to unlock flag.
- Identify reward application function.
- Hook reward function.
- Classify reward as AP-controlled or vanilla-allowed.
- Suppress AP-controlled reward.
- Emit location check for the original action.
- Apply repair pass after reward screen.

Graduation criteria:

- no vanilla AP-controlled unlock survives if item not received.
- AP-received unlock survives reward screens and saves.
- non-AP rewards still work if left vanilla.

### 12.11 Save-state and save-file checklist

Goal: avoid AP state loss or duplication.

Steps:

- Treat AP server/client state as authoritative.
- On profile load, read profile hash.
- On payload attach, Python resends full desired state.
- On savestate rollback, checked locations from AP remain checked.
- Prevent race checks while Python disconnected unless save flags are readable.
- Optionally persist seed/profile marker in save but not full AP state initially.

Graduation criteria:

- Python restart does not lose items/checks.
- PCSX2 restart does not lose AP state.
- savestate rollback cannot duplicate money or AP grants.
- disconnected race completion is either blocked or recoverable from save flags.

---

## 13. APWorld design

### 13.1 Files

```text
worlds/mc3/
  __init__.py
  items.py
  locations.py
  options.py
  regions.py
  rules.py
  catalog.py
  slot_data.py
```

### 13.2 `MC3World`

```python
class MC3World(World):
    game = "Midnight Club 3: DUB Edition Remix"
    web = MC3WebWorld()

    item_name_to_id = ITEM_NAME_TO_ID
    location_name_to_id = LOCATION_NAME_TO_ID

    def generate_early(self):
        self.catalog = load_catalog(self.options.catalog_mode)

    def create_regions(self):
        create_regions_from_catalog(self, self.catalog)

    def create_items(self):
        self.multiworld.itempool += build_item_pool(self, self.catalog)

    def set_rules(self):
        apply_rules_from_gate_contract(self, self.catalog)

    def create_item(self, name: str):
        return create_mc3_item(self, name)

    def fill_slot_data(self):
        return build_slot_data(self, self.catalog)

    def generate_output(self, output_directory):
        write_seed_contract_json(self, output_directory)
```

### 13.3 Options

```python
class MC3Options(PerGameCommonOptions):
    progression_mode: Choice  # career, full, chaos
    vehicle_itemization: Choice  # groups, individual, grants, hybrid
    part_itemization: Choice  # tiers, categories, individual
    collectible_checks: Toggle
    collectible_reward_randomization: Toggle
    cosmetic_checks: Toggle
    money_checks: Choice  # off, milestones
    tournament_granularity: Choice  # completion, per_race, both
    club_granularity: Choice
    vanilla_reward_policy: Choice  # suppress_ap_controlled, allow_cosmetic, vanilla
    trap_percentage: Range
    garage_slot_logic: Choice
    starting_city_policy: Choice
    starting_vehicle_policy: Choice
```

### 13.4 Logic

Logic is data-driven:

```python
@dataclass(frozen=True)
class GateDefinition:
    gate_id: GateId
    required_items: FrozenSet[ItemName]
    required_any: Tuple[FrozenSet[ItemName], ...]
    required_counts: Mapping[ItemName, int]
    required_locations: FrozenSet[LocationName]
```

Examples:

```text
Race San Diego Early 01:
  requires:
    - City Permit: San Diego
    - Vehicle Class License: D
    - at least one legal vehicle usable

Vehicle Lamborghini Murcielago:
  requires:
    - Vehicle Category Permit: Exotic
    - Vehicle Class License: A
    - Vehicle Permit: Lamborghini Murcielago

Part Stage 3 Engine:
  requires:
    - Part Category Permit: Engine
    - Progressive Engine Tier x3
```

### 13.5 Completion

Goal options:

```text
Complete Career
Defeat Final Champion
Complete Tokyo Challenge
100% AP Locations
Collect all Rockstar Logos + Final Race
```

Completion condition:

```python
self.multiworld.completion_condition[player] = (
    lambda state: state.has(goal_item_name, player)
)
```

The runtime sends `StatusUpdate(CLIENT_GOAL)` when the corresponding in-game goal check is emitted and AP rules say goal is complete.

---

## 14. Client design

### 14.1 Event-sourced persistence

Use SQLite, not just JSON, for serious development.

Tables:

```sql
received_items(
  ap_index INTEGER PRIMARY KEY,
  item_id INTEGER NOT NULL,
  location_id INTEGER,
  sender INTEGER,
  flags INTEGER,
  received_at TEXT
);

location_checks(
  location_id INTEGER PRIMARY KEY,
  source_event_id INTEGER,
  first_seen_at TEXT,
  sent_to_ap INTEGER NOT NULL DEFAULT 0
);

desired_state_snapshots(
  sequence INTEGER PRIMARY KEY,
  state_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  blob BLOB NOT NULL
);

runtime_events(
  sequence INTEGER PRIMARY KEY,
  event_type TEXT NOT NULL,
  payload BLOB NOT NULL,
  received_at TEXT NOT NULL
);

ap_connection_state(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
```

### 14.2 Main loop

```python
async def run_client(config):
    state_store = SqliteEventStore(config.state_path)
    seed = SeedContractLoader.load(config.seed_contract_path)

    ap = ArchipelagoAdapter(config.ap)
    game = PCSX2MailboxRuntimeAdapter(config.pcsx2)

    service = MC3APClientService(ap, game, state_store, seed)
    await service.run()
```

### 14.3 Reconciliation

```python
async def reconcile_all(self):
    client_state = self.store.load()
    desired = reduce_desired_state(self.seed, client_state)
    await self.game.set_desired_state(desired)
    await self.game.request_runtime_snapshot()
    snapshot = await self.game.get_snapshot()
    validate_runtime_against_desired(snapshot, desired)
```

### 14.4 AP packet handling

On `ReceivedItems`:

1. validate index,
2. if index mismatch, send `Sync` + all known `LocationChecks`,
3. append item log,
4. recompute desired state,
5. send full snapshot to game.

On game `LocationChecked`:

1. append check set,
2. send all unsent checks or full set,
3. persist,
4. recompute desired state if check-gated options exist.

On game `GoalCompleted`:

1. persist goal event,
2. send `StatusUpdate(CLIENT_GOAL)` exactly once.

---

## 15. Payload design

### 15.1 Hook installation

Start from known hooks:

```c
install_hook(loc_4AE100,  mc3ap_SetCarCfgHook);
install_hook(loc_1B0C20,  mc3ap_OnLoadCareerDataDone);
install_hook(loc_1AE8A0,  mc3ap_OnSaveDataHook1);
install_hook(loc_1AF4F8,  mc3ap_OnSaveDataHook2);
install_hook(loc_1AF098,  mc3ap_OnCreateSavegame);
install_hook(loc_3EE860,  mc3ap_OnRaceOver);
install_hook(loc_3EDAC8,  mc3ap_OnRaceFinished);
```

Add discovered hooks as they graduate:

```c
install_hook(loc_event_select,      mc3ap_OnEventSelected);
install_hook(loc_event_start_gate,  mc3ap_OnEventStartAttempt);
install_hook(loc_city_travel,       mc3ap_OnCityTravelAttempt);
install_hook(loc_dealer_purchase,   mc3ap_OnVehiclePurchaseAttempt);
install_hook(loc_garage_select,     mc3ap_OnVehicleSelectAttempt);
install_hook(loc_part_purchase,     mc3ap_OnPartPurchaseAttempt);
install_hook(loc_part_equip,        mc3ap_OnPartEquipAttempt);
install_hook(loc_ability_activate,  mc3ap_OnAbilityActivateAttempt);
install_hook(loc_collectible_pickup,mc3ap_OnCollectiblePickup);
install_hook(loc_reward_apply,      mc3ap_OnVanillaRewardApply);
```

### 15.2 Reconcile loop

```c
void mc3ap_reconcile(void) {
    DesiredState* desired = mailbox_get_desired_state();

    mc3ap_reconcile_cities(desired);
    mc3ap_reconcile_events(desired);
    mc3ap_reconcile_vehicles(desired);
    mc3ap_reconcile_parts(desired);
    mc3ap_reconcile_abilities(desired);
    mc3ap_reconcile_cosmetics(desired);
    mc3ap_reconcile_money(desired);
    mc3ap_reconcile_collectible_rewards(desired);
}
```

Run at:

- profile loaded,
- save loaded,
- desired-state update,
- garage enter,
- garage exit,
- event start,
- city travel,
- race finish,
- reward screen,
- periodic light tick.

### 15.3 Gate evaluation

```c
GateDecision mc3ap_can_start_event(EventId event_id) {
    GateDefinition* gate = catalog_get_event_gate(event_id);
    return gate_eval(gate, desired_state, runtime_state);
}
```

Return:

```c
typedef struct {
    bool allowed;
    uint32_t reason_code;
    uint32_t missing_gate_id;
} GateDecision;
```

### 15.4 Blocking behavior

Every blocking hook must choose from a small set of safe outcomes:

```text
ALLOW_ORIGINAL
BLOCK_RETURN_TO_MENU
BLOCK_SHOW_MESSAGE
BLOCK_FORCE_GARAGE
BLOCK_FORCE_FALLBACK_VEHICLE
SUPPRESS_REWARD
REPAIR_AND_CONTINUE
```

No hook should ad-hoc jump to arbitrary game code unless validated.

---

## 16. Full validation architecture

### 16.1 Validation layers

```text
1. APWorld generation tests
2. Domain reducer tests
3. AP adapter tests
4. Persistence tests
5. Mailbox ABI tests
6. Fake runtime integration tests
7. Payload self-tests
8. PCSX2 bridge tests
9. Emulator probe tests
10. End-to-end scenario tests
```

### 16.2 APWorld tests

Validate:

- every item ID unique
- every location ID unique
- item count equals location count after options
- every gate references existing items/locations
- every generated seed is beatable
- no progression item is unreachable
- no required location has impossible requirements
- catalog hash matches slot data

### 16.3 Domain reducer tests

Properties:

- deterministic: same inputs produce same desired state
- idempotent: applying same AP inventory twice yields same desired state
- monotonic: receiving more progression cannot remove unlocks unless options explicitly allow traps
- money ledger: replay does not double money
- vehicle grants: same AP index cannot duplicate, different AP indexes can if duplicated items are valid
- traps: same trap ID only applies once

### 16.4 AP protocol tests

Fake AP server scenarios:

- successful connection
- connection refused
- reconnect after drop
- `ReceivedItems` in-order
- `ReceivedItems` mismatch => `Sync` + `LocationChecks`
- `ReceivedItems.index == 0` => full inventory reset
- offline received items delivered on reconnect
- duplicate location check safe
- goal status sent once

### 16.5 Mailbox ABI tests

Generate C and Python encoders from one schema.

Tests:

- struct sizes match golden file
- field offsets match golden file
- command roundtrip
- event roundtrip
- endian correctness
- ring overflow behavior
- heartbeat behavior
- desired-state blob checksum

Payload has `_Static_assert` for offsets and sizes.

### 16.6 Payload self-tests

`CMD_RUN_SELF_TEST` returns one result per test:

```text
MAILBOX_MAGIC
ABI_VERSION
GAME_CRC
PROFILE_POINTER
VEHICLE_LIST_POINTER
VEHICLE_COUNT
KNOWN_HOOKS_INSTALLED
COMMAND_RING
EVENT_RING
DESIRED_STATE_PARSE
RUNTIME_SNAPSHOT
```

As hooks graduate:

```text
EVENT_SELECT_HOOK
EVENT_START_GATE_HOOK
CITY_TRAVEL_HOOK
VEHICLE_PURCHASE_HOOK
PART_PURCHASE_HOOK
ABILITY_ACTIVATE_HOOK
COLLECTIBLE_PICKUP_HOOK
VANILLA_REWARD_HOOK
```

### 16.7 Emulator scenario tests

Scenarios are YAML:

```yaml
name: locked_vehicle_cannot_start_race
given:
  desired_state:
    cities: [san_diego]
    vehicle_classes: [D]
    vehicle_categories: [tuner]
    vehicles: []
actions:
  - debug_force_current_vehicle: "nissan_350z"
  - attempt_start_event: "san_diego_ordered_01"
expect:
  gate_blocked: true
  reason: "vehicle_not_permitted"
```

Use two modes:

1. **debug simulated mode** — payload simulates hooks without UI automation.
2. **real runtime mode** — PCSX2 is driven manually or via input script for smoke tests.

### 16.8 Coverage matrix

Every feature must have:

```text
catalog entry
AP item definition if unlockable
AP location definition if checkable
gate definition if progression-relevant
runtime detector
runtime enforcer
unit test
fake runtime test
payload self-test or probe
manual/emulator validation
```

A feature is not “done” until all rows are green.

---

## 17. Risk review and mitigations

### 17.1 Risk: public hook data is insufficient

Mitigation:

- use MC3CarRandomizer hooks as foothold,
- maintain reverse-engineering checklist,
- do not call a feature complete until hook is discovered and tested.

### 17.2 Risk: vanilla rewards bypass AP

Mitigation:

- reward suppressor hook,
- transition repair passes,
- validation scenarios for every vanilla unlock.

### 17.3 Risk: savestates duplicate or roll back progress

Mitigation:

- AP state authoritative,
- received items indexed,
- money total ledger,
- check set replay,
- forbid checkable play while Python disconnected unless save flags are recoverable.

### 17.4 Risk: garage full loses AP-granted vehicles

Mitigation:

- AP garage slot model,
- direct grants go to pending claim queue if garage full,
- no silent conversion to cash unless item semantics explicitly say so.

### 17.5 Risk: per-vehicle/part catalog is wrong

Mitigation:

- generated catalog hash,
- runtime validation against vehicle list pointer,
- cross-check extracted assets with public guide data,
- catalog diff tests.

### 17.6 Risk: UI shows locked content even if start is blocked

Mitigation:

- start with hard functional gate,
- add UI hide/lock overlays later,
- no progression depends on UI hiding.

### 17.7 Risk: process-memory bridge fragile

Mitigation:

- mailbox magic scan, not fixed address,
- version checks,
- no baseline PCSX2 fork requirement; use mailbox magic scan, executable/CRC validation, ABI checks, and per-PCSX2-version bridge tests; optional emulator-side IPC only if it can be upstreamed or kept out of the main user path.

### 17.8 Risk: performance degradation

Mitigation:

- event-driven hooks,
- cached bitsets,
- fixed-size data,
- no allocations in payload hot paths,
- periodic light repair only.

### 17.9 Risk: AP item duplicates beyond normal game expectations

Mitigation:

- every AP item has instance identity via received item index,
- direct grants handle duplicates through explicit policy,
- permits are idempotent bitsets,
- money is total ledger.

### 17.10 Risk: legal/distribution issues

Mitigation:

- distribute no game assets,
- require user-provided legally dumped ISO,
- generate/patch locally,
- avoid shipping modified `ASSETS.DAT`.

---

## 18. Implementation sequence without feature removal

This sequence does not cut final scope; it reduces risk by building the architecture first.

### Phase 0 — contracts and skeleton

Deliverables:

- APWorld skeleton
- full item/location schema
- seed contract schema
- domain reducer
- fake runtime
- fake AP server
- validation runner

Exit criteria:

- fake E2E can receive item, unlock vehicle/city/part in fake runtime, emit check, send AP packet.

### Phase 1 — payload foothold

Deliverables:

- injected ELF
- mailbox
- known MC3CarRandomizer-derived hooks
- heartbeat
- profile/vehicle list probes
- race finish event probe

Exit criteria:

- Python finds mailbox and receives payload events.

### Phase 2 — event catalog

Deliverables:

- event selection/current event hook
- stable event IDs
- race win/loss classification
- race/tournament/club catalog

Exit criteria:

- every race completion emits correct AP location in debug seed.

### Phase 3 — core gates

Deliverables:

- city gate
- event start gate
- class/category/vehicle use gate
- money ledger
- vanilla reward suppressor first pass

Exit criteria:

- AP items control access to cities, events, vehicles, and money.

### Phase 4 — full vehicle/garage coverage

Deliverables:

- purchase hook
- garage ownership structure
- direct vehicle grants
- prize car handling
- garage slot logic
- vehicle purchase/ownership checks

Exit criteria:

- every vehicle can be itemized and checked.

### Phase 5 — parts/customization coverage

Deliverables:

- part catalog
- purchase/equip hooks
- performance parts
- visual parts
- cosmetics
- repair on garage exit/race start

Exit criteria:

- every part/cosmetic can be itemized and checked.

### Phase 6 — collectibles and rewards

Deliverables:

- logo pickup hook
- logo bitset
- 36 individual checks
- 12/24/36 tier reward suppression/grants

Exit criteria:

- all logo pickups emit stable checks and rewards are AP-controlled.

### Phase 7 — polish and release

Deliverables:

- UI messages
- installer
- setup docs
- launcher integration
- PCSX2 IPC hardening
- compatibility checks
- full scenario suite

Exit criteria:

- full seed is playable and deterministic.

---

## 19. Reviewed assumptions

### Assumption: “MC3CarRandomizer proves enough to start.”

Status: valid but limited. It proves a plugin ELF and several hooks for the target build, not every hook we need.

### Assumption: “Race finish hook can detect checks.”

Status: partially valid. The hook exists, but we still need stable event identity and win/loss classification.

### Assumption: “Vehicle list pointer solves vehicle unlocks.”

Status: partial. It gives vehicle names/count, but not ownership, purchase, category/class struct layout, or garage management.

### Assumption: “Collectibles can be checks.”

Status: conceptually valid. Public sources confirm collectible logos exist and have 12/24/36 rewards. Runtime pickup detection and bitset layout are unknown.

### Assumption: “Parts can be itemized.”

Status: design-valid, implementation unknown. Requires part catalog and purchase/equip hooks.

### Assumption: “Python process-memory bridge is stable enough.”

Status: acceptable baseline if validated across target PCSX2 stable/nightly versions. Do not require a fork unless stock PCSX2 cannot support a required capability. Treat emulator-side IPC as optional future polish, not required architecture.

### Assumption: “All AP-controlled vanilla rewards can be suppressed.”

Status: likely but unproven. Requires reward hook and repair pass.

---

## 20. Final architecture summary

The full-coverage version is feasible if treated as a reverse-engineering-heavy N-tier system.

The safest final architecture is:

```text
APWorld:
  deterministic generation and full catalog/logic

Python domain core:
  pure reducer from AP log + check set + seed contract to DesiredGameState

Python application:
  AP protocol, persistence, reconciliation, validation

PCSX2 adapter:
  mailbox transport only

Payload:
  MC3 hooks, gate enforcement, runtime snapshots, event detection

Validation:
  fake AP, fake runtime, mailbox ABI, payload self-tests, emulator scenarios
```

No feature is removed. The simplification is that every feature becomes data:

```text
ItemDefinition
LocationDefinition
GateDefinition
RuntimeDetector
RuntimeEnforcer
ValidationScenario
```

When a new vehicle, part, collectible, race, or reward is discovered, it is added to the catalog and automatically participates in AP generation, runtime enforcement, and validation.

---

## 21. Archipelago upstream compliance addendum

This section updates the design against the current Archipelago `adding games.md`, `contributing.md`, `style.md`,
`tests.md`, `world api.md`, `options api.md`, `apworld specification.md`, and `world maintainer.md` documents.

Source documents reviewed:

- `docs/adding games.md` — https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/adding%20games.md
- `docs/contributing.md` — https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/contributing.md
- `docs/style.md` — https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/style.md
- `docs/tests.md` — https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/tests.md
- `docs/world api.md` — https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/world%20api.md
- `docs/options api.md` — https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/options%20api.md
- `docs/apworld specification.md` — https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/apworld%20specification.md
- `docs/apworld_dev_faq.md` — https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/apworld_dev_faq.md
- `docs/world maintainer.md` — https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/world%20maintainer.md
- `docs/network protocol.md` — https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/network%20protocol.md

### 21.1 Compliance stance

The MC3 integration has two distribution modes:

1. **Unofficial / custom APWorld mode** — the world is packaged as `mc3.apworld`, and the PCSX2 client/payload
   ships separately. This should be the first public test distribution.
2. **Upstream mode** — the world is submitted to the main Archipelago repository. This requires tighter
   compliance with world tests, docs, style, launcher integration, maintainer responsibilities, and reviewability.

The PCSX2 payload/client design is allowed by the Archipelago model because the `adding games.md` doc explicitly says
that game modification varies by system and engine and is not prescribed by the world docs. The part that must match
Archipelago closely is the Python APWorld and the external client protocol behavior.

### 21.2 Client hard requirements to encode explicitly

The external MC3 client must support:

- both `ws://` and `wss://` Archipelago server connections;
- automatic reconnect after unstable/lost connections;
- editable saved connection info, especially port changes for rooms moved by the website;
- sending `StatusUpdate` when MC3 completion is achieved;
- sending `LocationChecks` when runtime checks are detected;
- sending one-time checks on connect if they occurred while disconnected and are recoverable from save/runtime flags;
- parsing and applying `ReceivedItems` on demand;
- handling duplicate/copy items beyond the number vanilla MC3 expects;
- handling admin/server-created items with no player/location attribution;
- persisting `last_processed_item_index` locally;
- accepting items sent while disconnected;
- resyncing with `Sync` plus full `LocationChecks` on item-index mismatch;
- treating `ReceivedItems.index == 0` as full inventory replacement;
- supporting per-message compression for WebSocket sessions.

Client configuration object:

```python
@dataclass(frozen=True)
class APConnectionConfig:
    host: str
    port: int
    slot_name: str
    password: str | None
    use_tls: bool
    uuid: str
```

State keys must not include host/port, because the same room can move ports. State should be keyed by:

```text
(seed_name, game_name, slot_name, profile_hash, slot_id if known)
```

### 21.3 Launcher integration requirement

The Python client should register an Archipelago Launcher `Component` when shipped inside an AP repository/fork:

```python
from LauncherComponents import Component, components, launch_subprocess


def launch_mc3_client(*args: str) -> None:
    from .client import main
    launch_subprocess(main, name="Midnight Club 3 Client", args=args)


components.append(Component(
    display_name="Midnight Club 3 Client",
    func=launch_mc3_client,
    game_name="Midnight Club 3: DUB Edition Remix",
    supports_uri=True,
    file_identifier=".apmc3",
    description="Connects Midnight Club 3: DUB Edition Remix running in PCSX2 to Archipelago.",
))
```

Exact function names should be verified against the current `LauncherComponents` implementation during coding.

### 21.4 World package requirements

The upstream world package must include:

```text
worlds/mc3/
  __init__.py
  archipelago.json
  items.py
  locations.py
  options.py
  regions.py
  rules.py
  slot_data.py
  catalog.py
  docs/
    setup_en.md
    en_Midnight Club 3 DUB Edition Remix.md
  data/
    static_catalog/
    schema/
  test/
    __init__.py
    bases.py
    test_default.py
    test_access.py
    test_item_pool.py
    test_options.py
```

Rules:

- every Python-containing subdirectory under `worlds/mc3` must contain `__init__.py`;
- `archipelago.json` must at minimum contain `{ "game": "Midnight Club 3: DUB Edition Remix" }`;
- for custom `.apworld` distribution, the package must be lower-case as `mc3.apworld`;
- non-runtime dev tools, extraction scripts, symbol files, emulator logs, and large generated catalogs should be excluded
  from `.apworld` packaging using `.apignore` if they are not needed at generation/runtime;
- no copyrighted game assets, ISO files, extracted assets, or rebuilt `ASSETS.DAT` files may ship in the APWorld.

Recommended `archipelago.json`:

```json
{
  "game": "Midnight Club 3: DUB Edition Remix",
  "world_version": "0.1.0",
  "minimum_ap_version": "0.6.4",
  "authors": ["Joshua Prier"]
}
```

The `minimum_ap_version` value must be verified against the actual target Archipelago version before release.

### 21.5 `World` and `WebWorld` skeleton

```python
from BaseClasses import Item, ItemClassification, Location, Region
from worlds.AutoWorld import Tutorial, WebWorld, World

from .items import ITEM_NAME_TO_ID, ITEM_TABLE, filler_item_names
from .locations import LOCATION_NAME_TO_ID
from .options import MC3Options


class MC3Item(Item):
    game = "Midnight Club 3: DUB Edition Remix"


class MC3Location(Location):
    game = "Midnight Club 3: DUB Edition Remix"


class MC3WebWorld(WebWorld):
    theme = "ocean"
    rich_text_options_doc = True
    tutorials = [
        Tutorial(
            "Multiworld Setup Guide",
            "A guide to setting up Midnight Club 3: DUB Edition Remix for Archipelago.",
            "English",
            "setup_en.md",
            "setup/en",
            ["Joshua Prier"],
        )
    ]
    bug_report_page = "https://github.com/<owner>/<repo>/issues"


class MC3World(World):
    """Drive through MC3 Remix while Archipelago controls career progression, vehicles, upgrades, and collectibles."""

    game = "Midnight Club 3: DUB Edition Remix"
    web = MC3WebWorld()
    options_dataclass = MC3Options
    options: MC3Options
    topology_present = True

    item_name_to_id = ITEM_NAME_TO_ID
    location_name_to_id = LOCATION_NAME_TO_ID
    item_name_groups = {
        "Vehicles": set(),
        "Performance Parts": set(),
        "Visual Parts": set(),
        "Collectibles": set(),
        "Progression": set(),
        "Money": set(),
        "Traps": set(),
    }
    location_name_groups = {
        "Races": set(),
        "Tournaments": set(),
        "Club Races": set(),
        "Collectibles": set(),
        "Garages": set(),
        "Dealerships": set(),
    }

    def create_item(self, name: str) -> MC3Item:
        definition = ITEM_TABLE[name]
        return MC3Item(name, definition.classification, definition.ap_id, self.player)

    def get_filler_item_name(self) -> str:
        return self.random.choice(filler_item_names)

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        self.multiworld.regions.append(menu)
        # Create abstract progression regions from the generated catalog.
        # Do not replace self.multiworld.regions with assignment.

    def create_items(self) -> None:
        # Build the item pool to exactly match fillable locations.
        # Manually placed event items/precollected items must not be added to itempool.
        self.multiworld.itempool += self.build_item_pool()

    def set_rules(self) -> None:
        # Apply catalog-derived access rules.
        pass

    def fill_slot_data(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "game_build": "SLUS-21355",
            "expected_crc": "60A42FF5",
            "gate_contract": self.build_gate_contract(),
            "runtime_catalog_hash": self.runtime_catalog_hash,
        }
```

### 21.6 Options design requirements

`options.py` must use Archipelago `Option` classes and a dataclass inheriting from `PerGameCommonOptions`.
Each option class needs a user-facing docstring and `display_name`.

Initial option groups:

- **Progression Coverage** — city progression, class progression, tournament goal, race density;
- **Vehicle Coverage** — individual vehicle items, category permits, prize cars, motorcycle inclusion;
- **Parts Coverage** — performance parts, visual parts, cosmetics, garage customization;
- **Collectibles Coverage** — Rockstar logos as checks, collectible rewards;
- **Difficulty / Logic** — strict logic, accessibility, early sphere assists;
- **Client / Runtime Safety** — require client connected, savestate warnings, soft/hard gate mode.

Use option presets for common configurations:

```text
Starter Coverage
Full Coverage
Vehicle Chaos
Collectible Hunt
Race-Only Debug
```

Do not define `option_random`; Archipelago reserves `random` for fixed option types.

### 21.7 Itempool and manual-placement rules

The world must maintain this invariant:

```text
count(fillable_locations) == count(items_in_multiworld_itempool)
```

Do not add these to `multiworld.itempool`:

- event-only items used purely for logic;
- world-defined start inventory added via `multiworld.push_precollected`;
- manually locked items placed with direct placement APIs;
- seed-contract-only runtime markers;
- diagnostic/debug-only items.

If a feature needs deterministic placement, use the appropriate AP placement mechanism and keep it out of the standard
itempool. The design must not both manually place an item and submit that same item to the multiworld itempool.

### 21.8 Security and parsing rules

- No `eval` or `exec` in APWorld, catalog loading, option handling, scenario validation, or generated code.
- Avoid direct unsafe PyYAML use. Use Archipelago `Utils.parse_yaml` where YAML is necessary.
- Prefer JSON with schema validation for generated runtime contracts.
- Validate every generated contract with schema version, expected game build, expected CRC, and catalog hash.
- Fail closed if a client/payload/slot-data schema mismatch is detected.

### 21.9 Style rules

Apply Archipelago style in upstream-facing Python files:

- 120-character line limit;
- double-quoted strings;
- PEP8 style with Archipelago exceptions;
- type annotations for function signatures and class members where possible;
- new-style annotations like `dict[str, int]`;
- no trailing whitespace;
- markdown files should also target 120-character lines and avoid lazy numbering.

The injected payload can use a separate C style, but upstream Python/doc files should conform to Archipelago style.

### 21.10 Upstream test package

Add `worlds/mc3/test/`:

```text
worlds/mc3/test/
  __init__.py
  bases.py
  test_default.py
  test_access.py
  test_options.py
  test_item_pool.py
  test_slot_data.py
```

`bases.py`:

```python
from test.bases import WorldTestBase


class MC3TestBase(WorldTestBase):
    game = "Midnight Club 3: DUB Edition Remix"
```

Required upstream tests:

- default generation/fill works;
- all-state can reach everything;
- empty-state can reach at least something;
- generated item count equals generated fillable location count;
- filler item is repeatable and never unique progression;
- all option presets generate successfully;
- full coverage option set generates successfully;
- vehicle-only, parts-only, collectibles-only debug configurations generate successfully;
- every gate references a known item or event;
- every runtime location maps to a known AP location ID;
- `fill_slot_data` includes schema version, build, CRC, gate contract, and catalog hash;
- no large/expensive file parsing is performed at world import time.

Heavy randomized soak tests should not run in normal CI. Keep those under a local validation command or skip behind an
environment variable.

### 21.11 Development order adjusted to Archipelago guidance

The APWorld Dev FAQ recommends not doing 100% client first or 100% APWorld first. The adjusted plan is:

1. Create one client proof-of-concept for each major in-game operation type:
   - detect one race check;
   - grant one money item;
   - lock/unlock one city/race gate;
   - detect one collectible;
   - lock/unlock one vehicle;
   - lock/unlock one part;
   - display one message.
2. Create a trivial APWorld that always generates a tiny fixed set of items and locations.
3. Run a real end-to-end local server test with the trivial APWorld, PCSX2, payload, and Python client.
4. Expand catalogs feature-by-feature until full coverage is reached.
5. Only after full validation, decide whether to distribute as custom APWorld or submit upstream.

### 21.12 Maintainer obligations if upstreamed

If merged into the core Archipelago repo, the world author becomes a world maintainer unless another maintainer is
nominated. This implies:

- being reachable on the Archipelago Discord;
- reviewing or organizing reviews for MC3 world pull requests;
- fixing issues when core changes break MC3;
- watching GitHub/Discord for relevant updates;
- testing on main, especially during release-candidate phases;
- communicating long unavailability periods;
- keeping `CODEOWNERS` current.

This means upstreaming should wait until the client and validation setup are maintainable by more than one person or at
least documented enough that another maintainer could debug common failures.

### 21.13 New risks found during Archipelago doc review

| Risk | Why it matters | Mitigation |
|---|---|---|
| World import becomes slow due to large catalogs | AP docs warn world loading can be delayed by expensive import-time data parsing | Pre-generate compact Python/JSON data and lazy-load heavy validation-only catalogs outside world import |
| Non-repeatable filler item chosen by default | Default filler selection can choose any item from `item_name_to_id` | Implement `get_filler_item_name` with a safe repeatable filler list |
| Port change loses local AP state | AP rooms can move ports | Key state by seed/slot/profile, not host/port; expose editable host/port |
| Packaged `.apworld` misses Python subpackages | Frozen builds require `__init__.py` in Python subfolders | Add package validation in CI |
| Manual placement duplicates itempool entries | AP disallows manually placed items also being in itempool | Add itempool invariant tests |
| Test suite becomes too slow | AP tests should be fast and runner-agnostic | Keep normal APWorld tests under 1s each; move emulator/e2e soak tests outside upstream CI |
| Unsafe config parsing | AP discourages unsafe YAML and prohibits most `eval` use | Use `Utils.parse_yaml` or JSON schema; no `eval`/`exec` |
| Upstream maintainer burden underestimated | World maintainer responsibilities are ongoing | Start as custom APWorld until runtime and docs are stable |

### 21.14 Updated acceptance checklist

A release candidate is not ready until all of the following pass:

```text
[ ] APWorld folder has required docs, WebWorld, Tutorial, options_dataclass, item/location ID maps.
[ ] Every Python-containing world subfolder has __init__.py.
[ ] World imports quickly and does not parse large extracted game data at import time.
[ ] create_regions creates Menu and all abstract regions without assigning over multiworld.regions.
[ ] create_items appends/extends itempool and never assigns over multiworld.itempool.
[ ] Item count equals fillable location count for every supported option preset.
[ ] No manually placed item also appears in the normal itempool.
[ ] get_filler_item_name returns only repeatable filler.
[ ] Options have docstrings, display names, groups, and useful presets.
[ ] Client supports ws and wss.
[ ] Client supports editable saved host/port/password/slot.
[ ] Client stores AP state independently from host/port.
[ ] Client handles ReceivedItems index mismatch with Sync + LocationChecks.
[ ] Client treats ReceivedItems index 0 as full inventory replacement.
[ ] Client handles duplicate/admin-created items.
[ ] Client sends StatusUpdate on goal exactly once.
[ ] Client recovers offline one-time checks from runtime/save flags wherever possible.
[ ] Launcher Component exists for source/fork distribution.
[ ] Custom APWorld packaging builds via Build APWorlds.
[ ] .apignore excludes dev-only/generated-heavy files.
[ ] Unit tests cover default/full/debug presets and access dependencies.
[ ] Emulator scenario tests cover every runtime detector and enforcer.
[ ] Maintainer docs explain how to debug every hook and interface.
```
