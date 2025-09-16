from __future__ import annotations

import re
import time
from typing import List, Dict, Tuple, Optional

from playwright.sync_api import Page, Error
GRID_CELL_SEL = ".layout-grid-content .grid-list-item"
SOURCE_ITEM_SEL = "div.discovery-list-item"


def _find_source_item(page: Page, name: str):
    item = page.locator("div.discovery-list-item").filter(has_text=name).first
    # pastikan terlihat
    try:
        item.scroll_into_view_if_needed(timeout=2_000)
    except Error:
        pass
    return item


def list_sources(page: Page) -> List[Dict[str, str]]:
    items = page.locator("div.discovery-list-item")
    count = items.count()
    result: List[Dict[str, str]] = []
    for i in range(count):
        it = items.nth(i)
        # nama
        name = ""
        cand = it.locator("img + span[title]").first
        if cand.count():
            name = (cand.get_attribute("title") or cand.inner_text()).strip()
        else:
            # fallback: ambil span[title] pertama yang BUKAN di dalam .item-status-ip
            spans = it.locator("span[title]")
            for j in range(spans.count()):
                sp = spans.nth(j)
                in_status = sp.evaluate("el => !!el.closest('.item-status-ip')")
                if not in_status:
                    name = (sp.get_attribute("title") or sp.inner_text()).strip()
                    break

        # stream-id (jika ada)
        try:
            stream_id = it.get_attribute("data-stream-id") or ""
        except Error:
            stream_id = ""

        # url / address (jika tampak)
        url_el = it.locator(".item-status-ip span.over-ellipsis")
        url = (url_el.inner_text().strip() if url_el.count() else "")

        # status text (Connected / Network Error / Not Connected / dll)
        status_el = it.locator(".display-flex.align-items-center span.ft-12")
        status = status_el.inner_text().strip() if status_el.count() else ""

        result.append({
            "name": name,
            "status": status,
            "url": url,
            "stream_id": stream_id,
        })
    return result


def _grid_cell_by_index(page: Page, grid_index_1based: int):
    cells = page.locator(".layout-grid-content .grid-list-item")
    idx0 = grid_index_1based - 1
    return cells.nth(idx0)


def activate_grid_cell(page: Page, grid_index_1based: int, timeout_ms: int = 5000):
    idx = grid_index_1based - 1
    cells = page.locator(GRID_CELL_SEL)

    # 1) Pastikan sel ke-idx sudah ter-attach
    cells.nth(idx).wait_for(state="attached", timeout=timeout_ms)
    target = cells.nth(idx)

    # (opsional) scroll biar aman di headless
    try:
        target.scroll_into_view_if_needed()
    except Exception:
        pass

    # 2) Klik sel
    target.click()

    # 3) Tunggu sampai sel itu jadi "active-item" (pakai index, bukan handle)
    def _wait_active(idx: int, timeout: int):
        page.wait_for_function(
            """
            (i) => {
              const nodes = document.querySelectorAll('.layout-grid-content .grid-list-item');
              const el = nodes[i];
              return !!el && el.classList && el.classList.contains('active-item');
            }
            """,
            arg=idx,
            timeout=timeout
        )

    try:
        _wait_active(idx, 2000)
    except Error:
        # Retry sekali lagi (klik lagi, lalu tunggu lebih lama)
        target.click()
        page.wait_for_timeout(150)
        _wait_active(idx, 3000)


def assign_source_to_grid(page: Page, grid_index_1based: int, source_name: str):
    # Aktivasi sel grid tujuan
    activate_grid_cell(page, grid_index_1based)

    # Cari item source berdasarkan nama
    # Catatan: filter by text; jika nama mengandung spasi/kapital, tetap cocokkan apa adanya
    src = page.locator(SOURCE_ITEM_SEL).filter(has_text=source_name).first

    # Pastikan ada
    src.wait_for(state="visible", timeout=5000)

    # Scroll biar aman
    try:
        src.scroll_into_view_if_needed()
    except Exception:
        pass

    # UI kamu butuh double-click untuk “push” ke grid
    src.dblclick(timeout=3000)

    # (opsional) kecilkan jeda agar UI sempat update
    page.wait_for_timeout(200)

def _wait_visible_dialog(page: Page):
    dlg = page.locator(".el-dialog__wrapper:visible, .el-message-box__wrapper:visible")
    dlg.wait_for(state="visible", timeout=5_000)
    return dlg.first


def _find_url_input_in_dialog(dlg) -> Optional[object]:
    cand = dlg.locator("input.el-input__inner")
    n = cand.count()
    # coba berdasarkan value
    for i in range(n):
        inp = cand.nth(i)
        try:
            val = (inp.input_value() or "").strip()
            ph = (inp.get_attribute("placeholder") or "").lower()
        except Error:
            val, ph = "", ""
        if any(proto in val.lower() for proto in ("rtsp://", "http://", "https://", "rtmp://")):
            return inp
        if any(key in ph for key in ("url", "address", "stream", "rtsp", "http", "rtmp")):
            return inp
    # fallback: pertama
    return cand.first if n > 0 else None


def _click_dialog_primary(dlg):
    btns = dlg.locator(
        "button:has-text('Save'), "
        "button:has-text('OK'), "
        "button:has-text('Confirm'), "
        "button:has-text('保存'), "
        "button:has-text('确定'), "
        "button.el-button--primary"
    )
    if btns.count() == 0:
        raise RuntimeError("Tombol Save/OK/Confirm di dialog tidak ditemukan.")
    btns.first.click()


def set_source_url(page: Page, source_name: str, new_url: str):
    item = _find_source_item(page, source_name)
    if not item or item.count() == 0:
        raise RuntimeError(f"Source '{source_name}' tidak ditemukan.")

    # Hover agar ikon muncul, lalu klik ikon gear (shezhi)
    try:
        item.hover()
    except Error:
        pass

    gear = item.locator(".icon-setting i.icon-shezhi")
    if gear.count() == 0:
        # fallback: ikon setting lain di dalam item
        gear = item.locator("i.icon-shezhi")
    if gear.count() == 0:
        raise RuntimeError("Ikon 'settings' tidak ditemukan pada item source.")

    gear.first.click()

    # Tunggu dialog
    dlg = _wait_visible_dialog(page)

    # Temukan input URL
    url_input = _find_url_input_in_dialog(dlg)
    if not url_input or url_input.count() == 0:
        raise RuntimeError("Field URL pada dialog tidak ditemukan.")

    # Isi URL baru (fill() otomatis clear + type)
    url_input.fill(new_url)

    # Klik OK/Save
    _click_dialog_primary(dlg)

    # Tunggu dialog tertutup
    dlg.wait_for(state="hidden", timeout=5_000)
