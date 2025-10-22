import os, json, time, uuid, pathlib, random, hashlib, requests
try:
    import tomllib
except Exception:
    import tomli as tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CFG = ROOT / "config" / "default.toml"
LOG = ROOT / "logs" / "event_log.jsonl"
SNAPDIR = ROOT / "snapshots"
TESTDIR = ROOT / "test_data"

cfg = tomllib.loads(CFG.read_text(encoding="utf-8"))
llm = cfg.get("llm", {})
endpoint = llm.get("endpoint", "http://127.0.0.1:11434/api/generate")
model = llm.get("model", "llama3")
stream = bool(llm.get("stream", False))
timeout = int(llm.get("timeout", 60))

TESTDIR.mkdir(parents=True, exist_ok=True)
SNAPDIR.mkdir(parents=True, exist_ok=True)
LOG.parent.mkdir(parents=True, exist_ok=True)

def sha256(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def write_event(ev: dict):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")

def roundtrip_once(i: int):
    # 1) 랜덤 파일 Δ 생성
    fname = TESTDIR / f"rt_{i:04d}.txt"
    content = f"run={i}, ts={time.time()}, rand={random.random()}"
    fname.write_text(content, encoding="utf-8")
    h = sha256(fname)
    delta = {
        "ts": time.time(),
        "event": "delta",
        "path": str(fname.relative_to(ROOT)),
        "op": "write",
        "hash": h,
        "producer_actual": "llm_system_loop",
        "correlation_id": f"corr_{uuid.uuid4().hex[:12]}",
    }
    write_event(delta)

    # 2) LLM 호출 (Δ 요약 요청)
    prompt = (
        "You are MemoryOS verifier.\n"
        f"Delta event:\n- path: {delta['path']}\n- op: {delta['op']}\n- hash: {delta['hash']}\n"
        "Reply with a single short sentence acknowledging the delta and mentioning: MemoryOS, drift, snapshot."
    )
    payload = {"model": model, "prompt": prompt, "stream": stream}
    t0 = time.time()
    r = requests.post(endpoint, json=payload, timeout=timeout)
    latency_ms = int((time.time() - t0) * 1000)
    r.raise_for_status()
    data = r.json()
    resp = (data.get("response") or "").strip()

    llm_ev = {
        "ts": time.time(),
        "event": "llm_call",
        "provider": "ollama",
        "model": model,
        "latency_ms": latency_ms,
        "ok": True,
        "stream": stream,
        "request_preview": prompt[:200],
        "response_preview": resp[:200],
        "correlation_id": delta["correlation_id"],
    }
    write_event(llm_ev)

    # 3) 스냅샷 기록 (Δ + LLM 묶어서)
    snap = {
        "schema_version": "1.0.0",
        "snapshot_id": f"snap_{int(time.time())}_{i}",
        "state_summary": {"note": "llm_system_loop"},
        "delta": delta,
        "llm": {
            "provider": "ollama",
            "model": model,
            "latency_ms": latency_ms,
            "stream": stream,
            "response_preview": resp[:400],
        },
        "provenance": {"source": "scripts/llm_system_loop.py"},
    }
    out = SNAPDIR / f"llm_system_loop_{int(time.time())}_{i:04d}.json"
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] #{i} Δ→LLM {latency_ms} ms | {delta['path']}")

if __name__ == "__main__":
    runs = int(os.environ.get("LOOP_RUNS", "10"))
    delay = float(os.environ.get("LOOP_DELAY", "1.0"))
    for i in range(1, runs+1):
        roundtrip_once(i)
        time.sleep(delay)
