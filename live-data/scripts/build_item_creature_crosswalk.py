#!/usr/bin/env python3
"""Build MxCheatUI item/creature crosswalk for machine assessment (v1 + v2)."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"<local-data>/ARK_LiveData")
BUNDLES = ROOT / "bundles"
EXTRACT = BUNDLES / "_extract" / "MxCheatUI"
UNPACK = EXTRACT / "unpack" / "Data"
GAME_STATES = Path(r"<local-data>/ARK_GameStates")
SESSION_SAVE = ROOT / "saves" / "20260611_221210__TheCenter_WP.ark"
SESSION_BUNDLE = BUNDLES / "session_20260611_center_combat_destruction_v1.json"
CREATURE_ITEM_JSON = GAME_STATES / "asa_creature_item_player.json"

ITEM_TABLE = UNPACK / "SpawnItemDataTable_MxCheatUI.uasset"
CREATURE_TABLE = UNPACK / "SpawnCreatureDataTable_MxCheatUI.uasset"

OUT_V1_CSV = BUNDLES / "item_creature_crosswalk_v1.csv"
OUT_V1_JSON = BUNDLES / "item_creature_crosswalk_v1.json"
OUT_V2_CSV = BUNDLES / "item_creature_crosswalk_v2.csv"
OUT_V2_JSON = BUNDLES / "item_creature_crosswalk_v2.json"
OUT_V2_JSONL = BUNDLES / "item_creature_crosswalk_v2.jsonl"

MXCHEATUI_CF = "1028139"
GAIA_CF = "936457"

SESSION_COMBAT_CLASS_REFS = {
    "PrimalItemAmmo_GrapplingHook_C",
    "PrimalItem_TekRifle_C",
    "PrimalItemResource_Element_C",
    "PrimalItem_DinoSpawner_Zeppelin_C",
    "PrimalItemStructure_TekGenerator_C",
}

NOISE_MARKERS = (
    "MxCheatUI",
    "SpawnItemDataTable",
    "SpawnCreatureDataTable",
    "SpawnItemStruct",
    "SpawnCreatureStruct",
    "NewRow",
)

ITEM_PREFIXES = (
    "PrimalItemAmmo_",
    "PrimalItemArmor_",
    "PrimalItemStructure_",
    "PrimalItemResource_",
    "PrimalItemConsumable_",
    "PrimalItemSkin_",
    "PrimalItem_Weapon",
    "PrimalItem_",
)

V1_FIELDS = [
    "kind",
    "mxcheatui_asset_path",
    "blueprint_stem",
    "class_ref_C",
    "in_session_save_221210",
    "session_combat_v1",
    "e_primal_item_type_guess",
    "game_state_enum_hooks",
    "gaia_searchable",
    "notes",
]

V2_FIELDS = V1_FIELDS + [
    "display_name",
    "display_name_source",
    "display_name_confidence",
    "blueprint_path_ue",
    "cheat_giveitem_template",
    "cheat_spawn_dino_template",
    "dlc_or_pack",
    "path_category",
    "variant_tags",
    "e_cheat_actor_type_guess",
    "in_session_class_ref",
    "in_session_game_path",
    "in_session_stem",
    "session_match_method",
    "session_combat_bundle_v1",
    "tribe_log_display_name_hit",
    "also_in_opposite_table",
    "mxcheatui_table",
    "mxcheatui_mod_cf",
    "gaia_commands_mod_cf",
    "assessment_tags",
    "row_id",
]


def extract_mx_paths(data: bytes) -> list[str]:
    text = data.decode("latin-1", errors="ignore")
    parts = re.split(r"(?=/Game/)", text)
    paths: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if not part.startswith("/Game/"):
            continue
        match = re.match(r"/Game/[A-Za-z0-9_/]+", part)
        if not match:
            continue
        path = match.group(0)
        if any(marker in path for marker in NOISE_MARKERS):
            continue
        if path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def extract_creature_name_vocabulary(data: bytes) -> list[str]:
    anchor = data.find(b"Achatina\x00")
    blob = data[anchor:] if anchor >= 0 else data
    names: list[str] = []
    seen: set[str] = set()
    skip_tokens = (
        "Property",
        "Struct",
        "Script",
        "Blueprint",
        "Spawn",
        "None",
        "Data",
        "NewRow",
        "Soft",
        "Class",
        "Guid",
        "MxCheat",
        "CoreUObject",
    )
    for match in re.finditer(rb"([A-Z][A-Za-z0-9 '\-\.]{2,50})\x00", blob):
        name = match.group(1).decode("ascii").strip()
        if any(tok in name for tok in skip_tokens):
            continue
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def blueprint_stem(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def class_ref_c(path: str) -> str:
    return f"{blueprint_stem(path)}_C"


def blueprint_path_ue(path: str) -> str:
    stem = blueprint_stem(path)
    return f"{path}.{stem}"


def normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def split_camel(value: str) -> str:
    value = value.replace("_", " ")
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    return re.sub(r"\s+", " ", value).strip()


def derive_item_display_name(stem: str) -> str:
    body = stem
    for prefix in ITEM_PREFIXES:
        if body.startswith(prefix):
            body = body[len(prefix) :]
            break
    if body.endswith("Saddle") and stem.startswith("PrimalItemArmor_"):
        body = body[: -len("Saddle")] + " Saddle"
    return split_camel(body)


def folder_species(path: str) -> str:
    if "/Dinos/" in path:
        return path.split("/Dinos/")[1].split("/")[0]
    if "/Boss/" in path:
        return path.split("/Boss/")[1].split("/")[0]
    return ""


def variant_tags_for(path: str, stem: str) -> list[str]:
    tags: list[str] = []
    checks = [
        ("aberrant", "Aberrant"),
        ("corrupt", "Corrupted"),
        ("mega", "Mega"),
        ("alpha", "Alpha"),
        ("tamed", "Tamed"),
        ("_wild", "Wild"),
        ("minion", "Minion"),
        ("surface", "Surface"),
        ("_female", "Female"),
        ("_male", "Male"),
        ("saddle", "Saddle"),
        ("character_bp", "CharacterBP"),
    ]
    hay = f"{path}/{stem}".lower()
    for needle, label in checks:
        if needle in hay:
            tags.append(label)
    return tags


def creature_stem_species(stem: str) -> str:
    if stem.startswith("PrimalItemArmor_"):
        return stem.replace("PrimalItemArmor_", "").replace("Saddle", "")
    head = stem
    for suffix in (
        "_Character_BP_Corrupt",
        "_Character_BP_Aberrant",
        "_Character_BP_Male_Tamed",
        "_Character_BP_Female_Tamed",
        "_Character_BP_Male",
        "_Character_BP_Female",
        "_Character_BP",
        "_BP",
    ):
        if head.endswith(suffix):
            head = head[: -len(suffix)]
            break
    return head.split("_")[0]


def match_creature_display_name(path: str, vocabulary: list[str]) -> tuple[str, str, str]:
    stem = blueprint_stem(path)
    species = folder_species(path)
    stem_species = creature_stem_species(stem)
    variants = variant_tags_for(path, stem)

    if stem.startswith("PrimalItemArmor_"):
        saddle = stem.replace("PrimalItemArmor_", "").replace("Saddle", "")
        for name in vocabulary:
            if normalize_token(saddle) in normalize_token(name):
                return name.strip(), "mxcheatui_dino_name", "high"

    best_name = ""
    best_score = 0
    for name in vocabulary:
        score = 0
        nn = normalize_token(name)
        ns = normalize_token(stem_species)
        if ns and ns == nn:
            score += 120
        elif ns and ns in nn:
            score += 80
        if species and normalize_token(species) == nn:
            score += 40
        elif (
            species
            and normalize_token(species) in nn
            and ns not in nn
            and normalize_token(species) != ns
        ):
            score += 15
        for tag in variants:
            if tag.lower() in name.lower():
                score += 20
        if score > best_score:
            best_score = score
            best_name = name.strip()

    if (
        stem_species
        and best_name
        and normalize_token(stem_species) not in normalize_token(best_name)
        and best_score < 80
    ):
        best_name = ""
        best_score = 0

    if best_score >= 70:
        return best_name, "mxcheatui_dino_name", "high"
    if best_score >= 45:
        return best_name, "mxcheatui_dino_name", "medium"
    if best_score >= 25:
        return best_name, "mxcheatui_dino_name", "low"

    derived = stem_species or species or stem.split("_")[0]
    derived = split_camel(derived)
    for tag in variants:
        if tag in {"Aberrant", "Corrupted", "Mega", "Alpha", "Tamed", "Wild"}:
            if tag.lower() not in derived.lower():
                derived = f"{tag} {derived}"
    return derived, "derived_stem", "low"


def display_name_for(path: str, kind: str, creature_vocab: list[str]) -> tuple[str, str, str]:
    stem = blueprint_stem(path)
    if kind == "creature":
        return match_creature_display_name(path, creature_vocab)
    return derive_item_display_name(stem), "derived_stem", "medium"


def guess_e_primal_item_type(path: str, kind: str) -> str:
    stem = blueprint_stem(path)
    lower = path.lower()
    if kind == "creature":
        if "saddle" in stem.lower() or stem.startswith("PrimalItemArmor_"):
            return "Equipment"
        return ""
    if stem.startswith("PrimalItemAmmo_") or "/ammo/" in lower:
        return "Ammo"
    if stem.startswith("PrimalItemStructure_") or "/structures/" in lower:
        return "Structure"
    if stem.startswith("PrimalItemArmor_") or "/armor/" in lower:
        return "Equipment"
    if stem.startswith("PrimalItemResource_") or "/resources/" in lower:
        return "Resource"
    if "artifact" in lower or stem.startswith("PrimalItem_Artifact"):
        return "Artifact"
    if "skin" in lower or stem.startswith("PrimalItemSkin_"):
        return "Skin"
    if (
        stem.startswith("PrimalItem_Weapon")
        or "/weapons/" in lower
        or stem.startswith("PrimalItem_Tek")
        or "rifle" in lower
        or "weapon" in lower
    ):
        return "Weapon"
    if "attachment" in lower:
        return "WeaponAttachment"
    if "consumable" in lower or stem.startswith("PrimalItemConsumable_"):
        return "MiscConsumable"
    if stem.startswith("PrimalItem_"):
        return "MiscConsumable"
    return ""


def guess_e_cheat_actor_type(path: str, kind: str) -> str:
    if kind != "creature":
        return ""
    stem = blueprint_stem(path)
    if stem.startswith("PrimalItemArmor_"):
        return ""
    if "Tamed" in stem or "Tame" in stem:
        return "Tame"
    if any(x in stem for x in ("Wild", "Minion", "Surface", "Chupa")):
        return "Wild"
    if "Character_BP" in stem or stem.endswith("_BP"):
        return "Dino"
    return ""


def guess_game_state_hooks(path: str, kind: str, item_type: str, actor_type: str) -> str:
    hooks: list[str] = []
    stem = blueprint_stem(path)
    if kind == "creature":
        if actor_type:
            hooks.append(f"ECheatActorType:{actor_type}")
        elif "Character_BP" in stem or stem.endswith("_BP"):
            hooks.append("ECheatActorType:Dino")
        if stem.startswith("PrimalItemArmor_"):
            hooks.append("EPrimalItemType:Equipment")
        hooks.append("EPrimalMilestoneType:Kill")
        hooks.append("EPrimalMilestoneType:Tame")
    else:
        if item_type:
            hooks.append(f"EPrimalItemType:{item_type}")
        hooks.append("EPrimalMilestoneType:Craft")
        if item_type in {"Weapon", "Ammo"}:
            hooks.append("EPrimalMilestoneType:Kill")
    return "; ".join(hooks)


def dlc_or_pack(path: str) -> str:
    parts = path.split("/")
    return parts[2] if len(parts) > 2 and parts[1] == "Game" else ""


def path_category(path: str) -> str:
    parts = [p for p in path.split("/") if p and p not in {"Game"}]
    if len(parts) <= 1:
        return ""
    return "/".join(parts[1:-1])


def cheat_giveitem_template(path: str) -> str:
    bp = blueprint_path_ue(path)
    return f'cheat giveitem "Blueprint\'{bp}\'" 1 0 0'


def cheat_spawn_dino_template(path: str, kind: str) -> str:
    if kind != "creature":
        return ""
    stem = blueprint_stem(path)
    if stem.startswith("PrimalItemArmor_") or "Character_BP" not in stem:
        return ""
    bp = blueprint_path_ue(path)
    return f'cheat SpawnExactDino "Blueprint\'{bp}\'" 1 0 0 0'


def load_enum_families() -> dict:
    data = json.loads(CREATURE_ITEM_JSON.read_text(encoding="utf-8"))
    families = {
        "EPrimalItemType": [],
        "ECheatActorType": [],
        "EPrimalMilestoneType": [],
    }
    for cat in ("item", "creature", "player"):
        for entry in data.get("by_category", {}).get(cat, []):
            enum_type = entry.get("enum_type")
            if enum_type in families and entry.get("values"):
                families[enum_type] = entry.get("values", [])
    return families


def load_tribe_log_display_names() -> set[str]:
    if not SESSION_BUNDLE.exists():
        return set()
    bundle = json.loads(SESSION_BUNDLE.read_text(encoding="utf-8"))
    events = bundle.get("tribe_log_delta_open_to_exit", {}).get("session_new_tribe_events_unique", [])
    names: set[str] = set()
    patterns = [
        r"\(([^)]+)\)",
        r"Tamed an? ([^(]+?) -",
        r"Tamed a ([^(]+?) -",
        r"uploaded a ([^:]+):",
        r"downloaded a dino: ([^-]+)",
    ]
    for event in events:
        for pattern in patterns:
            for match in re.finditer(pattern, event):
                candidate = match.group(1).strip()
                if candidate and not candidate.startswith("<"):
                    names.add(candidate)
    return names


def build_session_index(save_path: Path) -> dict:
    data = save_path.read_bytes()
    class_refs = {r.decode("ascii", errors="ignore") for r in re.findall(rb"[A-Za-z0-9_]+_C", data)}
    game_paths = {p.decode("ascii", errors="ignore") for p in re.findall(rb"/Game/[A-Za-z0-9_/]+", data)}
    stems = {ref[:-2] for ref in class_refs if ref.endswith("_C")}
    return {
        "class_refs": class_refs,
        "game_paths": game_paths,
        "stems": stems,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def session_match(path: str, class_ref: str, session: dict) -> tuple[bool, str, dict]:
    stem = blueprint_stem(path)
    flags = {
        "in_session_class_ref": class_ref in session["class_refs"],
        "in_session_game_path": path in session["game_paths"],
        "in_session_stem": stem in session["stems"],
    }
    methods = [k.replace("in_session_", "") for k, v in flags.items() if v]
    matched = bool(methods)
    return matched, "+".join(methods) if methods else "", flags


def assessment_tags(
    path: str,
    kind: str,
    item_type: str,
    actor_type: str,
    session_flags: dict,
    session_combat: bool,
    tribe_hit: bool,
    variants: list[str],
) -> str:
    tags: list[str] = [kind]
    stem = blueprint_stem(path)
    pack = dlc_or_pack(path)
    if pack:
        tags.append(f"pack:{pack}")
    if item_type:
        tags.append(f"item_type:{item_type}")
    if actor_type:
        tags.append(f"actor_type:{actor_type}")
    if "tek" in path.lower() or "tek" in stem.lower():
        tags.append("tek")
    if session_flags.get("in_session_class_ref"):
        tags.append("session_class_ref")
    if session_flags.get("in_session_game_path"):
        tags.append("session_game_path")
    if session_flags.get("in_session_stem"):
        tags.append("session_stem")
    if session_combat:
        tags.append("session_combat_v1")
    if tribe_hit:
        tags.append("tribe_log_name_hit")
    for variant in variants:
        tags.append(f"variant:{variant}")
    if stem.startswith("PrimalItemArmor_"):
        tags.append("saddle_item")
    if "Character_BP" in stem:
        tags.append("character_bp")
    return ";".join(tags)


def build_rows(session: dict, tribe_names: set[str], creature_vocab: list[str]) -> list[dict]:
    item_paths = extract_mx_paths(ITEM_TABLE.read_bytes())
    creature_paths = extract_mx_paths(CREATURE_TABLE.read_bytes())
    item_stems = {blueprint_stem(p) for p in item_paths}
    creature_stems = {blueprint_stem(p) for p in creature_paths}
    overlap = item_stems & creature_stems

    rows: list[dict] = []
    row_id = 0
    for table_kind, paths in (("SpawnItemDataTable", item_paths), ("SpawnCreatureDataTable", creature_paths)):
        for path in paths:
            row_id += 1
            kind = "item" if table_kind == "SpawnItemDataTable" else "creature"
            stem = blueprint_stem(path)
            cref = class_ref_c(path)
            item_type = guess_e_primal_item_type(path, kind)
            actor_type = guess_e_cheat_actor_type(path, kind)
            display_name, display_source, display_conf = display_name_for(path, kind, creature_vocab)
            variants = variant_tags_for(path, stem)
            matched, match_method, session_flags = session_match(path, cref, session)
            session_combat = cref in SESSION_COMBAT_CLASS_REFS
            tribe_hit = display_name in tribe_names or any(
                normalize_token(display_name) == normalize_token(t) for t in tribe_names
            )

            row = {
                "row_id": f"mx_{row_id:05d}",
                "kind": kind,
                "mxcheatui_asset_path": path,
                "blueprint_stem": stem,
                "class_ref_C": cref,
                "display_name": display_name,
                "display_name_source": display_source,
                "display_name_confidence": display_conf,
                "blueprint_path_ue": blueprint_path_ue(path),
                "cheat_giveitem_template": cheat_giveitem_template(path),
                "cheat_spawn_dino_template": cheat_spawn_dino_template(path, kind),
                "dlc_or_pack": dlc_or_pack(path),
                "path_category": path_category(path),
                "variant_tags": ";".join(variants),
                "in_session_save_221210": "Y" if matched else "N",
                "in_session_class_ref": "Y" if session_flags["in_session_class_ref"] else "N",
                "in_session_game_path": "Y" if session_flags["in_session_game_path"] else "N",
                "in_session_stem": "Y" if session_flags["in_session_stem"] else "N",
                "session_match_method": match_method,
                "session_combat_v1": "Y" if session_combat else "N",
                "session_combat_bundle_v1": "Y" if session_combat else "N",
                "tribe_log_display_name_hit": "Y" if tribe_hit else "N",
                "e_primal_item_type_guess": item_type,
                "e_cheat_actor_type_guess": actor_type,
                "game_state_enum_hooks": guess_game_state_hooks(path, kind, item_type, actor_type),
                "gaia_searchable": "Y" if path.startswith("/Game/") else "N",
                "also_in_opposite_table": "Y" if stem in overlap else "N",
                "mxcheatui_table": table_kind,
                "mxcheatui_mod_cf": MXCHEATUI_CF,
                "gaia_commands_mod_cf": GAIA_CF,
                "assessment_tags": assessment_tags(
                    path,
                    kind,
                    item_type,
                    actor_type,
                    session_flags,
                    session_combat,
                    tribe_hit,
                    variants,
                ),
                "notes": "",
            }
            rows.append(row)
    return rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_indexes(rows: list[dict]) -> dict:
    by_class_ref: dict[str, list[str]] = defaultdict(list)
    by_stem: dict[str, list[str]] = defaultdict(list)
    by_display_name: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        rid = row["row_id"]
        by_class_ref[row["class_ref_C"]].append(rid)
        by_stem[row["blueprint_stem"]].append(rid)
        by_display_name[row["display_name"]].append(rid)
    return {
        "by_class_ref": dict(by_class_ref),
        "by_stem": dict(by_stem),
        "by_display_name": dict(by_display_name),
        "session_verified_row_ids": [r["row_id"] for r in rows if r["in_session_save_221210"] == "Y"],
        "session_combat_row_ids": [r["row_id"] for r in rows if r["session_combat_v1"] == "Y"],
        "tribe_log_hit_row_ids": [r["row_id"] for r in rows if r["tribe_log_display_name_hit"] == "Y"],
        "high_confidence_creature_names": [
            r["row_id"] for r in rows if r["kind"] == "creature" and r["display_name_confidence"] == "high"
        ],
    }


def main() -> None:
    if not ITEM_TABLE.exists() or not CREATURE_TABLE.exists():
        raise SystemExit(f"Missing extracted tables under {UNPACK}")
    if not SESSION_SAVE.exists():
        raise SystemExit(f"Missing session save: {SESSION_SAVE}")

    creature_vocab = extract_creature_name_vocabulary(CREATURE_TABLE.read_bytes())
    session = build_session_index(SESSION_SAVE)
    tribe_names = load_tribe_log_display_names()
    enum_families = load_enum_families()
    rows = build_rows(session, tribe_names, creature_vocab)

    write_csv(OUT_V2_CSV, V2_FIELDS, rows)
    write_csv(OUT_V1_CSV, V1_FIELDS, rows)

    indexes = build_indexes(rows)
    in_session = [r for r in rows if r["in_session_save_221210"] == "Y"]
    combat = [r for r in rows if r["session_combat_v1"] == "Y"]
    tribe_hits = [r for r in rows if r["tribe_log_display_name_hit"] == "Y"]

    manifest_v2 = {
        "schema_version": 2,
        "purpose": "machine_assessment_review",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "mxcheatui_item_table": str(ITEM_TABLE),
            "mxcheatui_creature_table": str(CREATURE_TABLE),
            "mxcheatui_creature_name_vocabulary_count": len(creature_vocab),
            "game_states_catalog": str(CREATURE_ITEM_JSON),
            "session_save": str(SESSION_SAVE),
            "session_bundle": str(SESSION_BUNDLE),
        },
        "mods": {
            "mxcheatui": {"curseforge_id": MXCHEATUI_CF, "role": "spawn_item_creature_datatables"},
            "gaia_commands": {"curseforge_id": GAIA_CF, "role": "asset_search_admin_bridge"},
        },
        "session_save_index": {
            "sha256": session["sha256"],
            "size_bytes": session["size_bytes"],
            "class_ref_count": len(session["class_refs"]),
            "game_path_count": len(session["game_paths"]),
        },
        "counts": {
            "total_rows": len(rows),
            "items": sum(1 for r in rows if r["kind"] == "item"),
            "creatures": sum(1 for r in rows if r["kind"] == "creature"),
            "in_session_save_221210": len(in_session),
            "session_combat_v1": len(combat),
            "tribe_log_display_name_hits": len(tribe_hits),
            "creature_display_name_high_confidence": sum(
                1 for r in rows if r["kind"] == "creature" and r["display_name_confidence"] == "high"
            ),
        },
        "enum_families_used": enum_families,
        "creature_name_vocabulary": creature_vocab,
        "tribe_log_display_names": sorted(tribe_names),
        "session_combat_class_refs": sorted(SESSION_COMBAT_CLASS_REFS),
        "session_combat_rows": combat,
        "tribe_log_hit_rows": tribe_hits,
        "indexes": indexes,
        "parser": {
            "path_method": "latin-1 split on (?=/Game/), trim to [A-Za-z0-9_/]",
            "creature_name_method": "null-terminated ASCII scan from Achatina anchor + vocabulary match",
            "item_display_name_method": "blueprint_stem token split (derived_stem)",
            "noise_filters": list(NOISE_MARKERS),
        },
        "outputs": {
            "csv_v2": str(OUT_V2_CSV),
            "jsonl_v2": str(OUT_V2_JSONL),
            "csv_v1_compat": str(OUT_V1_CSV),
        },
    }

    OUT_V2_JSON.write_text(json.dumps(manifest_v2, indent=2), encoding="utf-8")
    with OUT_V2_JSONL.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    manifest_v1 = {
        "schema_version": 1,
        "generated_at_utc": manifest_v2["generated_at_utc"],
        "sources": manifest_v2["sources"],
        "session_save_index": manifest_v2["session_save_index"],
        "counts": manifest_v2["counts"],
        "enum_families_used": enum_families,
        "session_combat_class_refs": manifest_v2["session_combat_class_refs"],
        "session_combat_rows": combat,
        "parser": manifest_v2["parser"],
        "output_csv": str(OUT_V1_CSV),
        "v2_detail_manifest": str(OUT_V2_JSON),
    }
    OUT_V1_JSON.write_text(json.dumps(manifest_v1, indent=2), encoding="utf-8")

    print(f"Wrote {len(rows)} rows -> {OUT_V2_CSV}")
    print(f"Wrote JSONL -> {OUT_V2_JSONL}")
    print(f"Wrote manifest -> {OUT_V2_JSON}")
    print(
        "in_session:",
        len(in_session),
        "| combat:",
        len(combat),
        "| tribe hits:",
        len(tribe_hits),
        "| creature vocab:",
        len(creature_vocab),
    )


if __name__ == "__main__":
    main()