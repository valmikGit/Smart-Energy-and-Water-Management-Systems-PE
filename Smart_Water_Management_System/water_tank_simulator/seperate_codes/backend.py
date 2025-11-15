# backend.py
import os
import re
import csv
import time
import json
import threading
import asyncio
from queue import Queue, Empty
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi import Request
import uvicorn

# Optional Redis (if REDIS_URL env var set)
try:
    import redis.asyncio as aioredis
    import redis
    REDIS_AVAILABLE = True
except Exception:
    aioredis = None
    redis = None
    REDIS_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Configure relative CSVs (edit paths to actual CSV location)
CSV_FILENAMES = [
    "data/Water_History_A1FD_2025-05-16_06-58.csv",
    "data/Water_History_A1FD_2025-05-16_07-00.csv",
    "data/Water_History_A1FF_2025-05-16_06-58.csv",
    "data/Water_History_A1MD_2025-05-16_06-59.csv",
    "data/Water_History_A1MD_2025-05-16_07-00.csv",
    "data/Water_History_A2MFF_2025-05-16_07-00.csv",
    "data/Water_History_BTTF_2025-05-16_07-01.csv",
]
CSV_PATHS = [os.path.join(BASE_DIR, p) for p in CSV_FILENAMES]

DEFAULT_DELAY_SECONDS = 1.0

# In-memory structures
EVENT_QUEUE: "Queue[Dict[str,Any]]" = Queue()
LATEST_STATE: Dict[str, Dict[str, Any]] = {}
LATEST_LOCK = threading.Lock()

# Data store for preloaded CSVs
DATA_STORE: Dict[str, Dict[str, Any]] = {}

# Workers and control
WORKER_EVENTS: Dict[str, threading.Event] = {}
WORKER_THREADS: Dict[str, threading.Thread] = {}

# For SSE/Websocket broadcasting (async)
SUBSCRIBERS: List[asyncio.Queue] = []
SUBSCRIBERS_LOCK = threading.Lock()
ASYNC_LOOP: Optional[asyncio.AbstractEventLoop] = None

# Redis settings (optional)
REDIS_URL = os.environ.get("REDIS_URL", None)
REDIS_CHANNEL = "tank_events"
REDIS_LATEST_KEY = "tank_latest_state"

app = FastAPI(title="Tank Simulation Backend (with SSE/WS/Redis)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------
# CSV helper
# -------------------
def _try_parse_datetime(s: str) -> Optional[datetime]:
    if not s:
        return None
    s = s.strip()
    fmts = [
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M",
        "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M",
        "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
        "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y",
        "%H:%M:%S", "%H:%M",
    ]
    for f in fmts:
        try:
            return datetime.strptime(s, f)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

def preload_csv(csv_path: str) -> Tuple[Optional[List[datetime]], Optional[List[float]], Optional[float], Optional[float], Optional[float], str]:
    if not os.path.exists(csv_path):
        return None, None, None, None, None, f"File not found: {csv_path}"
    timestamps = []
    values = []
    try:
        with open(csv_path, encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            headers = reader.fieldnames or []
            if not headers:
                return None, None, None, None, None, "CSV has no header row"
            norm_map = {}
            for h in headers:
                if h:
                    k = re.sub(r"[\s_()\-\[\]/:\\]", "", h.lower())
                    k = re.sub(r"liters|liter|l|m3|m³|kg|g", "", k)
                    norm_map[k] = h
            time_key = None
            value_key = None
            for cand in ["timestamp", "datetime", "date", "time", "ts"]:
                if cand in norm_map:
                    time_key = norm_map[cand]; break
            for cand in ["value", "volume", "level", "consumption", "flow", "reading"]:
                if cand in norm_map:
                    value_key = norm_map[cand]; break
            if not time_key:
                for h in headers:
                    if re.search(r"date|time|timestamp", h, re.I):
                        time_key = h; break
            if not value_key:
                for h in headers:
                    if re.search(r"value|volume|level|consum|flow|reading", h, re.I):
                        value_key = h; break
            if not time_key or not value_key:
                return None, None, None, None, None, f"Missing timestamp/value columns. Headers: {headers}"
            for row in reader:
                ts_raw = row.get(time_key, "")
                v_raw = row.get(value_key, "")
                ts = _try_parse_datetime(str(ts_raw).strip())
                if ts is None:
                    continue
                v_s = str(v_raw).strip()
                cleaned = re.sub(r"[^\d\.\-eE]", "", v_s)
                try:
                    v = float(cleaned)
                except:
                    s2 = v_s.replace(",", ".")
                    try:
                        v = float(re.sub(r"[^\d\.\-eE]", "", s2))
                    except:
                        continue
                timestamps.append(ts)
                values.append(v)
    except Exception as e:
        return None, None, None, None, None, f"CSV read error: {e}"
    if not values:
        return None, None, None, None, None, "No numeric rows found"
    combined = sorted(zip(timestamps, values), key=lambda x: x[0])
    timestamps_sorted, values_sorted = zip(*combined)
    gmin = float(min(values_sorted))
    gmax = float(max(values_sorted))
    grange = float(gmax - gmin) if gmax != gmin else 1.0
    return list(timestamps_sorted), list(values_sorted), gmin, gmax, grange, ""

# -------------------
# Worker
# -------------------
def worker_loop(name: str, timestamps: List[datetime], values: List[float], gmin: float, grange: float, delay_seconds: float, stop_event: threading.Event):
    n = len(values)
    idx = 0
    with LATEST_LOCK:
        LATEST_STATE[name] = {"level": 0.0, "timestamp": "", "progress_step": 0, "total_updates": n, "status": "Running"}
    while not stop_event.is_set():
        raw_val = values[idx]
        ts = timestamps[idx].strftime("%Y-%m-%d %H:%M:%S")
        normalized = (raw_val - gmin) / grange
        level_m3 = normalized * 10.0
        event = {
            "tank_id": name,
            "timestamp": ts,
            "raw_value": raw_val,
            "normalized": normalized,
            "level_m3": round(level_m3, 3),
            "progress_step": idx + 1,
            "total_updates": n,
        }
        # push to in-memory queue
        EVENT_QUEUE.put(event)
        # publish to Redis if configured (synchronous publish), and set latest hash
        if REDIS_URL and REDIS_AVAILABLE:
            try:
                r = redis.StrictRedis.from_url(REDIS_URL)
                r.publish(REDIS_CHANNEL, json.dumps(event))
                # set latest state as JSON string
                r.hset(REDIS_LATEST_KEY, name, json.dumps({
                    "level": round(level_m3, 3),
                    "timestamp": ts,
                    "progress_step": idx+1,
                    "total_updates": n,
                    "status": "Running"
                }))
            except Exception:
                pass
        # update LATEST_STATE
        with LATEST_LOCK:
            LATEST_STATE[name].update({
                "level": round(level_m3, 3),
                "timestamp": ts,
                "progress_step": idx + 1,
                "total_updates": n,
                "status": "Running",
            })
        # broadcast to SSE/WS subscribers (async)
        if ASYNC_LOOP is not None:
            # place into all subscriber queues
            with SUBSCRIBERS_LOCK:
                for q in SUBSCRIBERS:
                    try:
                        ASYNC_LOOP.call_soon_threadsafe(q.put_nowait, event)
                    except Exception:
                        pass
        time.sleep(max(0.0, float(delay_seconds)))
        idx += 1
        if idx >= n:
            idx = 0
    with LATEST_LOCK:
        if name in LATEST_STATE:
            LATEST_STATE[name]["status"] = "Stopped"

# -------------------
# Startup helpers for ASYNC loop
# -------------------
def start_background_forwarder(loop: asyncio.AbstractEventLoop):
    # not used much here; kept for potential extension
    pass

# -------------------
# API endpoints
# -------------------
@app.post("/start")
async def start_simulation(req: Request):
    """
    Body (JSON): {"delay_seconds": 1.0, "csv_paths": ["optional list of paths relative to BASE_DIR"]}
    """
    body = await req.json()
    delay_seconds = body.get("delay_seconds", DEFAULT_DELAY_SECONDS)
    csv_paths = body.get("csv_paths", None)
    paths = CSV_PATHS if not csv_paths else [os.path.join(BASE_DIR, p) for p in csv_paths]

    # preload all CSVs
    DATA_STORE.clear()
    errors = []
    for p in paths:
        name = os.path.splitext(os.path.basename(p))[0]
        ts, vals, gmin, gmax, grange, err = preload_csv(p)
        if err:
            errors.append(f"{name}: {err}")
            continue
        DATA_STORE[name] = {"csv_path": p, "timestamps": ts, "values": vals, "gmin": gmin, "gmax": gmax, "grange": grange}
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    # stop existing workers
    for ev in list(WORKER_EVENTS.values()):
        ev.set()
    for t in list(WORKER_THREADS.values()):
        if t.is_alive():
            t.join(timeout=0.2)
    WORKER_EVENTS.clear()
    WORKER_THREADS.clear()

    # clear latest state (keep queue)
    with LATEST_LOCK:
        LATEST_STATE.clear()

    # if Redis available, optionally clear latest key
    if REDIS_URL and REDIS_AVAILABLE:
        try:
            rcli = redis.StrictRedis.from_url(REDIS_URL)
            rcli.delete(REDIS_LATEST_KEY)
        except Exception:
            pass

    # start workers
    for name, info in DATA_STORE.items():
        ev = threading.Event()
        WORKER_EVENTS[name] = ev
        t = threading.Thread(target=worker_loop, args=(name, info["timestamps"], info["values"], info["gmin"], info["grange"], delay_seconds, ev), daemon=True)
        WORKER_THREADS[name] = t
        t.start()

    return JSONResponse({"status": "started", "tanks": list(DATA_STORE.keys()), "delay_seconds": delay_seconds})

@app.post("/stop")
def stop_simulation():
    for ev in list(WORKER_EVENTS.values()):
        ev.set()
    for t in list(WORKER_THREADS.values()):
        if t.is_alive():
            t.join(timeout=0.2)
    WORKER_EVENTS.clear()
    WORKER_THREADS.clear()
    return {"status": "stopped"}

@app.get("/events")
def get_events(max_events: int = Query(200)):
    events = []
    for _ in range(max_events):
        try:
            e = EVENT_QUEUE.get_nowait()
            events.append(e)
        except Empty:
            break
    return {"events": events, "returned": len(events)}

@app.get("/latest")
def latest():
    # Prefer Redis latest if available
    result = {}
    if REDIS_URL and REDIS_AVAILABLE:
        try:
            rc = redis.StrictRedis.from_url(REDIS_URL)
            items = rc.hgetall(REDIS_LATEST_KEY)
            if items:
                for k, v in items.items():
                    try:
                        result[k.decode() if isinstance(k, bytes) else k] = json.loads(v)
                    except Exception:
                        pass
        except Exception:
            pass
    if not result:
        with LATEST_LOCK:
            result = {k: v.copy() for k, v in LATEST_STATE.items()}
    return {"latest": result}

@app.get("/status")
def status():
    with LATEST_LOCK:
        snapshot = {k: v.copy() for k, v in LATEST_STATE.items()}
    running = any(v.get("status") == "Running" for v in snapshot.values()) if snapshot else False
    return {"running": running, "tanks": list(snapshot.keys()), "latest": snapshot, "queue_size": EVENT_QUEUE.qsize()}

@app.get("/list")
def list_csvs():
    avail = [os.path.basename(p) for p in CSV_PATHS]
    return {"csv_paths": CSV_PATHS, "available": avail}

@app.get("/health")
def health():
    return {"ok": True}

# -------------------
# SSE endpoint
# -------------------
from fastapi.responses import StreamingResponse

async def sse_event_generator(client_queue: asyncio.Queue):
    try:
        while True:
            ev = await client_queue.get()
            if ev is None:
                break
            # SSE format: "data: <json>\n\n"
            yield f"data: {json.dumps(ev)}\n\n"
    except asyncio.CancelledError:
        return

@app.get("/stream/sse")
async def stream_sse():
    """
    Server-Sent Events endpoint. Creates a per-client asyncio.Queue, registers it, and returns a stream.
    """
    # create per-client queue
    q: asyncio.Queue = asyncio.Queue()
    with SUBSCRIBERS_LOCK:
        SUBSCRIBERS.append(q)
    # Return streaming response
    response = StreamingResponse(sse_event_generator(q), media_type="text/event-stream")
    return response

# -------------------
# WebSocket endpoint
# -------------------
@app.websocket("/stream/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    q = asyncio.Queue()
    with SUBSCRIBERS_LOCK:
        SUBSCRIBERS.append(q)
    try:
        while True:
            ev = await q.get()
            if ev is None:
                break
            await ws.send_text(json.dumps(ev))
    except WebSocketDisconnect:
        pass
    finally:
        with SUBSCRIBERS_LOCK:
            if q in SUBSCRIBERS:
                SUBSCRIBERS.remove(q)

# -------------------
# Lifespan: capture asyncio loop
# -------------------
@app.on_event("startup")
async def startup_event():
    global ASYNC_LOOP
    ASYNC_LOOP = asyncio.get_event_loop()
    # If Redis configured and available, optionally create an async subscriber to Redis channel and fan-out to SUBSCRIBERS
    if REDIS_URL and REDIS_AVAILABLE:
        try:
            redis_client = aioredis.from_url(REDIS_URL)
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(REDIS_CHANNEL)

            async def redis_listener():
                async for message in pubsub.listen():
                    if message is None:
                        continue
                    if message.get("type") != "message":
                        continue
                    raw = message.get("data")
                    try:
                        ev = json.loads(raw)
                    except Exception:
                        continue
                    # fan out to internal subscribers
                    with SUBSCRIBERS_LOCK:
                        for q in SUBSCRIBERS:
                            await q.put(ev)

            asyncio.create_task(redis_listener())
        except Exception:
            pass

@app.on_event("shutdown")
async def shutdown_event():
    # close subscribers
    with SUBSCRIBERS_LOCK:
        for q in SUBSCRIBERS:
            try:
                q.put_nowait(None)
            except Exception:
                pass
        SUBSCRIBERS.clear()

# -------------------
# Run
# -------------------
if __name__ == "__main__":
    uvicorn.run("backend:app", host="0.0.0.0", port=8000, reload=False)