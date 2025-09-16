# Kiloview Playwright Automation

Automasi end‑to‑end untuk web UI **Kiloview D350** menggunakan **Playwright (Python)**. Skrip ini meng-handle login, memilih layout grid, menempatkan (assign) sumber video ke grid, melihat status setiap source, dan **mengedit URL stream** via dialog Settings.

---

## Prasyarat

* Python 3.10+ (disarankan 3.11/3.12)
* Playwright & browser binaries
* OS: macOS / Linux / Windows

## Instalasi

```bash
python3 -m venv myenv
source myenv/bin/activate            # Windows: myenv\Scripts\activate
pip install -r requirements.txt      # pastikan berisi playwright==<versi>
playwright install chromium
```

> Catatan: Proyek ini menjalankan **Chromium** (lihat `core/browser.py`).

## Struktur Proyek (ringkas)

```
kiloview/
├─ run.py
├─ scenarios/
│  └─ login_only.yaml
└─ core/
   ├─ browser.py
   ├─ auth.py
   ├─ utils.py
   └─ actions/
      ├─ layouts.py
      └─ sources.py
```

## Konfigurasi Skenario

`scenarios/login_only.yaml`:

```yaml
base_url: "http://172.15.4.211"
login:
  username: "admin"
  password: "admin"
```

---

## Cara Menjalankan (contoh)

**Dengan UI (headed), pilih 2x2, auto‑confirm peringatan layout shift, dan assign 4 grid:**

```bash
python3 run.py --headed --layout-cells 4 --confirm-layout-shift \
  --assign 1:depan --assign 3:depan --assign 4:depan --assign 2:depan
```

**Headless (tanpa UI), pilih 2x2 dan assign:**

```bash
python3 run.py --layout-cells 4 --confirm-layout-shift \
  --assign 1:depan --assign 3:depan --assign 4:depan --assign 2:depan
```

**Assign saja (tanpa ubah layout):**

```bash
python3 run.py --assign 1:depan --assign 3:depan --assign 4:depan --assign 2:depan
```

**Lihat daftar sumber (nama, status, URL):**

```bash
python3 run.py --headed --list-sources
```

**Baru — Edit URL stream satu atau beberapa source:**

```bash
# set satu URL
python3 run.py --headed --set-url "depan=rtsp://172.15.1.155:554/stream/ch1"

# set beberapa URL sekaligus
python3 run.py --headed \
  --set-url "depan=rtsp://172.15.1.155:554/stream/ch1" \
  --set-url "drone=rtsp://192.168.144.252:8554/stream_2"

# setelah set URL, assign ke grid
python3 run.py --headed --layout-cells 4 --confirm-layout-shift \
  --set-url "drone=rtsp://192.168.144.252:8554/stream_2" \
  --assign 1:depan --assign 2:drone
```

> **Penting:** gunakan tanda kutip **lurus** `"..."`, **jangan** kutip miring `“…”`.

---

## Opsi CLI

* `--scenario PATH` — file YAML skenario (default: `scenarios/login_only.yaml`).
* `--headed` — jalankan dengan UI (default headless).
* `--record-video` — rekam video (lihat `core/browser.py`).
* `--layout-cells N` — pilih preset layout:

  * `1` = Single, `4` = 2x2, `9` = 3x3, `16` = 4x4, dst.
* `--confirm-layout-shift` — otomatis klik **OK** bila muncul popup *“Layout shift will lose unsaved data…”*.
* `--assign N:NamaSource` — tempatkan source ke grid ke‑N (repeatable).
* `--list-sources` — tampilkan daftar sumber (nama, status, URL) di terminal.
* `--set-url NamaSource=URL` — buka dialog Settings ⚙️ di source tsb., isi URL, dan **Save** (repeatable).

> Sumber yang di‑assign harus sudah ada di panel **Source** (kanan). Mekanisme assign mengikuti perilaku UI: **aktifkan** grid target, lalu **double‑click** source pada daftar.

---

## Perilaku & Selektor UI (intisari)

* **Grid cell aktif**: `.layout-grid-content .grid-list-item.active-item`
* **Item source**: `div.discovery-list-item` (nama di `span.over-ellipsis`)
* **Ikon Settings** (gear) pada item: `.icon-setting i.icon-shezhi`
* **Dialog (Element‑UI)**: `.el-dialog__wrapper` / `.el-message-box__wrapper`
* **Tombol dialog**: `Save` / `OK` / `Confirm` / `确定` / `保存` (tombol primary)

Jika UI firmware berbeda, perbarui selector di `core/actions/sources.py` sesuai HTML terbaru.

---

## Output & Penyimpanan Sesi

* Folder `out/` dibuat otomatis.
* **Storage state** Playwright disimpan ke `out/storage_state.json` agar sesi login bisa dipakai ulang.

---

## Troubleshooting

* **Smart quotes**: Pesan seperti `[WARN] arg --assign di-skip (format salah)` sering terjadi bila memakai kutip miring `“3:drone”`. Ganti dengan kutip lurus: `"3:drone"`.
* **`ERR_ABORTED / frame was detached` saat `goto`**: UI SPA kadang redirect cepat. Kode sudah retry & menunggu field username. Pastikan alamat `base_url` benar dan perangkat online.
* **`Page.wait_for_function()` argumen**: Pastikan versi kode terbaru (sudah menggunakan `arg=...`).
* **Selector tidak ketemu di dialog Edit URL**: Kirimkan HTML dialog yang tampil; sesuaikan fungsi `_find_url_input_in_dialog()` atau `_click_dialog_primary()`.

---

## Kustomisasi Lanjutan

* Tambah preset layout lain di `actions/layouts.py` bila perangkat punya variasi baru.
* Mapping assign dari file (mis. YAML) dapat ditambahkan: baca daftar pasangan lalu panggil `assign_source_to_grid()` berurutan.
* Validasi status source sebelum assign (mis. hanya `Connected`) bisa ditambahkan dengan memanfaatkan `list_sources()`.

---

## Catatan Rilis (terakhir)

* **Tambah**: `--set-url` untuk edit URL stream per‑source via dialog Settings ⚙️.
* **Perbaikan**: kompatibilitas `wait_for_function` (pakai `arg=`), helper pilih layout, dan listing status source.

---

## Lisensi

Internal / project‑specific. Sesuaikan kebutuhan organisasi Anda.

## REST API — Contoh Penggunaan Lengkap

**Base URL**: `http://localhost:8000`

> Semua endpoint tidak butuh autentikasi. Gunakan header `Content-Type: application/json` untuk request `POST`.

---

### 1) `GET /health`

Cek server & konfigurasi dasar.

**cURL**

```bash
curl -s http://localhost:8000/health
```

**Respons (contoh)**

```json
{
  "ok": true,
  "base_url": "http://172.15.4.211"
}
```

---

### 2) `GET /sources`

Ambil daftar sumber video beserta status koneksi.

**cURL**

```bash
curl -s http://localhost:8000/sources
```

**Respons (contoh)**

```json
[
  {"name":"depan","status":"Connected","url":"rtsp://172.15.1.155:554/stream/ch1","stream_id":"c83f1a50ea1a5dc4dd1e77b08b1554f5"},
  {"name":"drone","status":"Network Error","url":"rtsp://192.168.144.252:8554/stream_2","stream_id":"bbdc4cadf88cbac48f7f850f44a9bed5"}
]
```

**Python (requests)**

```python
import requests
print(requests.get("http://localhost:8000/sources").json())
```

---

### 3) `POST /layout`

Pilih layout grid (1=Single, 4=2x2, 9=3x3, 16=4x4, dst.).

> `confirm_shift` **default = true** → popup “Layout shift will lose unsaved data…” akan otomatis di-OK. Kirim `false` jika tidak ingin auto-OK.

**cURL**

```bash
# Auto-OK (default)
curl -s -X POST http://localhost:8000/layout \
  -H 'Content-Type: application/json' \
  -d '{"cells": 4}'

# Tanpa auto-OK\ ncurl -s -X POST http://localhost:8000/layout \
  -H 'Content-Type: application/json' \
  -d '{"cells": 9, "confirm_shift": false}'
```

**Respons (contoh)**

```json
{"ok": true, "cells": 4}
```

---

### 4) `POST /assign`

Tempatkan satu sumber ke sel grid tertentu (index **1-based**).

**cURL**

```bash
curl -s -X POST http://localhost:8000/assign \
  -H 'Content-Type: application/json' \
  -d '{"grid": 1, "name": "depan"}'
```

**Respons (contoh)**

```json
{"ok": true, "grid": 1, "name": "depan"}
```

---

### 5) `POST /assign/bulk`

Tempatkan beberapa sumber sekaligus.

**cURL**

```bash
curl -s -X POST http://localhost:8000/assign/bulk \
  -H 'Content-Type: application/json' \
  -d '{
        "assigns": [
          {"grid": 1, "name": "depan"},
          {"grid": 2, "name": "drone"},
          {"grid": 3, "name": "depan"}
        ]
      }'
```

**Respons (contoh)**

```json
{"ok": true, "count": 3}
```

---

### 6) `POST /set-url`

Edit URL stream untuk satu/lebih sumber.

**cURL**

```bash
curl -s -X POST http://localhost:8000/set-url \
  -H 'Content-Type: application/json' \
  -d '{
        "items": [
          {"name": "depan", "url": "rtsp://172.15.1.155:554/stream/ch1"},
          {"name": "drone", "url": "rtsp://192.168.144.252:8554/stream_2"}
        ]
      }'
```

**Respons (contoh)**

```json
{"ok": true, "count": 2}
```

---

### 7) `POST /run`

Menjalankan beberapa langkah sekaligus: **(opsional)** set layout, set URL, dan assign; lalu mengembalikan snapshot sources terbaru.

**cURL**

```bash
curl -s -X POST http://localhost:8000/run \
  -H 'Content-Type: application/json' \
  -d '{
        "layout_cells": 4,
        "set_urls": [
          {"name": "depan", "url": "rtsp://172.15.1.155:554/stream/ch1"}
        ],
        "assigns": [
          {"grid": 1, "name": "depan"},
          {"grid": 2, "name": "drone"}
        ]
      }'
```

**Respons (contoh)**

```json
{
  "layout_cells": 4,
  "set_urls": 1,
  "assigns": 2,
  "sources": [
    {"name":"depan","status":"Connected","url":"rtsp://172.15.1.155:554/stream/ch1","stream_id":"c83f1a50..."},
    {"name":"drone","status":"Network Error","url":"rtsp://192.168.144.252:8554/stream_2","stream_id":"bbdc4cad..."}
  ]
}
```

---

### Error Handling

Jika ada kegagalan (mis. perangkat tidak bisa diakses, timeout, selektor UI berubah), API akan mengembalikan HTTP 5xx dengan bentuk:

```json
{ "detail": "Failed to <aksi>: <pesan error>" }
```

**Contoh**

```json
{
  "detail": "Failed to list sources: Page.goto: Timeout 60000ms exceeded.
Call log:
..."
}
```

**Tips**

* Pastikan perangkat `base_url` dapat diakses dari mesin API.
* RTSP/RTMP URL valid dan dapat dijangkau oleh perangkat.
* Nama sumber (`name`) harus sama persis seperti yang terlihat di `/sources`.
