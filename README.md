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
(gaya Alex Hormozi) + **face tracking**, siap diunduh dan diunggah ke TikTok / Reels / Shorts.

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
- **Subtitle word-by-word** — font tebal (Montserrat/Bebas Neue), highlight per kata, margin aman.
- **Kualitas 720/1080** — format `bestvideo[height<=1080]`.
- **Efek viral** — kontras + saturasi + sharpen ringan.
- **Padding 1,5 detik** — tiap clip dipotong sedikit lebih lebar agar momen selalu utuh (anti-terpotong).
- **Auto-chunk 25 MiB** — audio panjang >25 MB otomatis dipecah agar lolos batas Whisper (podcast panjang aman).
- **Deteksi bahasa otomatis** — Whisper auto-detect semua bahasa.

---

## 📁 Struktur Proyek

```
clipper/
├── backend/                 # FastAPI (Python 3.11)
│   ├── app/
│   │   ├── main.py          # App entry + routing
│   │   ├── config.py        # Konfigurasi (env vars)
│   │   ├── models.py        # Pydantic models
│   │   ├── jobs.py          # Job manager + pipeline async
│   │   ├── downloader.py    # yt-dlp (audio + segment ranges)
│   │   ├── transcriber.py   # Whisper word timestamps
│   │   ├── analyzer.py      # GPT viral-moment detection
│   │   ├── face_tracker.py  # MediaPipe face tracking + reframe
│   │   ├── subtitles.py     # ASS word-by-word
│   │   └── renderer.py      # ffmpeg clip + efek + thumbnail
│   └── run.py               # Launcher
├── frontend/                # Next.js 15 (App Router)
│   └── app/page.tsx         # Paste URL → progress → library unduh
├── docs/
│   └── REQUIREMENTS.md      # Spesifikasi, arsitektur, roadmap
└── requirements.txt         # Dependensi Python
```

---

## 🚀 Menjalankan Secara Lokal

### Prasyarat
- **Python 3.11** dan **ffmpeg** terpasang (`ffmpeg -version`).
- **Node.js 18+** untuk frontend.
- **`OPENAI_API_KEY`** (untuk Whisper + GPT analisis).

### 1. Backend

```bash
cd clipper
pip install -r requirements.txt
export OPENAI_API_KEY="sk-..."
python backend/run.py
# → http://localhost:8000  (health: /health)
```

### 2. Frontend

```bash
cd clipper/frontend
npm install
BACKEND_URL=http://localhost:8000 npm run dev
# → http://localhost:3000
```

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
| A | Akurasi & hardening dasar (uji end-to-end, frame-accurate, font, bahasa) | ⬜ P0 |
| B | Multi-speaker split-screen + dynamic speaker switching | ✅ v0.2 (diarization, multi-face, split-screen, dynamic switch) |
| C | Subtitle & efek profesional | ⬜ P1 |
| D | Platform (TikTok/IG/X) & pengunduhan | ⬜ P1 |
| E | State, storage, observability | ⬜ P1 |
| F | Frontend UX | ⬜ P1 |
| G | Deployment, testing, keamanan | ⬜ P2 |

**Selesai:** v0.1 pipeline + frontend; **v0.2 multi-speaker** (diarization opsional, multi-face,
split-screen duo, layout engine).

> Panduan lengkap + daftar gap ya, mulai dari `docs/ROADMAP.md` §3 (kekurangan) & §4 (rencana).
