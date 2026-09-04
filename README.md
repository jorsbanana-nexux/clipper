> [!WARNING]
> ## ⚠️ STATUS: TAHAP PENGEMBANGAN AKTIF — HARAP BERHATI-HATI
> Proyek ini **belum stabil dan masih dalam pengembangan aktif**. API, struktur
> folder, dan perilaku dapat berubah tanpa pemberitahuan. **Jangan gunakan di
> produksi** sebelum mencapai rilis `v1.0`. Baca [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md)
> untuk roadmap & status fitur terbaru.

---

# CLIPPER <span style="color:#ff5c1f">.</span>

**AI web clipper** — tempel link video, AI menganalisis momen viral, memotong hanya
bagian terbaik, lalu membingkai ulang ke **9:16** dengan **subtitle word-by-word**
(gaya MrBeast strict: 100% tanpa tanda baca, maks 2 baris di tengah layar,
bounce per kata 120%→95%→100%, hanya kata aktif yang menyala kuning) + **face tracking**, siap diunduh dan diunggah ke TikTok / Reels / Shorts.

> "Bukan sekadar clipper otonom yang kaku — tapi editor profesional."

---

## 🧠 Konsep Inti

Terbagi menjadi **2 mode**:

| Mode | Nama | Status | Deskripsi |
|------|------|--------|-----------|
| 1 | **Podcast** | 🟢 *in progress* | Tempel URL → AI temukan momen viral → potong segmen terpilih → clip 9:16 face-tracked + subtitle word-by-word |
| 2 | **Keyword** | 🔴 *coming soon* | 1 kata kunci → clipper (TTS + template) — **belum dikerjakan** |

---

## ⚙️ Cara Kerja (Mode 1 — Podcast)

```
tempel URL ──► ambil transkrip dari captions (0 MB audio) ──► GPT analisis momen viral
     ──► unduh HANYA segmen video terpilih ──► Whisper HANYA segmen audio terpilih
     ──► face-track & reframe 9:16 ──► subtitle word-by-word ──► efek ──► library unduh
```

> **Optimasi ringan (low-spec friendly):** transkrip diambil dari caption YouTube/auto-caption
> **tanpa mengunduh audio**. Whisper hanya dipakai untuk **segmen audio terpilih** (dapat
> word-timestamps akurat untuk subtitle). Fallback ke unduh audio penuh hanya bila video
> tidak punya caption sama sekali.

**Fitur utama:**
- **Analisis dulu, download kemudian** — AI membaca transkrip (dari caption, 0 MB audio),
  menemukan momen (mis. menit `01:20–02:34`), lalu hanya segmen video itu yang diunduh → hemat bandwith & waktu.
- **Face tracking nyata** (MediaPipe + OpenCV Haar fallback) — bingkai 9:16 mengikuti wajah pembicara.
- **Multi-speaker (v0.2)** — deteksi banyak wajah, split-screen duo (2 pembicara), dan speaker
  (crop kiri/kanan untuk 2 pembicara berdampingan), dan speaker
  diarization opsional (pyannote) untuk auto-decision single vs duo. Tanpa `HUGGINGFACE_TOKEN`
  otomatis fallback ke single-speaker (ringan).
- **Subtitle MrBeast strict** — teks 100% tanpa tanda baca, maks 2 baris di tengah layar, font Komika Axis tebal, stroke hitam tebal, bounce per kata 100→120→95→100%, HANYA kata yang sedang diucapkan menyala kuning lalu kembali putih.
- **Kualitas 720/1080** — format `bestvideo[height<=1080]`.
- **Efek viral** — kontras + saturasi + sharpen ringan.
- **Padding 1,5 detik** — tiap clip dipotong sedikit lebih lebar agar momen selalu utuh (anti-terpotong).
- **Auto-chunk 25 MiB** — audio panjang >25 MB otomatis dipecah agar lolos batas Whisper (podcast panjang aman).
- **Fase A hardening** — cut akurat, bundle font, verifikasi output, auto-detect bahasa, yt-dlp tangguh, cleanup. Checklist uji: [`docs/TESTING.md`](docs/TESTING.md).
- **Deteksi bahasa otomatis** — Whisper auto-detect semua bahasa.

---

## 📁 Struktur Proyek

```
clipper/
├── backend/                 # FastAPI (Python 3.11)
│   ├── app/
│   │   ├── main.py          # App entry + routing + CORS
│   │   ├── config.py        # Konfigurasi (env vars)
│   │   ├── models.py        # Pydantic models
│   │   ├── jobs.py          # Job manager + pipeline async
│   │   ├── downloader.py    # yt-dlp (captions, audio, segment ranges)
│   │   ├── transcriber.py   # Whisper word timestamps + auto-chunk 25 MiB
│   │   ├── analyzer.py      # GPT viral-moment detection
│   │   ├── diarization.py   # Speaker diarization (opsional, pyannote)
│   │   ├── layout.py        # Template single/duo + layout timeline
│   │   ├── compositor.py    # Dynamic switching + crossfade
│   │   ├── face_tracker.py  # MediaPipe face tracking + reframe
│   │   ├── subtitles.py     # ASS word-by-word
│   │   └── renderer.py      # ffmpeg clip + efek + thumbnail + verify
│   └── run.py               # Launcher
├── frontend/                # Next.js 15 (App Router)
│   └── app/page.tsx         # Paste URL → progress → library unduh
├── docs/
│   └── REQUIREMENTS.md      # Spesifikasi, arsitektur, roadmap
├── .env.example             # Template konfigurasi (salin ke .env)
└── requirements.txt         # Dependensi Python
```

---

## 🚀 Menjalankan Secara Lokal (manual step-by-step)

> `setup.py` **sudah dihapus**. Setup sekarang 100% manual — lebih jelas & mudah
> di-debug. Ikuti 4 langkah di bawah. Total ~5 menit.

### Langkah 1 — Prasyarat

- **Python 3.11** (cek: `py -0` di Windows / `python3 --version` di macOS/Linux).
- **ffmpeg** di PATH (cek: `ffmpeg -version`).
- **Node.js 18+** & **npm** (cek: `node -v`).
- **Mode GRATIS (tanpa modal):** `GEMINI_API_KEY` dari [aistudio.google.com/apikey](https://aistudio.google.com/apikey) — gratis, tanpa kartu. Transkripsi pakai **faster-whisper lokal** (0 rupiah).
- *(Alternatif berbayar)* **`OPENAI_API_KEY`** dari [platform.openai.com/api-keys](https://platform.openai.com/api-keys) — hanya jika ingin pakai OpenAI.
- *(Opsional)* **`HUGGINGFACE_TOKEN`** dari [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) — hanya untuk multi-speaker.

> 💡 **Rekomendasi**: Clipper bisa dijalankan **100% gratis** — transkripsi di PC
> Anda (faster-whisper) + analisis via Gemini (free tier). Tidak perlu OpenAI sama sekali.

### Langkah 2 — Setup `.env` (di mana key ditaruh)

Buat file `.env` di **root project** (salin dari template), lalu isi kunci:

```bash
# dari root project
copy .env.example .env      # Windows
cp .env.example .env        # macOS / Linux
```

Buka `.env` dan isi. **Mode gratis** (disarankan): biarkan `OPENAI_API_KEY=` kosong,
isi `GEMINI_API_KEY=...` (dari aistudio.google.com/apikey).

```ini
# MODE GRATIS (transkripsi lokal + Gemini)
WHISPER_BACKEND=local
WHISPER_MODEL_SIZE=small      # pakai 'tiny'/'base' untuk PC low-RAM
ANALYSIS_BACKEND=gemini
GEMINI_API_KEY=AIza...        # gratis, dari aistudio.google.com/apikey

# ALTERNATIF: mode OpenAI (berbayar)
# ANALYSIS_BACKEND=openai
# WHISPER_BACKEND=openai
# OPENAI_API_KEY=sk-...

# OPSIONAL (kosongkan kalau tidak pakai multi-speaker)
HUGGINGFACE_TOKEN=
CLIPPER_MULTI_SPEAKER=0
```

> Jika **tidak** memakai multi-speaker, biarkan `HUGGINGFACE_TOKEN=` kosong dan
> `CLIPPER_MULTI_SPEAKER=0` — Clipper otomatis berjalan single-speaker (ringan).
> Jika memakai, isi token lalu set `CLIPPER_MULTI_SPEAKER=1`.

### Langkah 3 — Install & jalankan backend

```bash
# Windows
py -3.11 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install -r requirements-free.txt   # mode gratis: faster-whisper + Gemini
.venv\Scripts\python backend\run.py

# macOS / Linux
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python backend/run.py
```

→ Backend di **http://localhost:8000** · cek status key: `GET /health`.

### Langkah 4 — Install & jalankan frontend

```bash
cd frontend
npm install
BACKEND_URL=http://localhost:8000 npm run dev   # macOS/Linux
set BACKEND_URL=http://localhost:8000 && npm run dev   # Windows
# → buka http://localhost:3000
```

> **Ganti key nanti?** Cukup edit `.env` lalu restart backend. Tidak perlu re-install deps.

---

## 🔌 API

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| `POST` | `/jobs` | Buat job: `{url, max_clips, mode}` |
| `GET`  | `/jobs/{id}` | Status job + progress + daftar clip |
| `GET`  | `/health` | Health check |
| `GET`  | `/clips/...` | File clip & thumbnail (static) |

---

## 📌 Status & Roadmap

Roadmap detail & prioritas lengkap (untuk agent masa depan) ada di
[`docs/ROADMAP.md`](docs/ROADMAP.md). Ringkas fase:

| Fase | Fokus | Status |
|------|-------|--------|
| A | Akurasi & hardening dasar (uji end-to-end, frame-accurate, font, bahasa) | ✅ v0.1.x (A1–A7; A0 = checklist docs/TESTING.md) |
| B | Multi-speaker split-screen + dynamic speaker switching | ✅ v0.2 (diarization, multi-face, split-screen, dynamic switch) |
| C | Subtitle & efek profesional | ⬜ P1 |
| D | Platform (TikTok/IG/X) & pengunduhan | ⬜ P1 |
| E | State, storage, observability | ⬜ P1 |
| F | Frontend UX | ⬜ P1 |
| G | Deployment, testing, keamanan | ⬜ P2 |

**Selesai:** v0.1 pipeline + frontend; **v0.2 multi-speaker** (diarization opsional, multi-face,
split-screen duo, layout engine).

> Panduan lengkap + daftar gap ya, mulai dari `docs/ROADMAP.md` §3 (kekurangan) & §4 (rencana).
