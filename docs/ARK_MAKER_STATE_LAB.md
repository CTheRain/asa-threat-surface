# ARK Maker State Lab

Operating concept for **ARK Maker Lab** — a DLC-only, singleplayer bug-forensics chamber. Official PvP is **observation input**; ARK Maker is the **controlled reproduction environment**.

This document is the plan spine. The public repo carries the pre-lab evidence map; capsules carry the future regression chamber.

---

## Two-layer model

```text
┌─────────────────────────────────────────────────────────────────┐
│  Official PvP / community reports  →  observation only          │
│  (clips, tickets, session intel — never the reproduction site)  │
└────────────────────────────┬────────────────────────────────────┘
                             │ evidence packet
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  asa-threat-surface (this repo)  →  current evidence map        │
│  class refs · enum surfaces · save evidence · tribe log         │
│  lookup packs · threat docs · state simulator                   │
└────────────────────────────┬────────────────────────────────────┘
                             │ capsule candidate
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  ARK Maker State Lab (future DLC)  →  reproduction chamber      │
│  Lua trigger/logger · frozen state trays · patch regression     │
└────────────────────────────┬────────────────────────────────────┘
                             │ verdict packet
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  toolkit swarm  →  refinery/router                              │
│  chat / LLM only sees clean verdict packets — not raw sludge    │
└─────────────────────────────────────────────────────────────────┘
```

---

## What this repo already does (pre-lab)

| Stage | Repo artifact | Role |
|-------|---------------|------|
| Static surfaces | `game-states/asa_game_states.json`, `asa_creature_item_player.json` | Enum families from `ArkAscended.exe` |
| Live disk evidence | `live-data/scripts/asa_game_state_monitor.py` | SP save/profile/log mirroring (disk-only) |
| Session proof | `live-data/bundles/session_*.json` | Anchored hashes, class refs, combat/craft deltas |
| Crosswalk | `live-data/bundles/item_creature_crosswalk_v*.json` | MxCheatUI ↔ save join |
| LLM lookup | `live-data/bundles/asa_game_lookup_*.json` | Drag-and-drop query packs |
| Threat framing | `threat-surface/docs/asa_threat_surface_v1.md` | Client-trust method language |
| Browser sim | `index.html` + `game-states/asa_game_states_sim.json` | Enum → persistence walkthrough |

Pipeline today:

```text
observed ASA behavior
  → class refs / enum surfaces / save evidence / tribe log evidence
  → lookup packs + threat docs + simulator scenarios
```

---

## What ARK Maker Lab adds (post-DLC)

```text
observed ASA behavior
  → evidence packet (from this repo)
  → controlled ARK Maker capsule
  → Lua trigger / logger
  → patch regression result
  → dev report / video packet / mechanic registry update
```

ARK Maker is **not** a public product page or raid tool. It is a **DLC-only SP lab** where each bug becomes a small fossil tray — reproducible, versioned, and retestable after patches.

---

## State capsules (the keystone)

A capsule is a **frozen reproduction unit**, not a clip or a save dump in git.

```text
clean control
  → suspect setup
  → trigger-ready state
  → bug activation
  → first corrupted state
  → persisted corrupted state
  → post-patch verification state
```

Each tray slot maps to:

- **Disk anchors** — which `.ark` / `.arkbak` / tribe-log mirror proves the state (local on `<local-data>/`, never committed raw)
- **Enum hooks** — which `EPrimalItemType`, `ECheatActorType`, `EActorListsBP`, etc. should fire
- **Lua logger expectations** — what the ARK Maker script must emit before/after trigger
- **Verdict** — pass / fail / regression / unknown after patch

Formal schema: [`CAPSULE_SCHEMA.md`](CAPSULE_SCHEMA.md)

First scaffold: [`../capsules/capsule_000_survival_test/`](../capsules/capsule_000_survival_test/)

---

## Evidence bridge

Every capsule **must** cite threat-surface evidence — not invent mechanics from chat.

```text
threat-surface evidence  →  ARK Maker capsule candidate
```

| Evidence type | Typical source in repo | Capsule field |
|---------------|------------------------|---------------|
| Class ref in save | session bundle `entities[]` | `actor.class_ref` |
| Enum hook | lookup pack `enum_hooks` | `state_tray.*.expected_hooks` |
| Sim scenario | `asa_game_states_sim.json` | `evidence_bridge.sim_scenario` |
| Threat claim | `threat-surface/docs/` | `evidence_bridge.threat_surface_refs` |
| Disk layer | session `persistence_layers` | `state_tray.*.persistence_layer` |

Promotion path:

1. **Observe** — PvP report or SP session (monitor captures disk)
2. **Index** — crosswalk + lookup pack entry exists
3. **Simulate** — HTML State Simulator scenario covers the hook chain
4. **Capsule** — `capsules/capsule_NNN_*` manifest authored
5. **Run** — ARK Maker DLC loads capsule, Lua fires, logger writes `runs/`
6. **Report** — `reports/` verdict packet → toolkit swarm → dev-facing language

---

## Related docs

| Doc | Purpose |
|-----|---------|
| [`CAPSULE_SCHEMA.md`](CAPSULE_SCHEMA.md) | JSON manifest fields, state tray slots, run artifacts |
| [`PATCH_DAY_WORKFLOW.md`](PATCH_DAY_WORKFLOW.md) | Game update → re-run capsules → regression matrix |
| [`SAFETY_BOUNDARY.md`](SAFETY_BOUNDARY.md) | Red lines: no intel automation, no raw paks in git |
| [`../threat-surface/docs/asa_threat_surface_v1.md`](../threat-surface/docs/asa_threat_surface_v1.md) | Client-trust evidence and Wildcard-facing framing |
| [`../threat-surface/docs/HOW_IT_WORKS.md`](../threat-surface/docs/HOW_IT_WORKS.md) | How static scans and live monitor work |

---

## ARK Maker Lab principles

1. **DLC-only, singleplayer** — no Official server access required for reproduction.
2. **Disk-first doctrine** — same as the live monitor: persistence layers are authoritative evidence, not live `AShooterGameState` reads.
3. **One bug, one tray** — capsules stay small; compound raids become multiple capsules.
4. **Method-proof language** — reports name systems (`EPrimalItemType`, movement correction CVARs), not player names or tribe routes.
5. **Bug museum** — surviving capsules become the mechanic registry; dead bugs stay as post-patch verification records.

---

## Status

| Component | Status |
|-----------|--------|
| Evidence map (this repo) | **Live** — public on GitHub Pages |
| State simulator | **Live** — browser walkthrough |
| Capsule schema + scaffold | **Live** — `capsule_000_survival_test` |
| ARK Maker DLC runtime | **Future** — Lua logger + capsule loader TBD |
| Toolkit swarm router | **Future** — verdict packet refinery TBD |