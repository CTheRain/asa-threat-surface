# Safety Boundary

Red lines for **ARK Maker State Lab** and the `asa-threat-surface` evidence map. These apply to repo contents, capsule runs, toolkit swarm output, and Wildcard-facing reports.

---

## Scope

| In scope | Out of scope |
|----------|--------------|
| DLC-only singleplayer reproduction | Official PvP raid planning |
| Client-trust / persistence forensics | Live session tracking automation |
| Method-proof dev reports | Cheat distribution or brand promotion |
| Disk-observable evidence | Live memory scraping of `AShooterGameState` |

---

## Git / GitHub — never commit

Enforced by `.gitignore` and review habit:

| Artifact | Why |
|----------|-----|
| `*.pak`, `*.ucas`, `*.utoc` | Game/mod archives; size + license |
| `*.ark`, `*.arkbak`, `*.arkprofile` | Saves contain world state; may embed names |
| Full IoStore mirror | ~258 GB; stays on `<local-data>/ARK_ThreatSurface/` |
| Raw mod unpack trees | Rebuild from small extracts in `live-data/sources/` |
| API tokens, `.env` | Secrets |

**Allowed in git:** JSON indexes, CSVs, small MxCheatUI table extracts, capsule manifests, verdict packets, scrubbed docs.

Scrub before publish:

```powershell
python scripts/scrub_personal_paths.py
```

Replaces `C:\Users\<username>` and `S:\ARK_*` with neutral placeholders.

---

## Capsule runs — local only

| Rule | Detail |
|------|--------|
| Saves stay local | `template.local_save_anchor` points to `<local-data>/`, never git |
| Screenshots | Redact HUD player/tribe names before any public report |
| Logger output | May commit **summarized** `verdict.json`; raw `logger_output.jsonl` optional and scrubbed |
| One actor default | Keep trays small; split compound scenarios into multiple capsules |

---

## Observation vs reproduction

```text
Official PvP  →  INPUT ONLY (clips, reports, public data)
ARK Maker SP  →  REPRODUCTION ONLY (capsules, Lua, disk proof)
```

Do **not**:

- Route capsules from live Official intel to target specific players
- Publish tribe names, server IPs, or join coordinates from observation
- Claim inner workings of third-party cheat clients without captured binaries

Do:

- Name vanilla systems (`UShooterCheatManager`, `EPrimalItemType`, movement CVARs)
- Cite repo evidence files in reports
- Use ARK Maker to freeze and replay mechanics

---

## Toolkit swarm / LLM packets

Chat interfaces receive **verdict packets** only:

```json
{
  "verdict": "pass | fail | regressed",
  "wildcard_framing": "method-proof sentence",
  "evidence_citations": ["capsule_id", "enum_hook"]
}
```

Do **not** feed:

- Entire `pak_meat_strings` or 2.5k entity dumps per message
- Unscrubbed session bundles with live paths
- Pegasus command lists as operational instructions

Use `asa_game_lookup_quick_v1.json` or `verdict.json` — not raw threat-surface mirror.

---

## Intel automation — explicit red lines

From `threat-surface/docs/asa_threat_surface_v1.md`:

- Do **not** build Pegasus-like tracking automation
- Do **not** publish raid routing from live intel
- Do **not** claim GPT/Aurora/King internals without client binaries

ARK Maker Lab **replaces** raid manuals with **fossil trays** — reproducible mechanics, not player hunting.

---

## Wildcard-facing language

**Use:**

> "Client-trusted movement and projectile hit reporting appear authoritative to the server."
> "Disk persistence accepts PrimalItem class refs without revalidation after reload."

**Avoid:**

> "Here's how to raid server X using Pegasus."
> "Player Y's tribe is online now."

Align with [`asa_threat_surface_v1.md`](../threat-surface/docs/asa_threat_surface_v1.md) §4.

---

## Bridge mods (research only)

| Mod | CurseForge | Allowed use |
|-----|------------|-------------|
| MxCheatUI | 1028139 | Crosswalk rebuild; spawn table extracts in repo |
| GaiaCommands | 936457 | Asset search bridge reference |

Mod extracts in git are **minimal rebuild inputs** — not a cheat distribution channel.

---

## Incident response

If personal paths or saves leak into a commit:

1. `git revert` or history rewrite before push
2. Re-run `scrub_personal_paths.py`
3. Rotate any exposed tokens
4. Do not push binary saves to GitHub — GitHub does not make this safe

---

## Summary

```text
observe in PvP  →  index in repo  →  reproduce in ARK Maker  →  verdict out
                      ↑ never raw paks/saves in git ↑
```

When in doubt: **disk proof local, verdict public, trays small, names scrubbed.**