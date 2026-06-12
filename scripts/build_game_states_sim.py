#!/usr/bin/env python3
"""Build browser-friendly game state simulation pack from enum catalog."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "game-states" / "asa_creature_item_player.json"
FULL = ROOT / "game-states" / "asa_game_states.json"
OUT = ROOT / "game-states" / "asa_game_states_sim.json"

KEY_ENUMS = (
    "ENetModeBP",
    "EPrimalItemType",
    "ECheatActorType",
    "EPrimalMilestoneType",
    "EActorListsBP",
)

ENUM_BLURBS = {
    "ENetModeBP": "How the session runs (SP uses Standalone).",
    "EPrimalItemType": "Item classification inside PrimalItem actors.",
    "ECheatActorType": "Cheat/target filters for dinos, tames, players, structures.",
    "EPrimalMilestoneType": "Progression and tribe-log milestone families.",
    "EActorListsBP": "Actor list buckets the game uses for wild/tamed/player tracking.",
}

SCENARIOS = [
    {
        "id": "craft_tek_rifle_sp",
        "title": "Craft Tek Rifle (Singleplayer)",
        "summary": "Player crafts a weapon; item type and class ref land in the save.",
        "entity_class_ref": "PrimalItem_TekRifle_C",
        "net_mode": "Standalone",
        "steps": [
            {
                "layer": "session",
                "title": "Session mode",
                "detail": "Singleplayer runs ENetModeBP::Standalone — client-trusted, no dedicated server.",
                "hooks": ["ENetModeBP:Standalone"],
            },
            {
                "layer": "input",
                "title": "Craft action",
                "detail": "Player completes fabricator craft.",
                "hooks": ["EPrimalMilestoneType:Craft"],
            },
            {
                "layer": "gamestate",
                "title": "Item typed in memory",
                "detail": "Game assigns EPrimalItemType::Weapon to the PrimalItem instance.",
                "hooks": ["EPrimalItemType:Weapon"],
            },
            {
                "layer": "instance",
                "title": "Blueprint instance",
                "detail": "Inventory holds PrimalItem_TekRifle_C with UE soft path to Tek Rifle blueprint.",
                "hooks": ["class_ref:PrimalItem_TekRifle_C"],
            },
            {
                "layer": "disk",
                "title": "Save persistence",
                "detail": "Exit save mirrors class ref and /Game/ path — observable on disk only.",
                "hooks": ["persistence:save_ark", "evidence:in_session_save"],
            },
            {
                "layer": "assessment",
                "title": "Trust note",
                "detail": "Monitor sees disk evidence; does not read live AShooterGameState memory.",
                "hooks": ["monitor:disk_only"],
            },
        ],
    },
    {
        "id": "tek_rifle_combat",
        "title": "Tek Rifle structure destruction",
        "summary": "Weapon damage milestone + tribe log kill/destroy events.",
        "entity_class_ref": "PrimalItem_TekRifle_C",
        "net_mode": "Standalone",
        "steps": [
            {
                "layer": "session",
                "title": "Combat loadout",
                "detail": "Player wields Tek Rifle (ammo: PrimalItemAmmo_GrapplingHook_C in same session).",
                "hooks": ["EPrimalItemType:Weapon", "EPrimalItemType:Ammo"],
            },
            {
                "layer": "input",
                "title": "Fire / damage",
                "detail": "Projectiles apply damage to structures and dinos.",
                "hooks": ["EPrimalMilestoneType:WeaponDamage", "EPrimalMilestoneType:Kill"],
            },
            {
                "layer": "gamestate",
                "title": "Actor classification",
                "detail": "Targets resolve through ECheatActorType (Structure, Dino, Tame).",
                "hooks": ["ECheatActorType:Structure", "ECheatActorType:Dino", "ECheatActorType:Tame"],
            },
            {
                "layer": "disk",
                "title": "Save delta",
                "detail": "Main save grows; rolling .arkbak captures intermediate states.",
                "hooks": ["persistence:save_ark", "persistence:arkbak"],
            },
            {
                "layer": "tribe_log",
                "title": "Tribe log (RichColor)",
                "detail": "Destroyed/killed lines written to tribe log — separate persistence layer.",
                "hooks": ["persistence:tribe_log", "EPrimalMilestoneType:Kill"],
            },
        ],
    },
    {
        "id": "tame_oasisaur",
        "title": "Tame Oasisaur",
        "summary": "Creature actor type + tame milestone; tribe log upload/download.",
        "entity_class_ref": "Oasisaur_Character_BP_C",
        "net_mode": "Standalone",
        "steps": [
            {
                "layer": "input",
                "title": "Tame completion",
                "detail": "Taming bar completes on wild creature.",
                "hooks": ["EPrimalMilestoneType:Tame"],
            },
            {
                "layer": "gamestate",
                "title": "Actor becomes tame",
                "detail": "Creature actor classified as ECheatActorType::Tame.",
                "hooks": ["ECheatActorType:Tame", "ECheatActorType:Dino"],
            },
            {
                "layer": "instance",
                "title": "Character blueprint",
                "detail": "DinoCharacter with Oasisaur_Character_BP_C class ref.",
                "hooks": ["class_ref:Oasisaur_Character_BP_C"],
            },
            {
                "layer": "tribe_log",
                "title": "Tribe log entry",
                "detail": "Tamed a … line appears in tribe log delta.",
                "hooks": ["persistence:tribe_log", "EPrimalMilestoneType:Tame"],
            },
            {
                "layer": "disk",
                "title": "Save + log",
                "detail": "Creature state in save; tribe log in separate Saved file.",
                "hooks": ["persistence:save_ark"],
            },
        ],
    },
    {
        "id": "admin_giveitem",
        "title": "Admin giveitem (cheat path)",
        "summary": "Console cheat bypasses craft; still persists as PrimalItem class ref.",
        "entity_class_ref": "PrimalItem_TekRifle_C",
        "net_mode": "Standalone",
        "steps": [
            {
                "layer": "input",
                "title": "EnableCheats + giveitem",
                "detail": "UShooterCheatManager accepts blueprint soft path from console.",
                "hooks": ["surface:UShooterCheatManager", "surface:PrimalConsole"],
            },
            {
                "layer": "gamestate",
                "title": "Item spawned to inventory",
                "detail": "Same EPrimalItemType::Weapon typing as crafted item.",
                "hooks": ["EPrimalItemType:Weapon"],
            },
            {
                "layer": "instance",
                "title": "Class ref on disk",
                "detail": "PrimalItem_TekRifle_C appears in save strings after exit.",
                "hooks": ["class_ref:PrimalItem_TekRifle_C"],
            },
            {
                "layer": "assessment",
                "title": "Why this matters",
                "detail": "Client-trusted inventory persistence — same disk signal as legit craft.",
                "hooks": ["trust:client_inventory"],
            },
        ],
    },
    {
        "id": "spawn_creature_cheat",
        "title": "SpawnExactDino (cheat path)",
        "summary": "Spawn creature by blueprint; actor lists and cheat actor type apply.",
        "entity_class_ref": "Dodo_Character_BP_C",
        "net_mode": "Standalone",
        "steps": [
            {
                "layer": "input",
                "title": "SpawnExactDino",
                "detail": "Cheat manager instantiates Character_BP from soft path.",
                "hooks": ["surface:UShooterCheatManager"],
            },
            {
                "layer": "gamestate",
                "title": "Actor list registration",
                "detail": "Spawned dino enters AL_TAMED_DINOS or wild lists per state.",
                "hooks": ["EActorListsBP:AL_TAMED_DINOS", "ECheatActorType:Dino"],
            },
            {
                "layer": "instance",
                "title": "Character class",
                "detail": "Dodo_Character_BP_C (example) written to world save blob.",
                "hooks": ["class_ref:Dodo_Character_BP_C"],
            },
            {
                "layer": "disk",
                "title": "World persistence",
                "detail": "Dino entities persist in .ark; monitor can mirror on change.",
                "hooks": ["persistence:save_ark", "monitor:disk_only"],
            },
        ],
    },
]


def main() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    full = json.loads(FULL.read_text(encoding="utf-8"))
    enums = data.get("enums", {})
    full_enums = full.get("enums", {})
    picked = {}
    for name in KEY_ENUMS:
        src = enums.get(name) or full_enums.get(name)
        if src:
            picked[name] = {
                "values": src.get("values", []),
                "sources": src.get("sources", []),
                "categories": src.get("categories", []),
                "blurb": ENUM_BLURBS.get(name, ""),
            }

    pack = {
        "schema_version": 1,
        "purpose": "browser_game_state_simulation",
        "source": "asa_creature_item_player.json",
        "summary": data.get("summary", {}),
        "persistence_layers": [
            {
                "id": "memory",
                "label": "In-memory GameState",
                "client_trusted": True,
                "disk_observable": False,
                "note": "Live replication, projectiles, inventory — not captured by this monitor.",
            },
            {
                "id": "save_ark",
                "label": "Main save (.ark)",
                "client_trusted": True,
                "disk_observable": True,
                "note": "Class refs and /Game/ paths — primary crosswalk join.",
            },
            {
                "id": "arkbak",
                "label": "Rolling backup (.arkbak)",
                "client_trusted": True,
                "disk_observable": True,
                "note": "Slot rotation captures combat/session deltas.",
            },
            {
                "id": "tribe_log",
                "label": "Tribe log",
                "client_trusted": True,
                "disk_observable": True,
                "note": "RichColor kill/tame/destroy lines — milestone correlation.",
            },
            {
                "id": "primal_console",
                "label": "PrimalConsole history",
                "client_trusted": True,
                "disk_observable": True,
                "note": "EnableCheats, giveitem, debug commands.",
            },
        ],
        "key_enums": picked,
        "scenarios": SCENARIOS,
        "enum_catalog_size": len(enums),
    }
    OUT.write_text(json.dumps(pack, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} ({len(SCENARIOS)} scenarios, {len(picked)} key enums)")


if __name__ == "__main__":
    main()