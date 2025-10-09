# from __future__ import annotations
# from dotenv import load_dotenv
# import os, yaml
# from pathlib import Path
# from threading import Lock
# from typing import List, Optional

# from fastapi import FastAPI, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel, Field
# from get_rtmp import fetch_rtmp as android_fetch_rtmp
# from core.browser import launch_browser
# from core.auth import login, wait_for_dashboard
# from core.actions.layouts import select_layout
# from core.actions.sources import list_sources, assign_source_to_grid, set_source_url
# from core import utils
# from fastapi.responses import PlainTextResponse

# load_dotenv()

# # =========================
# # Konfigurasi dasar
# # =========================
# SCENARIO_PATH = os.getenv("SCENARIO_PATH")
# if not Path(SCENARIO_PATH).exists():
#     raise RuntimeError(f"Scenario YAML tidak ditemukan: {SCENARIO_PATH}")

# with open(SCENARIO_PATH, "r", encoding="utf-8") as f:
#     SCN = yaml.safe_load(f) or {}

# BASE_URL = SCN.get("base_url")
# CREDS = SCN.get("login") or {}
# if not BASE_URL or "username" not in CREDS or "password" not in CREDS:
#     raise RuntimeError("Scenario YAML harus berisi base_url dan login.username/password")

# OUT_DIR = utils.OUT_DIR
# OUT_DIR.mkdir(parents=True, exist_ok=True)

# _device_lock = Lock()


# def _run_with_page(fn):
#     pw, browser, context, page = launch_browser(
#         headless=True,
#         record_video=False,
#         out_dir=OUT_DIR,
#     )
#     try:
#         login(page, BASE_URL, CREDS["username"], CREDS["password"])
#         wait_for_dashboard(page)
#         return fn(page)
#     except Exception as e:
#         raise
#     finally:
#         try:
#             context.storage_state(path=str(OUT_DIR / "storage_state.json"))
#         except Exception:
#             pass
#         browser.close()
#         pw.stop()


# # =========================
# # FastAPI app
# # =========================
# app = FastAPI(title="Kiloview Controller API", version="1.0.0")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"], allow_credentials=True,
#     allow_methods=["*"], allow_headers=["*"],
# )


# # =========================
# # Schemas (Pydantic)
# # =========================
# class SourceItem(BaseModel):
#     name: str
#     status: str
#     url: str
#     stream_id: str


# class LayoutReq(BaseModel):
#     cells: int = Field(..., description="Jumlah cell grid: 1,4,9,16,...")
#     # Default True: popup 'Layout shift will lose unsaved data' akan di-OK otomatis
#     confirm_shift: bool = Field(True, description="Auto klik 'OK' jika popup layout shift muncul")


# class AssignOne(BaseModel):
#     grid: int = Field(..., ge=1, description="Index grid (1-based)")
#     name: str = Field(..., description="Nama source sesuai kolom 'name' di list-sources")


# class AssignBulkReq(BaseModel):
#     assigns: List[AssignOne]


# class SetUrlOne(BaseModel):
#     name: str
#     url: str


# class SetUrlBulkReq(BaseModel):
#     items: List[SetUrlOne]


# class RunCombinedReq(BaseModel):
#     # Optional langkah-langkah gabungan
#     layout_cells: Optional[int] = Field(None)
#     confirm_shift: bool = True  # default True
#     set_urls: Optional[List[SetUrlOne]] = None
#     assigns: Optional[List[AssignOne]] = None


# # =========================
# # Endpoints
# # =========================
# @app.get("/health")
# def health():
#     return {"ok": True, "base_url": BASE_URL}


# @app.get("/sources", response_model=List[SourceItem])
# def get_sources():
#     with _device_lock:
#         try:
#             data = _run_with_page(lambda p: list_sources(p))
#             return data
#         except Exception as e:
#             raise HTTPException(status_code=500, detail=f"Failed to list sources: {e}")


# @app.post("/layout")
# def set_layout(req: LayoutReq):
#     with _device_lock:
#         try:
#             def _do(page):
#                 select_layout(page, req.cells, confirm=req.confirm_shift)
#                 return {"ok": True, "cells": req.cells, "confirm_shift": req.confirm_shift}
#             return _run_with_page(_do)
#         except Exception as e:
#             raise HTTPException(status_code=500, detail=f"Failed to set layout: {e}")


# @app.post("/assign")
# def assign_one(req: AssignOne):
#     with _device_lock:
#         try:
#             def _do(page):
#                 assign_source_to_grid(page, req.grid, req.name)
#                 return {"ok": True, "grid": req.grid, "name": req.name}
#             return _run_with_page(_do)
#         except Exception as e:
#             raise HTTPException(status_code=500, detail=f"Failed to assign: {e}")


# @app.post("/assign/bulk")
# def assign_bulk(req: AssignBulkReq):
#     with _device_lock:
#         try:
#             def _do(page):
#                 for item in req.assigns:
#                     assign_source_to_grid(page, item.grid, item.name)
#                 return {"ok": True, "count": len(req.assigns)}
#             return _run_with_page(_do)
#         except Exception as e:
#             raise HTTPException(status_code=500, detail=f"Failed to assign bulk: {e}")


# @app.post("/set-url")
# def set_url_bulk(req: SetUrlBulkReq):
#     with _device_lock:
#         try:
#             def _do(page):
#                 for it in req.items:
#                     set_source_url(page, it.name, it.url)
#                 return {"ok": True, "count": len(req.items)}
#             return _run_with_page(_do)
#         except Exception as e:
#             raise HTTPException(status_code=500, detail=f"Failed to set url(s): {e}")


# @app.post("/run")
# def run_combined(req: RunCombinedReq):
#     """
#     Jalankan beberapa langkah sekaligus:
#     - (opsional) set layout
#     - (opsional) set URL beberapa source
#     - (opsional) assign beberapa source ke grid
#     """
#     with _device_lock:
#         try:
#             def _do(page):
#                 result = {}
#                 if req.layout_cells:
#                     select_layout(page, req.layout_cells, confirm=req.confirm_shift)
#                     result["layout_cells"] = req.layout_cells
#                     result["confirm_shift"] = req.confirm_shift

#                 if req.set_urls:
#                     for it in req.set_urls:
#                         set_source_url(page, it.name, it.url)
#                     result["set_urls"] = len(req.set_urls)

#                 if req.assigns:
#                     for a in req.assigns:
#                         assign_source_to_grid(page, a.grid, a.name)
#                     result["assigns"] = len(req.assigns)

#                 # kembalikan snapshot sumber setelah aksi
#                 result["sources"] = list_sources(page)
#                 return result

#             return _run_with_page(_do)
#         except Exception as e:
#             raise HTTPException(status_code=500, detail=f"Failed to run combined: {e}")

# class AndroidRtmpResp(BaseModel):
#     ok: bool
#     rtmp: Optional[str] = None
#     detail: Optional[str] = None

# @app.get("/android/rtmp", response_model=AndroidRtmpResp)
# def android_get_rtmp(
#     package: str = "com.ybws.newmlive",
#     do_login_taps: bool = True,
#     max_retries: int = 5,
#     scroll_attempts: int = 3,
# ):
#     """
#     Jalankan flow ADB di device Android dan ambil link RTMP yang tampil di UI.
#     Query params bisa disesuaikan:
#     - package: nama paket aplikasi Android
#     - do_login_taps: jalankan ketukan login default
#     - max_retries / scroll_attempts: kontrol scanning layar
#     """
#     with _device_lock:
#         try:
#             link = android_fetch_rtmp(
#                 package=package,
#                 do_login_taps=do_login_taps,
#                 max_retries=max_retries,
#                 scroll_attempts=scroll_attempts,
#             )
#             if not link:
#                 # 404 lebih tepat kalau tidak ditemukan
#                 raise HTTPException(status_code=404, detail="RTMP link not found on screen")
#             return AndroidRtmpResp(ok=True, rtmp=link)
#         except HTTPException:
#             # biarkan apa adanya
#             raise
#         except Exception as e:
#             raise HTTPException(status_code=500, detail=f"Failed to fetch RTMP: {e}")
        
# if __name__ == "__main__":
#     import uvicorn
#     host = os.getenv("API_HOST")
#     port = int(os.getenv("API_PORT"))
#     reload_enabled = os.getenv("API_RELOAD").lower() == "true"
#     uvicorn.run("main:app", host=host, port=port, reload=reload_enabled)


from __future__ import annotations
from dotenv import load_dotenv
import os, yaml
from pathlib import Path
from threading import Lock, Thread, Event
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from get_rtmp import fetch_rtmp as android_fetch_rtmp
from core.browser import launch_browser
from core.auth import login, wait_for_dashboard
from core.actions.layouts import select_layout
from core.actions.sources import list_sources, assign_source_to_grid, set_source_url
from core import utils
from fastapi.responses import PlainTextResponse

# ===== Tambahan untuk cache & polling =====
import json, time
from datetime import datetime, timezone

load_dotenv()

# =========================
# Konfigurasi dasar
# =========================
SCENARIO_PATH = os.getenv("SCENARIO_PATH")
if not Path(SCENARIO_PATH).exists():
    raise RuntimeError(f"Scenario YAML tidak ditemukan: {SCENARIO_PATH}")

with open(SCENARIO_PATH, "r", encoding="utf-8") as f:
    SCN = yaml.safe_load(f) or {}

BASE_URL = SCN.get("base_url")
CREDS = SCN.get("login") or {}
if not BASE_URL or "username" not in CREDS or "password" not in CREDS:
    raise RuntimeError("Scenario YAML harus berisi base_url dan login.username/password")

OUT_DIR = utils.OUT_DIR
OUT_DIR.mkdir(parents=True, exist_ok=True)

_device_lock = Lock()

def _run_with_page(fn):
    pw, browser, context, page = launch_browser(
        headless=True,
        record_video=False,
        out_dir=OUT_DIR,
    )
    try:
        login(page, BASE_URL, CREDS["username"], CREDS["password"])
        wait_for_dashboard(page)
        return fn(page)
    except Exception as e:
        raise
    finally:
        try:
            context.storage_state(path=str(OUT_DIR / "storage_state.json"))
        except Exception:
            pass
        browser.close()
        pw.stop()

# =========================
# FastAPI app
# =========================
app = FastAPI(title="Kiloview Controller API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# =========================
# Schemas (Pydantic)
# =========================
class SourceItem(BaseModel):
    name: str
    status: str
    url: str
    stream_id: str

class LayoutReq(BaseModel):
    cells: int = Field(..., description="Jumlah cell grid: 1,4,9,16,...")
    confirm_shift: bool = Field(True, description="Auto klik 'OK' jika popup layout shift muncul")

class AssignOne(BaseModel):
    grid: int = Field(..., ge=1, description="Index grid (1-based)")
    name: str = Field(..., description="Nama source sesuai kolom 'name' di list-sources")

class AssignBulkReq(BaseModel):
    assigns: List[AssignOne]

class SetUrlOne(BaseModel):
    name: str
    url: str

class SetUrlBulkReq(BaseModel):
    items: List[SetUrlOne]

class RunCombinedReq(BaseModel):
    layout_cells: Optional[int] = Field(None)
    confirm_shift: bool = True
    set_urls: Optional[List[SetUrlOne]] = None
    assigns: Optional[List[AssignOne]] = None

# ===== Tambahan: schema untuk cache =====
class SourcesCacheResp(BaseModel):
    updated_at: Optional[str]
    error: Optional[str]
    data: Optional[List[SourceItem]]

# =========================
# Endpoint existing (tetap apa adanya)
# =========================
@app.get("/health")
def health():
    return {"ok": True, "base_url": BASE_URL}

@app.get("/sources", response_model=List[SourceItem])
def get_sources():
    # PERILAKU LAMA (LIVE): tetap membuka browser & login
    with _device_lock:
        try:
            data = _run_with_page(lambda p: list_sources(p))
            return data
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to list sources: {e}")

@app.post("/layout")
def set_layout(req: LayoutReq):
    with _device_lock:
        try:
            def _do(page):
                select_layout(page, req.cells, confirm=req.confirm_shift)
                return {"ok": True, "cells": req.cells, "confirm_shift": req.confirm_shift}
            return _run_with_page(_do)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to set layout: {e}")

@app.post("/assign")
def assign_one(req: AssignOne):
    with _device_lock:
        try:
            def _do(page):
                assign_source_to_grid(page, req.grid, req.name)
                return {"ok": True, "grid": req.grid, "name": req.name}
            return _run_with_page(_do)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to assign: {e}")

@app.post("/assign/bulk")
def assign_bulk(req: AssignBulkReq):
    with _device_lock:
        try:
            def _do(page):
                for item in req.assigns:
                    assign_source_to_grid(page, item.grid, item.name)
                return {"ok": True, "count": len(req.assigns)}
            return _run_with_page(_do)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to assign bulk: {e}")

@app.post("/set-url")
def set_url_bulk(req: SetUrlBulkReq):
    with _device_lock:
        try:
            def _do(page):
                for it in req.items:
                    set_source_url(page, it.name, it.url)
                return {"ok": True, "count": len(req.items)}
            return _run_with_page(_do)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to set url(s): {e}")

@app.post("/run")
def run_combined(req: RunCombinedReq):
    """
    - (opsional) set layout
    - (opsional) set URL beberapa source
    - (opsional) assign beberapa source ke grid
    """
    with _device_lock:
        try:
            def _do(page):
                result = {}
                if req.layout_cells:
                    select_layout(page, req.layout_cells, confirm=req.confirm_shift)
                    result["layout_cells"] = req.layout_cells
                    result["confirm_shift"] = req.confirm_shift

                if req.set_urls:
                    for it in req.set_urls:
                        set_source_url(page, it.name, it.url)
                    result["set_urls"] = len(req.set_urls)

                if req.assigns:
                    for a in req.assigns:
                        assign_source_to_grid(page, a.grid, a.name)
                    result["assigns"] = len(req.assigns)

                result["sources"] = list_sources(page)
                return result

            return _run_with_page(_do)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to run combined: {e}")

class AndroidRtmpResp(BaseModel):
    ok: bool
    rtmp: Optional[str] = None
    detail: Optional[str] = None

@app.get("/android/rtmp", response_model=AndroidRtmpResp)
def android_get_rtmp(
    package: str = "com.ybws.newmlive",
    do_login_taps: bool = True,
    max_retries: int = 5,
    scroll_attempts: int = 3,
):
    with _device_lock:
        try:
            link = android_fetch_rtmp(
                package=package,
                do_login_taps=do_login_taps,
                max_retries=max_retries,
                scroll_attempts=scroll_attempts,
            )
            if not link:
                raise HTTPException(status_code=404, detail="RTMP link not found on screen")
            return AndroidRtmpResp(ok=True, rtmp=link)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch RTMP: {e}")

# =========================
# ======== TAMBAHAN: Worker cache setiap 20 detik ========
# =========================
POLL_INTERVAL_SEC = int(os.getenv("SOURCES_POLL_INTERVAL", "20"))
CACHE_PATH = OUT_DIR / "sources_cache.json"

_cache = {
    "updated_at": None,  # ISO string UTC
    "error": None,       # pesan error polling terakhir (jika ada)
    "data": None         # List[SourceItem] atau None
}

_stop_event = Event()
_worker_thread: Optional[Thread] = None

def _write_cache_to_disk():
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _load_cache_from_disk_if_any():
    if CACHE_PATH.exists():
        try:
            data = json.load(open(CACHE_PATH, "r", encoding="utf-8"))
            # Validasi ringan
            if isinstance(data, dict):
                _cache.update({
                    "updated_at": data.get("updated_at"),
                    "error": data.get("error"),
                    "data": data.get("data"),
                })
        except Exception:
            pass

def _poll_sources_once():
    global _cache
    with _device_lock:
        data = _run_with_page(lambda p: list_sources(p))
    _cache = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
        "data": data
    }
    _write_cache_to_disk()

def _poller_loop():
    _load_cache_from_disk_if_any()
    # seed awal (tidak blocking kalau error)
    try:
        _poll_sources_once()
    except Exception as e:
        _cache["error"] = f"initial poll failed: {e}"
        _cache["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_cache_to_disk()

    # loop periodik
    while not _stop_event.wait(POLL_INTERVAL_SEC):
        try:
            _poll_sources_once()
        except Exception as e:
            _cache["error"] = f"poll failed: {e}"
            _cache["updated_at"] = datetime.now(timezone.utc).isoformat()
            _write_cache_to_disk()

@app.on_event("startup")
def _on_startup():
    global _worker_thread
    _worker_thread = Thread(target=_poller_loop, name="sources-poller", daemon=True)
    _worker_thread.start()

@app.on_event("shutdown")
def _on_shutdown():
    _stop_event.set()
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=5)

# ===== Endpoint baru untuk konsumsi cache (non-breaking) =====
@app.get("/sources_cached", response_model=List[SourceItem])
def get_sources_cached():
    if _cache["data"] is None:
        raise HTTPException(status_code=503, detail="Cache belum tersedia. Coba lagi beberapa detik.")
    return _cache["data"]

@app.get("/sources/cache", response_model=SourcesCacheResp)
def get_sources_cache_meta():
    return SourcesCacheResp(**_cache)

# =========================
# Entrypoint
# =========================
if __name__ == "__main__":
    import uvicorn
    host = os.getenv("API_HOST")
    port = int(os.getenv("API_PORT"))
    reload_enabled = os.getenv("API_RELOAD", "false").lower() == "true"
    uvicorn.run("main:app", host=host, port=port, reload=reload_enabled)
