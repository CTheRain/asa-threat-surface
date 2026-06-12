# runs/

Per-execution artifacts from ARK Maker State Lab.

## Layout

```text
runs/
  run_YYYYMMDD_HHMMSS/
    run_manifest.json
    logger_output.jsonl
    screenshots/
      01_clean_control.png
      02_suspect_setup.png
      ...
```

## Git policy

- **Commit:** `run_manifest.json`, scrubbed summaries
- **Do not commit:** `.ark`, `.arkbak`, raw screenshots with player/tribe HUD text (redact first)

Populate this folder on first manual or DLC-automated run.