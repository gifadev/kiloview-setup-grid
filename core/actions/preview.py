from typing import Iterable, Tuple, List
from playwright.sync_api import Page, Error
from ..ui_selectors import (
    PREVIEW_ITEM_BY_INDEX,
    PREVIEW_VIDEO_BOX_IN,
    PREVIEW_STATUS_CONNECTED_IN,
    PREVIEW_LOADING_IN,
    PREVIEW_DELETE_ICON_IN,
    SOURCE_ITEM_BY_TITLE,
    SOURCE_CONNECTED_ITEMS,
)

def clear_preview_slot(page: Page, slot_idx: int, timeout_ms: int = 3_000) -> None:
    slot = page.locator(PREVIEW_ITEM_BY_INDEX(slot_idx))
    try:
        slot.hover(timeout=timeout_ms)
    except Error:
        pass
    delete_icon = page.locator(PREVIEW_DELETE_ICON_IN(slot_idx))
    try:
        if delete_icon.is_visible():
            delete_icon.click(timeout=timeout_ms)
            # beri jeda singkat biar UI update
            page.wait_for_timeout(300)
    except Error:
        # aman diabaikan kalau tidak ada icon/ gagal klik
        pass

def wait_preview_ready(page: Page, slot_idx: int, timeout_ms: int = 8_000) -> None:
    """Tunggu loading hilang atau status jadi Connected di slot preview."""
    # 1) loading overlay hilang (kalau ada)
    try:
        page.locator(PREVIEW_LOADING_IN(slot_idx)).wait_for(state="detached", timeout=timeout_ms)
    except Error:
        # kalau elemen loading tidak ada, lanjut
        pass
    # 2) status 'Connected' (jika tersedia di UI ini)
    try:
        page.locator(PREVIEW_STATUS_CONNECTED_IN(slot_idx)).wait_for(timeout=timeout_ms)
    except Error:
        # beberapa sumber tidak pernah menampilkan status hijau, cukup lewat
        pass

def drag_source_to_preview(
    page: Page,
    source_title: str,
    slot_idx: int,
    clear_before: bool = False,
    timeout_ms: int = 10_000,
) -> None:
    """Drag & drop 1 sumber (berdasarkan title) ke slot preview ke-N."""
    if clear_before:
        clear_preview_slot(page, slot_idx)

    src = page.locator(SOURCE_ITEM_BY_TITLE(source_title)).first
    tgt = page.locator(PREVIEW_VIDEO_BOX_IN(slot_idx)).first

    # Validasi ringan biar errornya jelas
    if src.count() == 0:
        raise RuntimeError(f'Source dengan title "{source_title}" tidak ditemukan.')
    if page.locator(PREVIEW_ITEM_BY_INDEX(slot_idx)).count() == 0:
        raise RuntimeError(f"Preview slot ke-{slot_idx} tidak ditemukan.")

    src.drag_to(tgt, timeout=timeout_ms)
    wait_preview_ready(page, slot_idx, timeout_ms=timeout_ms)

def fill_preview_auto(
    page: Page,
    count: int,
    clear_before: bool = False,
    timeout_ms: int = 10_000,
) -> int:
    """
    Isi N slot pertama dengan sumber yang statusnya 'Connected' secara urut dari atas.
    Return: berapa slot yang berhasil terisi.
    """
    srcs = page.locator(SOURCE_CONNECTED_ITEMS)
    try:
        total = srcs.count()
    except Error:
        total = 0

    filled = 0
    for i in range(min(count, total)):
        slot_idx = i + 1
        if clear_before:
            clear_preview_slot(page, slot_idx)

        src = srcs.nth(i)
        tgt = page.locator(PREVIEW_VIDEO_BOX_IN(slot_idx)).first

        # drag
        src.drag_to(tgt, timeout=timeout_ms)
        wait_preview_ready(page, slot_idx, timeout_ms=timeout_ms)
        filled += 1
    return filled

def apply_preview_map(
    page: Page,
    mapping: Iterable[Tuple[str, int]],
    clear_before: bool = False,
    timeout_ms: int = 10_000,
) -> None:
    """
    mapping: iterable pasangan (source_title, slot_idx)
    """
    for title, slot in mapping:
        drag_source_to_preview(
            page,
            source_title=title,
            slot_idx=slot,
            clear_before=clear_before,
            timeout_ms=timeout_ms,
        )
