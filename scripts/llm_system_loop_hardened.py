# -*- coding: utf-8 -*-
import argparse, json, time, signal, uuid
from datetime import datetime, timedelta, timezone
import requests, sys, os

# --- ensure scripts folder on sys.path (for append_event.py) ---
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path: sys.path.append(_here)

from append_event import append_event
from build_context import build_context

STOP_FLAG = False
def _sigint(_, __):
    global STOP_FLAG; STOP_FLAG = True
signal.signal(signal.SIGINT, _sigint)

def now_utc_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def soft_stop(deadline_utc, window_sec=60):
    return (deadline_utc - datetime.now(timezone.utc)).total_seconds() <= window_sec

def parse_until(s):
    s = s.strip().replace(" ", "T")
    try:
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except Exception:
        # fallback: treat naive as KST(+9)
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone(timedelta(hours=9))).astimezone(timezone.utc)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://127.0.0.1:11434/api/generate")
    ap.add_argument("--model", default="llama3")
    ap.add_argument("--db", default=os.environ.get("MEMORYOS_DB"))
    ap.add_argument("--log", default=os.path.join(_here, "..", "logs", "event_log.jsonl"))
    ap.add_argument("--until", required=True)   # e.g., 2025-10-23T10:00:00+09:00
    ap.add_argument("--sleep-ms", type=int, default=0)
    ap.add_argument("--connect-timeout", type=float, default=3.0)
    ap.add_argument("--read-timeout", type=float, default=15.0)
    args = ap.parse_args()

    deadline_utc = parse_until(args.until)
    sess = requests.Session()

    # open JSONL
    os.makedirs(os.path.dirname(args.log), exist_ok=True)
    log_fp = open(args.log, "a", encoding="utf-8")

    def emit(event, data):
        rec = {"ts": now_utc_iso(), "event": event, "data": data}
        try:
            log_fp.write(json.dumps(rec, ensure_ascii=False)+"\n"); log_fp.flush()
        except Exception:
            pass
        if args.db:
            try:
                append_event(args.db, event, str(uuid.uuid4()), data)
            except Exception:
                pass

    i = 0
    try:
        while not STOP_FLAG:
            if soft_stop(deadline_utc, 60):
                emit("soft_stop", {"note":"within 60s of deadline"}); break
            if datetime.now(timezone.utc) >= deadline_utc:
                break

            i += 1
            
            # Prepare user input (in a real system, this would come from user input)
            user_input = f"[Δ] iteration {i}"
            
            # Build context for this input
            context = build_context(user_input)
            
            # Construct the final prompt with context injection
            if context:
                prompt = f"{context}\n\n[USER INPUT]\n{user_input}"
            else:
                prompt = user_input
            
            payload = {"model": args.model, "prompt": prompt, "stream": False}
            t0 = time.perf_counter()
            try:
                r = sess.post(args.endpoint, json=payload, timeout=(args.connect_timeout, args.read_timeout))
                latency_ms = round((time.perf_counter()-t0)*1000.0, 1)
                if r.status_code==200:
                    emit("llm_call", {"iter": i, "status": r.status_code, "latency_ms": latency_ms})
                else:
                    emit("error", {"iter": i, "status": r.status_code, "latency_ms": latency_ms})
            except requests.exceptions.Timeout:
                latency_ms = round((time.perf_counter()-t0)*1000.0, 1)
                emit("timeout", {"iter": i, "latency_ms": latency_ms})
            except Exception as e:
                emit("exception", {"iter": i, "err": str(e)})

            if args.sleep_ms>0:
                time.sleep(args.sleep_ms/1000.0)
    finally:
        emit("shutdown", {"reason": "deadline" if datetime.now(timezone.utc)>=deadline_utc else ("signal" if STOP_FLAG else "unknown")})
        try: log_fp.close()
        except: pass
        print(f"✅ Finished at {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')} (target {args.until})")

if __name__ == "__main__":
    main()
