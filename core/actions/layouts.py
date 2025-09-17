# core/actions/layouts.py
from __future__ import annotations
from playwright.sync_api import Page, Error

# --- Selectors yang stabil dari DOM yang kamu kirim ---
SEL_LAYOUT_SELECT = ".layout-setting-box .el-select"                  # tombol dropdown
SEL_LAYOUT_DROPDOWN = ".layout-tool-select"                           # container dropdown
SEL_LAYOUT_OPTION = ".layout-tool-select .layout-select-option"       # setiap item pilihan

# Modal konfirmasi "Layout shift will lose unsaved data..."
SEL_MODAL_WRAPPER = "div.el-message-box__wrapper"
SEL_MODAL_OK = f"{SEL_MODAL_WRAPPER} .el-button--primary"             # tombol OK
SEL_MODAL_CANCEL = f"{SEL_MODAL_WRAPPER} .el-button--default"         # tombol Cancel

# Grid item (untuk nunggu perubahan layout selesai)
SEL_GRID_ITEM = ".layout-grid-content .grid-list-item"


def _maybe_handle_layout_shift_modal(page: Page, confirm: bool = True, timeout_ms: int = 1500) -> None:
    """
    Jika popup muncul, klik OK (confirm=True) atau Cancel (confirm=False).
    Jika tidak muncul, diabaikan.
    """
    try:
        modal = page.locator(SEL_MODAL_WRAPPER).filter(
            has_text="Layout shift will lose unsaved data"
        )
        modal.wait_for(state="visible", timeout=timeout_ms)
        if confirm:
            page.locator(SEL_MODAL_OK).click()
        else:
            # biasanya tombol Cancel adalah .el-button--default pertama
            page.locator(SEL_MODAL_CANCEL).first.click()
    except Error:
        # tidak ada modal — aman
        pass


def select_layout(page: Page, cells: int, confirm: bool = True, timeout_ms: int = 10_000) -> None:
    """
    Pilih layout berdasarkan jumlah cell: 1 (Single), 4 (2x2), 9 (3x3), 16 (4x4), ...
    Akan otomatis meng-OK popup layout-shift jika 'confirm=True'.
    """
    label_map = {
        1:  "Single",
        2:  "PIP",   
        4:  "2x2",
        9:  "3x3",
        16: "4x4",
    }
    label = label_map.get(cells)
    if label is None:
        raise ValueError(f"cells '{cells}' tidak didukung. Pilihan: {sorted(label_map.keys())}")

    # Buka dropdown
    page.locator(SEL_LAYOUT_SELECT).click()
    page.locator(SEL_LAYOUT_DROPDOWN).wait_for(state="visible", timeout=timeout_ms)

    # Klik opsi sesuai label
    option = page.locator(SEL_LAYOUT_OPTION).filter(has_text=label).first
    if option.count() == 0:
        raise RuntimeError(f"Layout '{label}' tidak ditemukan di dropdown")
    option.click()

    # Tangani modal konfirmasi jika muncul
    _maybe_handle_layout_shift_modal(page, confirm=confirm, timeout_ms=1500)

    # Tunggu grid terbentuk sesuai jumlah cell (best effort)
    try:
        # pastikan minimal index ke-(cells-1) sudah ada/visible
        page.locator(SEL_GRID_ITEM).nth(cells - 1).wait_for(state="visible", timeout=timeout_ms)
    except Error:
        # kadang animasi cepat; jika gagal tunggu, tetap lanjut
        pass
