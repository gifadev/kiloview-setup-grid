from playwright.sync_api import Page, Error
from ..ui_selectors import (
    LAYOUT_DROPDOWN_INPUT,
    LAYOUT_OPTION_ROW,
    LAYOUT_DIALOG,
    LAYOUT_CONFIRM_OK,
    GRID_CELL,
)

def _cells_to_title(cells: int) -> str:
    mapping = {1: "Single", 4: "2x2", 9: "3x3", 16: "4x4"}
    if cells in mapping:
        return mapping[cells]
    raise ValueError(f"layout cells {cells} tidak dikenali. Pakai 1/4/9/16.")

def select_layout(page: Page, cells: int, auto_confirm: bool = False, timeout_ms: int = 8000):
    title = _cells_to_title(cells)

    # buka dropdown
    dd = page.locator(LAYOUT_DROPDOWN_INPUT).first
    dd.wait_for(state="visible", timeout=timeout_ms)
    dd.click()

    # pilih item berdasarkan teks judul
    opt = page.locator(LAYOUT_OPTION_ROW).filter(has_text=title).first
    opt.wait_for(state="visible", timeout=timeout_ms)
    opt.click()

    # konfirmasi dialog jika muncul
    if auto_confirm:
        try:
            page.wait_for_selector(LAYOUT_DIALOG, timeout=1500)
            page.locator(LAYOUT_CONFIRM_OK).click()
        except Error:
            pass
    else:
        pass

    try:
        page.wait_for_function(
            "(cfg) => document.querySelectorAll(cfg.sel).length === cfg.expected",
            arg={"sel": GRID_CELL, "expected": cells},
            timeout=5000,
        )
    except Error:
        pass

def confirm_layout_shift(page: Page, timeout_ms: int = 3000) -> None:
    try:
        # modal wrapper Element-UI
        page.wait_for_selector('.el-message-box__wrapper[aria-modal="true"]',
                               state='visible', timeout=timeout_ms)
        ok_btn = page.locator('.el-message-box__btns .el-button--primary')
        if ok_btn.count() > 0:
            ok_btn.first.click()
        else:
            page.get_by_role("button", name="OK").click()
        # tunggu modal tertutup
        page.wait_for_selector('.el-message-box__wrapper', state='detached',
                               timeout=timeout_ms)
    except Error:
        pass