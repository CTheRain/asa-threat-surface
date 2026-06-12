#!/usr/bin/env python3
"""Build drag-and-drop LLM lookup pack from item_creature_crosswalk_v2."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"S:\ARK_LiveData")
BUNDLES = ROOT / "bundles"
CROSSWALK_JSONL = BUNDLES / "item_creature_crosswalk_v2.jsonl"
CROSSWALK_JSON = BUNDLES / "item_creature_crosswalk_v2.json"
SESSION_BUNDLE = BUNDLES / "session_20260611_center_combat_destruction_v1.json"

OUT_JSON = BUNDLES / "asa_game_lookup_v1.json"
OUT_JSON_MIN = BUNDLES / "asa_game_lookup_v1.min.json"
OUT_MD = BUNDLES / "asa_game_lookup_v1.md"
OUT_QUICK_JSON = BUNDLES / "asa_game_lookup_quick_v1.json"
OUT_PROMPT = BUNDLES / "asa_game_lookup_system_prompt_v1.txt"


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def compact_entity(row: dict) -> dict:
    return {
        "id": row["row_id"],
        "kind": row["kind"],
        "display_name": row["display_name"],
        "blueprint_stem": row["blueprint_stem"],
        "class_ref": row["class_ref_C"],
        "asset_path": row["mxcheatui_asset_path"],
        "blueprint_ue": row["blueprint_path_ue"],
        "pack": row["dlc_or_pack"],
        "category": row["path_category"],
        "variants": row["variant_tags"],
        "item_type": row["e_primal_item_type_guess"],
        "actor_type": row["e_cheat_actor_type_guess"],
        "enum_hooks": row["game_state_enum_hooks"],
        "giveitem": row["cheat_giveitem_template"],
        "spawn_dino": row["cheat_spawn_dino_template"],
        "in_session_save": row["in_session_save_221210"] == "Y",
        "session_combat": row["session_combat_v1"] == "Y",
        "tribe_log_hit": row["tribe_log_display_name_hit"] == "Y",
        "tags": row["assessment_tags"].split(";") if row["assessment_tags"] else [],
        "name_confidence": row["display_name_confidence"],
    }


def entity_card_text(entity: dict) -> str:
    lines = [
        f"**{entity['display_name']}** (`{entity['class_ref']}`)",
        f"- Kind: {entity['kind']} | Pack: {entity['pack']} | Category: {entity['category']}",
        f"- Asset path: `{entity['asset_path']}`",
        f"- Blueprint (UE): `{entity['blueprint_ue']}`",
    ]
    if entity["item_type"]:
        lines.append(f"- Item type guess: {entity['item_type']}")
    if entity["actor_type"]:
        lines.append(f"- Actor type guess: {entity['actor_type']}")
    if entity["enum_hooks"]:
        lines.append(f"- Game-state hooks: {entity['enum_hooks']}")
    if entity["giveitem"]:
        lines.append(f"- Give item: `{entity['giveitem']}`")
    if entity["spawn_dino"]:
        lines.append(f"- Spawn dino: `{entity['spawn_dino']}`")
    flags = []
    if entity["in_session_save"]:
        flags.append("in_session_save")
    if entity["session_combat"]:
        flags.append("session_combat")
    if entity["tribe_log_hit"]:
        flags.append("tribe_log")
    if flags:
        lines.append(f"- Verified flags: {', '.join(flags)}")
    if entity["tags"]:
        lines.append(f"- Tags: {', '.join(entity['tags'][:12])}")
    return "\n".join(lines)


def load_rows() -> list[dict]:
    rows = []
    with CROSSWALK_JSONL.open(encoding="utf-8") as fh:
        for line in fh:
            rows.append(json.loads(line))
    return rows


def build_indexes(entities: dict[str, dict]) -> dict:
    by_display_name: dict[str, list[str]] = defaultdict(list)
    by_class_ref: dict[str, str] = {}
    by_stem: dict[str, str] = {}
    by_kind: dict[str, list[str]] = defaultdict(list)
    by_pack: dict[str, list[str]] = defaultdict(list)
    by_tag: dict[str, list[str]] = defaultdict(list)
    by_item_type: dict[str, list[str]] = defaultdict(list)
    by_actor_type: dict[str, list[str]] = defaultdict(list)
    session_verified: list[str] = []
    session_combat: list[str] = []
    tribe_log: list[str] = []
    tek: list[str] = []
    weapons: list[str] = []
    structures: list[str] = []

    for class_ref, ent in entities.items():
        by_class_ref[class_ref] = class_ref
        by_stem[ent["blueprint_stem"]] = class_ref
        by_display_name[normalize_key(ent["display_name"])].append(class_ref)
        by_kind[ent["kind"]].append(class_ref)
        if ent["pack"]:
            by_pack[ent["pack"]].append(class_ref)
        for tag in ent["tags"]:
            by_tag[tag].append(class_ref)
        if ent["item_type"]:
            by_item_type[ent["item_type"]].append(class_ref)
        if ent["actor_type"]:
            by_actor_type[ent["actor_type"]].append(class_ref)
        if ent["in_session_save"]:
            session_verified.append(class_ref)
        if ent["session_combat"]:
            session_combat.append(class_ref)
        if ent["tribe_log_hit"]:
            tribe_log.append(class_ref)
        if any("tek" in t for t in ent["tags"]):
            tek.append(class_ref)
        if ent["item_type"] == "Weapon":
            weapons.append(class_ref)
        if ent["item_type"] == "Structure":
            structures.append(class_ref)

        # alias keys: stem tokens, path tail words
        for alias in {
            normalize_key(ent["blueprint_stem"]),
            normalize_key(ent["blueprint_stem"].replace("PrimalItem_", "").replace("PrimalItem", "")),
            normalize_key(class_ref.replace("_C", "")),
        }:
            if alias and alias not in by_display_name:
                by_display_name[alias].append(class_ref)

    return {
        "by_display_name": dict(by_display_name),
        "by_class_ref": by_class_ref,
        "by_stem": by_stem,
        "by_kind": dict(by_kind),
        "by_pack": dict(by_pack),
        "by_tag": dict(by_tag),
        "by_item_type": dict(by_item_type),
        "by_actor_type": dict(by_actor_type),
        "collections": {
            "session_verified": session_verified,
            "session_combat": session_combat,
            "tribe_log_hits": tribe_log,
            "tek": tek,
            "weapons": weapons,
            "structures": structures,
        },
    }


def llm_instructions() -> str:
    return """You have ASA (ARK Survival Ascended) game lookup data from Maker Lab / live SP validation.

HOW TO ANSWER:
1. User asks about an item, creature, weapon, structure, or cheat → search indexes.by_display_name, by_stem, by_class_ref (normalize to lowercase, strip punctuation).
2. Return the matching entity record: display_name, class_ref, asset_path, blueprint_ue, giveitem, spawn_dino, enum_hooks, tags.
3. If user asks "how to spawn/give X" → return giveitem for items, spawn_dino for creatures (when present).
4. If user asks about game-state / trust / persistence → note in_session_save, session_combat, tribe_log_hit flags and enum_hooks.
5. If multiple matches → list top matches by relevance (exact display_name > stem > partial).
6. If no match → say not in MxCheatUI crosswalk; suggest GaiaCommands asset search (CF 936457).

SOURCE: MxCheatUI mod datatables (CF 1028139) cross-walked to game-state enums and session save 20260611_221210 The Center SP.
"""


def build_quick_pack(entities: dict[str, dict], indexes: dict) -> dict:
    quick_ids = set(indexes["collections"]["session_combat"])
    quick_ids.update(indexes["collections"]["tribe_log_hits"])
    for class_ref in indexes["collections"]["session_verified"]:
        ent = entities[class_ref]
        if ent["session_combat"] or ent["tribe_log_hit"] or "tek" in ent["tags"]:
            quick_ids.add(class_ref)
    quick_entities = {k: entities[k] for k in sorted(quick_ids) if k in entities}
    return {
        "schema_version": 1,
        "pack_type": "quick",
        "entity_count": len(quick_entities),
        "llm_instructions": llm_instructions(),
        "indexes": {
            "by_display_name": {
                k: v for k, v in indexes["by_display_name"].items() if any(i in quick_entities for i in v)
            },
            "collections": indexes["collections"],
        },
        "entities": quick_entities,
    }


def build_markdown(entities: dict[str, dict], indexes: dict, meta: dict) -> str:
    lines = [
        "# ASA Game Lookup Pack v1",
        "",
        "Drag this file into ChatGPT / Claude / Grok with the question about items, creatures, blueprints, or cheat commands.",
        "",
        "## LLM instructions",
        llm_instructions(),
        "",
        "## Quick collections",
        f"- Session combat ({len(indexes['collections']['session_combat'])}): "
        + ", ".join(
            entities[c]["display_name"] for c in indexes["collections"]["session_combat"] if c in entities
        ),
        f"- Tribe log hits ({len(indexes['collections']['tribe_log_hits'])})",
        f"- Session-verified in save ({len(indexes['collections']['session_verified'])})",
        "",
        "## Session combat items (verified)",
        "",
    ]
    for class_ref in indexes["collections"]["session_combat"]:
        if class_ref in entities:
            lines.append(entity_card_text(entities[class_ref]))
            lines.append("")

    lines.extend(["## Tribe log creatures/items (session)", ""])
    for class_ref in indexes["collections"]["tribe_log_hits"]:
        if class_ref in entities:
            lines.append(entity_card_text(entities[class_ref]))
            lines.append("")

    lines.extend(
        [
            "## Full entity catalog (alphabetical by display name)",
            "",
            f"Total entities: {len(entities)}. Source: {meta.get('source_note', '')}",
            "",
        ]
    )
    for class_ref in sorted(entities, key=lambda c: entities[c]["display_name"].lower()):
        lines.append(entity_card_text(entities[class_ref]))
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    if not CROSSWALK_JSONL.exists():
        raise SystemExit(f"Missing {CROSSWALK_JSONL}")

    rows = load_rows()
    entities = {row["class_ref_C"]: compact_entity(row) for row in rows}
    indexes = build_indexes(entities)

    crosswalk_meta = {}
    if CROSSWALK_JSON.exists():
        crosswalk_meta = json.loads(CROSSWALK_JSON.read_text(encoding="utf-8"))

    session_note = ""
    if SESSION_BUNDLE.exists():
        bundle = json.loads(SESSION_BUNDLE.read_text(encoding="utf-8"))
        session_note = bundle.get("session", {}).get("activity_summary", "")

    pack = {
        "schema_version": 1,
        "pack_type": "full",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "drag_and_drop_llm_lookup",
        "llm_instructions": llm_instructions(),
        "source_note": (
            "MxCheatUI spawn tables + ARK_GameStates enums + "
            "The Center SP session save 20260611_221210"
        ),
        "session_context": {
            "map": "TheCenter_WP",
            "save_sha256": crosswalk_meta.get("session_save_index", {}).get("sha256"),
            "activity_summary": session_note,
        },
        "mods": crosswalk_meta.get("mods", {}),
        "enum_families": crosswalk_meta.get("enum_families_used", {}),
        "counts": {
            "entities": len(entities),
            "items": sum(1 for e in entities.values() if e["kind"] == "item"),
            "creatures": sum(1 for e in entities.values() if e["kind"] == "creature"),
            **{k: len(v) for k, v in indexes["collections"].items()},
        },
        "query_examples": [
            {
                "user_asks": "How do I give myself a Tek Rifle?",
                "lookup": "tek rifle",
                "field": "giveitem",
            },
            {
                "user_asks": "What is the blueprint path for Grappling Hook ammo?",
                "lookup": "grappling hook",
                "field": "blueprint_ue",
            },
            {
                "user_asks": "Spawn an Oasisaur — what command?",
                "lookup": "oasisaur",
                "field": "spawn_dino",
            },
            {
                "user_asks": "What EPrimalItemType is Tek Generator?",
                "lookup": "tek generator",
                "field": "item_type",
            },
            {
                "user_asks": "Was Tek Rifle in my session save?",
                "lookup": "tek rifle",
                "field": "in_session_save",
            },
        ],
        "indexes": indexes,
        "entities": entities,
    }

    OUT_JSON.write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_JSON_MIN.write_text(
        json.dumps(pack, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    OUT_QUICK_JSON.write_text(
        json.dumps(build_quick_pack(entities, indexes), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    OUT_MD.write_text(
        build_markdown(entities, indexes, {"source_note": pack["source_note"]}),
        encoding="utf-8",
    )
    OUT_PROMPT.write_text(
        llm_instructions()
        + "\n\nAttached file: asa_game_lookup_v1.json (full) or asa_game_lookup_quick_v1.json (session-focused).\n"
        + "Use indexes.by_display_name first, then entities[class_ref].\n",
        encoding="utf-8",
    )

    print(f"Wrote {OUT_JSON} ({OUT_JSON.stat().st_size // 1024} KB)")
    print(f"Wrote {OUT_JSON_MIN} ({OUT_JSON_MIN.stat().st_size // 1024} KB)")
    print(f"Wrote {OUT_QUICK_JSON} ({OUT_QUICK_JSON.stat().st_size // 1024} KB)")
    print(f"Wrote {OUT_MD} ({OUT_MD.stat().st_size // 1024} KB)")
    print(f"Wrote {OUT_PROMPT}")


if __name__ == "__main__":
    main()