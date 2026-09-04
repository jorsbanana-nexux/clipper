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
- **Multi-speaker (v0.2 + fix kritikal v0.3.1)** — split-screen duo atas-bawah
  aktif OTOMATIS saat `CLIPPER_MULTI_SPEAKER=1` + `HUGGINGFACE_TOKEN`:
  layar terbelah 2,5 detik SEBELUM pembicara ke-2 bicara (anti-telat), menutup
  saat monolog panjang, buka lagi saat ada giliran bicara, dan jendela yang
  ternyata cuma 1 wajah otomatis jadi solo. Tanpa token → SOLO crop-follow
  mulus (tidak pernah kacau). *(v0.3.1 memperbaiki bug di mana duo tidak
  pernah aktif pada percakapan bergantian normal.)*
- **Subtitle MrBeast strict** — teks 100% tanpa tanda baca, maks 2 baris di tengah layar, font Komika Axis tebal, stroke hitam tebal, bounce per kata 100→120→95→100%, HANYA kata yang sedang diucapkan menyala kuning lalu kembali putih.
- **Kualitas 720/1080** — format `bestvideo[height<=1080]`.
- **Efek viral** — kontras + saturasi + sharpen ringan.
- **Padding 1,5 detik** — tiap clip dipotong sedikit lebih lebar agar momen selalu utuh (anti-terpotong).
- **Auto-chunk 25 MiB** — audio panjang >25 MB otomatis dipecah agar lolos batas Whisper (podcast panjang aman).
- **Fase A hardening** — cut akurat, bundle font, verifikasi output, auto-detect bahasa, yt-dlp tangguh, cleanup. Checklist uji: [`docs/TESTING.md`](docs/TESTING.md).
- **Deteksi bahasa otomatis** — Whisper auto-detect semua bahasa.

**Baru di v0.3 — hasil riset semua platform clipper (Opus/Vizard/Klap/Munch):**
- **Human steer** — beri topik/instruksi SEBELUM render ("AI-nya memilih bagian
  membosankan" = keluhan #1 semua platform; di sini kamu punya suara).
- **Skor viral 5 dimensi** — hook/payoff/emosi/quotable/energi, transparan di UI,
  bukan sekadar angka 1-10 misterius. Plus **quality gate** (skor < 4 dibuang)
  dan **rantai fallback model Gemini gratis** (analisis tak pernah mati
  karena satu model sibuk/dipensiunkan).
- **Caption + hashtag siap posting** — dibuat dalam BAHASA KONTEN (khususnya
  Indonesia — tidak ada platform global yang melakukan ini), tinggal copy.
- **4 preset subtitle** — MrBeast (pop kuning), Hormozi (besar hijau),
  Karaoke (isi progresif), Minimal — atau tanpa subtitle. Per job, dari UI.
- **Export multi-aspek** — 9:16 native, plus 1:1 & 4:5 (face-safe, blur-pad).
- **Anti-klip-repetitif** — prompt melarang momen duplikat; lebih baik 5 clip
  bagus & berbeda daripada 8 clip sama rasa.
- **Download semua (ZIP)** + `metadata.json` (caption/hashtag/skor per clip).
- **Smoke test offline** — `python tests/smoke_render.py` membuktikan rantai
  render bekerja end-to-end TANPA internet & TANPA API key (gap #1 ROADMAP).

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
├── tests/
│   └── smoke_render.py     # Uji rantai render end-to-end (offline, tanpa API key)
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
| `POST` | `/jobs` | Buat job: `{url, max_clips, mode, keywords, instruction, subtitle_style, aspect}` |
| `GET`  | `/jobs/{id}` | Status job + progress + daftar clip (skor 5 dimensi + caption + hashtag) |
| `GET`  | `/jobs/{id}/zip` | Download SEMUA clip dalam 1 ZIP + metadata.json |
| `GET`  | `/styles` | Daftar preset subtitle yang tersedia |
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
