-- ARK Maker State Lab — survival logger v1 (scaffold)
-- capsule_000_survival_test
-- Emits JSON lines for: class_ref, enum_hook, save_size_bytes, timestamp_utc
-- Replace stub bodies when ARK Maker DLC runtime API is available.

local CAPSULE_ID = "capsule_000_survival_test"
local TARGET_CLASS = "PrimalItem_TekRifle_C"
local TARGET_HOOK = "EPrimalItemType:Weapon"

local function emit(event, payload)
  -- DLC runtime: write to runs/run_*/logger_output.jsonl
  print(string.format('{"capsule":"%s","event":"%s","payload":%s}',
    CAPSULE_ID, event, payload or "{}"))
end

function OnCapsuleLoad()
  emit("OnCapsuleLoad", '{"status":"loaded"}')
end

function OnItemGranted()
  emit("OnItemGranted", string.format('{"class_ref":"%s","enum_hook":"%s"}',
    TARGET_CLASS, TARGET_HOOK))
end

function OnSaveBefore()
  emit("OnSaveBefore", "{}")
end

function OnSaveAfter()
  emit("OnSaveAfter", '{"persistence_layer":"save_ark"}')
end

function OnReloadComplete()
  emit("OnReloadComplete", string.format('{"class_ref":"%s","pass":null}',
    TARGET_CLASS))
end