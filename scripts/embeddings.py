# -*- coding: utf-8 -*-
"""
MemoryOS Embedding Layer (Provider-Agnostic, Cached)
- READ-ONLY usage for context recall
"""
import os, time, hashlib, json
from typing import List, Optional
from math import sqrt
from pathlib import Path

# ---- Config
PROVIDER = os.environ.get("MEMORYOS_EMBED_PROVIDER", "stub")  # openai|ollama|hf|stub
MODEL    = os.environ.get("MEMORYOS_EMBED_MODEL", "text-embedding-3-small")
TIMEOUT  = float(os.environ.get("MEMORYOS_EMBED_TIMEOUT", "2.0"))  # seconds
CACHE_ON = os.environ.get("MEMORYOS_EMBED_CACHE", "true").lower() == "true"
CACHE_DIR = Path(os.environ.get("MEMORYOS_EMBED_CACHE_DIR", "./.cache/embeddings"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _cache_key(text:str)->str:
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{PROVIDER}:{MODEL}:{h}"

def _cache_get(key:str)->Optional[List[float]]:
    if not CACHE_ON: return None
    p = CACHE_DIR / f"{hashlib.sha1(key.encode()).hexdigest()}.json"
    if not p.exists(): return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def _cache_put(key:str, vec:List[float])->None:
    if not CACHE_ON: return
    p = CACHE_DIR / f"{hashlib.sha1(key.encode()).hexdigest()}.json"
    try:
        p.write_text(json.dumps(vec), encoding="utf-8")
    except Exception:
        pass

def _normalize(v:List[float])->List[float]:
    n = sqrt(sum(x*x for x in v)) or 1.0
    return [x/n for x in v]

def cosine_sim(a:List[float], b:List[float])->float:
    if not a or not b or len(a)!=len(b): return 0.0
    dot = sum(x*y for x,y in zip(a,b))
    return dot

# ---- Providers (minimal implementations; replace calls as needed)
def _stub_embed(text:str)->List[float]:
    # deterministic 64-dim for offline tests
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    raw = [b/255.0 for b in digest[:64]]
    return _normalize(raw)

def _openai_embed(text:str)->List[float]:
    # placeholder; leave actual API call for integration environment
    # MUST NOT error if key missing; gracefully fallback to stub
    if not os.environ.get("OPENAI_API_KEY"):
        return _stub_embed(text)
    # integrate your actual client here with timeout
    return _stub_embed(text)

def _ollama_embed(text:str)->List[float]:
    # placeholder for local model; safe fallback to stub
    return _stub_embed(text)

def _hf_embed(text:str)->List[float]:
    # placeholder for HF Inference; safe fallback
    return _stub_embed(text)

def get_emb(text:str)->List[float]:
    key = _cache_key(text[:2048])  # cap input
    v = _cache_get(key)
    if v: return v
    start = time.perf_counter()
    try:
        if PROVIDER == "openai":
            vec = _openai_embed(text)
        elif PROVIDER == "ollama":
            vec = _ollama_embed(text)
        elif PROVIDER == "hf":
            vec = _hf_embed(text)
        else:
            vec = _stub_embed(text)
    except Exception:
        vec = _stub_embed(text)
    dur = time.perf_counter() - start
    if dur > TIMEOUT:
        # soft timeout (just log via file; never raise)
        try:
            Path("./logs").mkdir(exist_ok=True)
            Path("./logs/memoryos_metrics.log").write_text(
                f"[{time.time():.0f}] embed_timeout provider={PROVIDER} dur={dur:.3f}\n",
                encoding="utf-8"
            )
        except Exception:
            pass
    _cache_put(key, vec)
    return vec