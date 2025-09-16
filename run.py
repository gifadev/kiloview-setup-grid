# run.py
import argparse, yaml
from pathlib import Path

from core.browser import launch_browser
from core.auth import login, wait_for_dashboard
from core import utils

from core.actions.layouts import select_layout
from core.actions.sources import (
    list_sources,
    assign_source_to_grid,
    set_source_url,
)

def parse_assign_pairs(pairs):
    out = []
    for raw in pairs or []:
        if ":" not in raw:
            print(f"[WARN] arg --assign di-skip (format salah): '{raw}'")
            continue
        idx_str, name = raw.split(":", 1)
        try:
            idx = int(idx_str)
        except ValueError:
            print(f"[WARN] arg --assign di-skip (index bukan angka): '{raw}'")
            continue
        out.append((idx, name.strip()))
    return out


def parse_set_url_pairs(pairs):
    out = []
    for raw in pairs or []:
        if "=" not in raw:
            print(f"[WARN] arg --set-url di-skip (format salah): '{raw}'")
            continue
        name, url = raw.split("=", 1)
        name = name.strip()
        url = url.strip()
        if not name or not url:
            print(f"[WARN] arg --set-url di-skip (nama/url kosong): '{raw}'")
            continue
        out.append((name, url))
    return out


def run_scenario(
    scn: dict,
    headless: bool = True,
    record_video: bool = False,
    layout_cells: int | None = None,
    confirm_layout_shift: bool = False,
    assign_pairs: list[tuple[int, str]] | None = None,
    list_only: bool = False,
    set_url_pairs: list[tuple[str, str]] | None = None,
):
    pw, browser, context, page = launch_browser(headless=headless, record_video=record_video, out_dir=utils.OUT_DIR)
    try:
        base = scn["base_url"]
        creds = scn["login"]
        login(page, base, creds["username"], creds["password"])
        wait_for_dashboard(page)

        # (Opsional) pilih layout
        if layout_cells:
            select_layout(page, layout_cells, confirm=confirm_layout_shift)

        # (Baru) set URL-URL source lebih dulu (jika ada)
        for (name, url) in set_url_pairs or []:
            print(f"[INFO] set URL '{name}' -> {url}")
            set_source_url(page, name, url)

        # (Opsional) assign sumber ke grid
        for (idx, name) in assign_pairs or []:
            print(f"[INFO] place {name} -> grid {idx}")
            assign_source_to_grid(page, idx, name)

        # (Opsional) list sumber
        if list_only:
            data = list_sources(page)
            print(data)
            print("\n[LIST SOURCES]")
            for it in data:
                print(f"- {it['name']}: {it['status']} | {it['url']}")
            print("")

        # simpan storage state (biar sesi dipakai lagi)
        context.storage_state(path=str(utils.OUT_DIR / "storage_state.json"))

    finally:
        browser.close()
        pw.stop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="scenarios/login_only.yaml")
    ap.add_argument("--headed", action="store_true", help="jalankan dengan UI (non-headless)")
    ap.add_argument("--record-video", action="store_true")

    # Layout
    ap.add_argument("--layout-cells", type=int, help="jumlah cell grid (1=Single, 4=2x2, 9=3x3, 16=4x4, dst.)")
    ap.add_argument("--confirm-layout-shift", action="store_true", help="auto klik OK jika muncul peringatan layout shift")

    # Assign
    ap.add_argument("--assign", action="append", help='map source ke grid, format "N:NamaSource" (repeatable)')

    # List
    ap.add_argument("--list-sources", action="store_true")

    # Baru: edit URL stream
    ap.add_argument("--set-url", action="append", help='edit URL stream source, format "NamaSource=rtsp://..." (repeatable)')

    args = ap.parse_args()

    with open(args.scenario, "r", encoding="utf-8") as f:
        scn = yaml.safe_load(f)

    assign_pairs = parse_assign_pairs(args.assign)
    set_url_pairs = parse_set_url_pairs(args.set_url)

    run_scenario(
        scn,
        headless=not args.headed,
        record_video=args.record_video,
        layout_cells=args.layout_cells,
        confirm_layout_shift=args.confirm_layout_shift,
        assign_pairs=assign_pairs,
        list_only=args.list_sources,
        set_url_pairs=set_url_pairs,
    )
