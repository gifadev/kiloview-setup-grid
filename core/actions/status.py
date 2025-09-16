from typing import List, Dict
from playwright.sync_api import Page
from ..ui_selectors import LIST_SOURCE_ITEM

PROTO_PREFIXES = ("rtsp://", "rtmp://", "http://", "https://")

def _pick_name_from_item(item) -> str:
    # Cari <span title="..."> yang bukan URL (bukan rtsp/rtmp/http)
    spans = item.locator('span[title]')
    count = spans.count()
    for i in range(count):
        t = (spans.nth(i).get_attribute("title") or "").strip()
        if t and not t.lower().startswith(PROTO_PREFIXES):
            return t
    # fallback: teks pertama yang non-kosong
    txt = (item.inner_text() or "").strip().splitlines()
    return next((l.strip() for l in txt if l.strip()), "")

def _pick_url_from_item(item) -> str:
    # URL biasanya di .item-status-ip span[title]
    ip_span = item.locator('.item-status-ip span[title]')
    if ip_span.count() > 0:
        return (ip_span.first.get_attribute("title") or "").strip()
    # fallback: cari title yang berupa URL
    spans = item.locator('span[title]')
    count = spans.count()
    for i in range(count):
        t = (spans.nth(i).get_attribute("title") or "").strip()
        if t.lower().startswith(PROTO_PREFIXES):
            return t
    return ""

def _pick_status_text(item) -> str:
    # Baris status biasanya berisi <span class="ft-12 ...">Connected/Not Connected/Network Error
    spans = item.locator(".display-flex.align-items-center span.ft-12")
    c = spans.count()
    if c > 0:
        return (spans.nth(c - 1).text_content() or "").strip()
    return ""

def _normalize_status(s: str) -> str:
    if not s:
        return "unknown"
    low = s.lower()
    if "error" in low:
        return "error"
    if "not" in low and "connect" in low:
        return "not connected"
    if "connecting" in low:
        return "connecting"
    if "connected" in low:
        return "connected"
    return low

def read_sources_status(page: Page) -> List[Dict[str, str]]:
    # Pastikan panel Source sudah render
    page.wait_for_selector(LIST_SOURCE_ITEM, timeout=10_000)
    items = page.locator(LIST_SOURCE_ITEM)
    n = items.count()
    results: List[Dict[str, str]] = []
    for i in range(n):
        item = items.nth(i)
        name = _pick_name_from_item(item)
        url = _pick_url_from_item(item)
        status_label = _pick_status_text(item)
        results.append({
            "name": name or f"item_{i}",
            "url": url,
            "status": _normalize_status(status_label),
            "status_label": status_label,
        })
    return results
