"""Notes demo app for Kubernetes + MCP debugging practice.

Normal endpoints:   /            HTML page
                    /api/notes   GET list, POST {"text": "..."}
Ops endpoints:      /healthz     liveness  (process alive)
                    /readyz      readiness (Redis reachable, not forced unready)
                    /metrics     Prometheus metrics
Chaos endpoints:    /chaos/crash     exit the process            -> CrashLoopBackOff
                    /chaos/leak      allocate memory each call   -> OOMKilled
                    /chaos/cpu       burn CPU for N seconds      -> HPA scale-up
                    /chaos/slow      slow response               -> latency
                    /chaos/unready   toggle readiness failure    -> no endpoints
"""

import json
import logging
import os
import sys
import threading
import time

import redis
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
CHAOS_ENABLED = os.getenv("CHAOS_ENABLED", "true").lower() == "true"


# ---------- structured JSON logging ----------
class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "msg": record.getMessage(),
            "version": APP_VERSION,
        }
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
log = logging.getLogger("notes")
log.addHandler(handler)
log.setLevel(logging.INFO)

# ---------- metrics ----------
REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "path", "status"])
LATENCY = Histogram("http_request_duration_seconds", "Request latency", ["path"])
LEAKED_MB = Gauge("chaos_leaked_megabytes", "Memory leaked via /chaos/leak")
NOTES_TOTAL = Gauge("notes_total", "Number of notes stored")

# ---------- state ----------
app = FastAPI(title="Notes Demo", version=APP_VERSION)
rdb = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, socket_timeout=1, socket_connect_timeout=1,
                  decode_responses=True)
state = {"force_unready": False, "leak": []}


class Note(BaseModel):
    text: str


@app.middleware("http")
async def observe(request: Request, call_next):
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        path = request.url.path
        LATENCY.labels(path).observe(time.perf_counter() - start)
        REQUESTS.labels(request.method, path, str(status)).inc()
        if path not in ("/healthz", "/readyz", "/metrics"):
            log.info(f"{request.method} {path} {status}")


# ---------- app endpoints ----------
@app.get("/", response_class=HTMLResponse)
def index():
    return f"""<!doctype html><html><head><title>Notes Demo</title>
<style>body{{font-family:system-ui;max-width:640px;margin:40px auto;padding:0 16px}}
li{{padding:4px 0}}input{{width:70%;padding:6px}}button{{padding:6px 12px}}</style></head>
<body><h1>Notes Demo <small style="color:#888">v{APP_VERSION}</small></h1>
<p>Pod: <code>{os.getenv('HOSTNAME', 'local')}</code></p>
<form onsubmit="add(event)"><input id="t" placeholder="Write a note"><button>Add</button></form>
<ul id="list"></ul>
<script>
async function load(){{const r=await fetch('/api/notes');const d=await r.json();
 document.getElementById('list').innerHTML=d.notes.map(n=>'<li>'+n.replace(/</g,'&lt;')+'</li>').join('');}}
async function add(e){{e.preventDefault();const t=document.getElementById('t');
 await fetch('/api/notes',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{text:t.value}})}});
 t.value='';load();}}
load();
</script></body></html>"""


@app.get("/api/notes")
def list_notes():
    try:
        notes = rdb.lrange("notes", 0, -1)
    except redis.RedisError as exc:
        log.error(f"redis read failed: {exc}")
        raise HTTPException(503, "storage unavailable")
    NOTES_TOTAL.set(len(notes))
    return {"notes": notes}


@app.post("/api/notes", status_code=201)
def add_note(note: Note):
    try:
        rdb.rpush("notes", note.text[:500])
    except redis.RedisError as exc:
        log.error(f"redis write failed: {exc}")
        raise HTTPException(503, "storage unavailable")
    return {"ok": True}


# ---------- ops endpoints ----------
@app.get("/healthz")
def healthz():
    return {"status": "alive", "version": APP_VERSION}


@app.get("/readyz")
def readyz(response: Response):
    if state["force_unready"]:
        response.status_code = 503
        return {"status": "unready", "reason": "forced via /chaos/unready"}
    try:
        rdb.ping()
    except redis.RedisError as exc:
        response.status_code = 503
        log.warning(f"readiness failed: redis unreachable ({exc})")
        return {"status": "unready", "reason": "redis unreachable"}
    return {"status": "ready"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ---------- chaos endpoints ----------
def _require_chaos():
    if not CHAOS_ENABLED:
        raise HTTPException(403, "chaos disabled")


@app.post("/chaos/crash")
def chaos_crash():
    _require_chaos()
    log.critical("chaos: crashing process on purpose")
    threading.Timer(0.2, lambda: os._exit(1)).start()
    return {"crashing": True}


@app.post("/chaos/leak")
def chaos_leak(mb: int = 50):
    _require_chaos()
    state["leak"].append(bytearray(mb * 1024 * 1024))
    total = sum(len(b) for b in state["leak"]) // (1024 * 1024)
    LEAKED_MB.set(total)
    log.warning(f"chaos: leaked {mb} MB, total {total} MB")
    return {"leaked_total_mb": total}


@app.post("/chaos/cpu")
def chaos_cpu(seconds: int = 60):
    _require_chaos()

    def burn(end):
        while time.time() < end:
            pass

    end = time.time() + min(seconds, 600)
    threading.Thread(target=burn, args=(end,), daemon=True).start()
    log.warning(f"chaos: burning CPU for {seconds}s")
    return {"burning_seconds": seconds}


@app.get("/chaos/slow")
def chaos_slow(seconds: float = 5):
    _require_chaos()
    time.sleep(min(seconds, 60))
    return {"slept": seconds}


@app.post("/chaos/unready")
def chaos_unready():
    _require_chaos()
    state["force_unready"] = not state["force_unready"]
    log.warning(f"chaos: force_unready={state['force_unready']}")
    return {"force_unready": state["force_unready"]}


log.info(f"notes app starting version={APP_VERSION} redis={REDIS_HOST}:{REDIS_PORT}")
