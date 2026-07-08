"""Tools for MC3 Archipelago integration.

extract_assets.py         — extract ASSETS.DAT via dave.py
extract_vehicle_catalog.py — parse vehicle.lst to JSON
extract_part_catalog.py   — extract part definitions
extract_event_catalog.py  — map events to stable IDs
probe_memory.py           — find MC3AP mailbox in PCSX2 process memory
probe_runtime_addresses.py — discover hook addresses at runtime
generate_mailbox_abi.py   — generate C/Python mailbox structs from schema
generate_pnach_debug.py   — generate PNACH debug patches
build_seed_contract.py    — package seed contract for client
"""