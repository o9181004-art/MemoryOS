import os, json, time, uuid, pathlib, requests
try:
    import tomllib
except Exception:
    import tomli as tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CFG = ROOT / "config" / "default.toml"
LOG = ROOT / "logs" / "event_log.jsonl"
SNAPDIR = ROOT / "snapshots"

cfg = tomllib.loads(CFG.read_text(encoding="utf-8"))
llm = cfg.get("llm", {})
endpoint = llm.get("endpoint", "http://127.0.0.1:11434/api/generate")
model = llm.get("model", "llama3")
stream = bool(llm.get("stream", False))
timeout = int(llm.get("timeout", 60))

messages = [
    {"role":"system","content":"You are a helpful assistant."},
    {"role":"user","content":"Say one short sentence that includes the words: MemoryOS, drift, snapshot."}
]
prompt = "\n".join([m["content"] for m in messages])

payload = {"model": model, "prompt": prompt, "stream": stream}
t0 = time.time()
r = requests.post(endpoint, json=payload, timeout=timeout)
lat_ms = int((time.time()-t0)*1000)
r.raise_for_status()
data = r.json()
resp = (data.get("response") or "").strip()

# 1) event_log.jsonl에 llm_call 기록
event = {
    "ts": time.time(),
    "event": "llm_call",
    "provider": "ollama",
    "model": model,
    "endpoint": endpoint,
    "latency_ms": lat_ms,
    "stream": stream,
    "ok": True,
    "request_preview": prompt[:200],
    "response_preview": resp[:200],
    "correlation_id": f"run_{uuid.uuid4().hex[:12]}",
}
LOG.parent.mkdir(parents=True, exist_ok=True)
with LOG.open("a", encoding="utf-8") as f:
    f.write(json.dumps(event, ensure_ascii=False) + "\n")

# 2) 간단 스냅샷 파일 생성 (llm 섹션 포함)
snap = {
    "schema_version": "1.0.0",
    "snapshot_id": f"snap_{int(time.time())}",
    "state_summary": {"note":"LLM roundtrip smoke"},
    "llm": {
        "provider":"ollama",
        "model":model,
        "latency_ms":lat_ms,
        "stream":stream,
        "response_preview": resp[:400],
    },
    "provenance": {"source":"scripts/llm_roundtrip.py"},
}
SNAPDIR.mkdir(parents=True, exist_ok=True)
out = SNAPDIR / f"llm_roundtrip_{int(time.time())}.json"
out.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"[OK] LLM roundtrip complete in {lat_ms} ms")
print("Response:", resp[:200].replace("\n"," "))
print("Event log:", str(LOG))
print("Snapshot :", str(out))
