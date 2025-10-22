import json, time, pathlib, requests
try:
    import tomllib
except Exception:
    import tomli as tomllib

cfg = tomllib.loads(pathlib.Path("config/default.toml").read_text(encoding="utf-8"))
llm = cfg.get("llm", {})
endpoint = llm.get("endpoint", "http://127.0.0.1:11434/api/generate")
model = llm.get("model", "llama3")
stream = bool(llm.get("stream", False))
timeout = int(llm.get("timeout", 60))

payload = {"model": model, "prompt": "MemoryOS connectivity test", "stream": stream}
t0 = time.time()

def parse_stream(resp):
    """Ollama stream=true: line-delimited JSON (가끔 'data: {...}') 처리"""
    resp.raise_for_status()
    parts = []
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            if line.startswith("data:"):
                try:
                    obj = json.loads(line[5:].strip())
                except Exception:
                    continue
            else:
                continue
        if obj.get("response"):
            parts.append(obj["response"])
        if obj.get("done"):
            break
    return "".join(parts).strip()

if not stream:
    r = requests.post(endpoint, json=payload, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    text = (data.get("response") or "").strip()
else:
    r = requests.post(endpoint, json=payload, timeout=timeout, stream=True)
    text = parse_stream(r)

lat = int((time.time()-t0)*1000)
print(f"[OK] Ollama response ({lat} ms):")
print(text[:400].replace("\n"," "))
