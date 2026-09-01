# REQUIREMENTS — Clipper

> Dokumen ini adalah **sumber kebenaran (source of truth)** untuk spesifikasi,
> arsitektur, dan roadmap. **Wajib diperbarui setiap ada tindakan/update/upgrade.**

**Terakhir diperbarui:** 2026-09-01

---

## 1. Visi Produk

Web clipper versi keluaran terbaru yang melampaui platform clipper tingkat atas.
Mesin AI serba guna untuk mengubah video panjang (podcast) menjadi klip pendek
**viral** yang siap diunggah ke TikTok / Reels / Shorts.

Prinsip: **"editor profesional, bukan clipper otonom yang kaku."**

---

## 2. Mode

| Mode | Nama | Prioritas | Status |
|------|------|-----------|--------|
| 1 | Podcast | 🔥 Fokus sekarang | 🟢 in progress |
| 2 | Keyword (1 kata kunci → clipper) | Menyusul | 🔴 not started |

**Mode 2 TIDAK dikerjakan dulu.** Fokus penuh ke Mode 1.

---

## 3. Mode 1 — Spesifikasi Detail

### 3.1 Sumber video
- YouTube, TikTok, Instagram, dan platform lain (via `yt-dlp`).
- v1 fokus **YouTube** (paling stabil). Platform lain diuji bertahap.

### 3.2 Alur Pipeline

| # | Tahap | Komponen | Output |
|---|-------|----------|--------|
| 1 | Unduh audio + metadata | `downloader.py` | `audio.mp3`, info video |
| 2 | Transkripsi word-level | `transcriber.py` (Whisper) | kata + `start`/`end` |
| 3 | Analisis momen viral | `analyzer.py` (GPT) | 6–10 `ViralMoment` |
| 4 | Unduh segmen terpilih | `downloader.download_segment` | video rentang saja |
| 5 | Face track + reframe 9:16 | `face_tracker.py` | `vertical.mp4` |
| 6 | Subtitle word-by-word | `subtitles.py` + `renderer.py` | `final.mp4` |
| 7 | Library unduh | `jobs.py` + frontend | daftar clip |

### 3.3 Subtitle (gaya profesional)

| Aspek | Spesifikasi |
|-------|-------------|
| Font | **Tebal sans-serif** — Montserrat / Montserrat Black / Bebas Neue |
| Animasi | **Word-by-word** highlight (`\k` karaoke, gaya Alex Hormozi) |
| Posisi | Tengah-bawah, margin aman (tidak tertutup tombol like/comment) |
| Akurasi | Timestamp kata nyata dari Whisper — tidak melenceng |
| Konsistensi | Satu template baku (font, warna, margin) |

### 3.4 Face Tracking & Smart Layout

| Fitur | Status |
|-------|--------|
| Auto-reframe 9:16 + pelacakan wajah aktif (ikuti pembicara) | ✅ v0.1 (single-speaker) |
| Auto dual-speaker saat wawancara multi-orang | ⬜ v0.2 |
| Dynamic speaker switching (webcam ↔ screen share) | ⬜ v0.2 |

### 3.5 Kualitas video
- 720p/1080p, **no blur** (`bestvideo[height<=1080]`).
- Fallback ke format terbaik yang tersedia.

### 3.6 Efek
- Kontras +1.06, saturasi +1.15, sharpen ringan (`unsharp`).
- Daftar efek diperluas di v0.3 (zoom punch, glow, dll).

---

## 4. Arsitektur Teknis

### 4.1 Diagram komponen

```
┌──────────────┐    HTTP/rewrite     ┌──────────────────────────┐
│  Frontend    │ ──────────────────► │  Backend (FastAPI)       │
│  Next.js 15  │   /api/*  /clips/*  │                          │
└──────────────┘                     │  ┌────────────────────┐  │
                                     │  │ JobManager (async) │  │
                                     │  └────────────────────┘  │
                                     │  downloader/transcriber  │
                                     │  analyzer/face_tracker   │
                                     │  subtitles/renderer      │
                                     │  └──► ffmpeg + yt-dlp    │
                                     └──────────┬───────────────┘
                                                │
                                    ┌───────────▼───────────┐
                                    │ OpenAI (Whisper + GPT) │
                                    └───────────────────────┘
```

### 4.2 Stack

| Lapisan | Teknologi |
|---------|-----------|
| Backend | Python 3.11, FastAPI, uvicorn |
| Download | yt-dlp |
| Transkripsi | OpenAI Whisper (`whisper-1`, word timestamps) |
| Analisis | OpenAI GPT (`gpt-5.4-mini`, structured output) |
| Video | ffmpeg 7.x, OpenCV, MediaPipe |
| Frontend | Next.js 15 (App Router), React 19 |
| Storage | Lokal `./output` (v0.1) → S3/Redis (v1.0) |

### 4.3 State & Job
- v0.1: job in-memory (`jobs.py` dict) — cukup untuk single-process.
- v1.0: Redis untuk horizontal scaling.

---

## 5. API Kontrak

### `POST /jobs`
```json
{ "url": "https://youtube.com/watch?v=...", "max_clips": 8, "mode": "podcast" }
```
→ `JobStatus` (job_id, status, progress).

### `GET /jobs/{id}`
```json
{
  "job_id": "abc", "status": "done", "progress": 1.0,
  "clips": [
    { "index": 1, "title": "...", "viral_score": 9,
      "start_time": 80.0, "end_time": 154.0, "download_url": "/clips/..." }
  ]
}
```

---

## 6. Roadmap

| Versi | Fokus | Status |
|-------|-------|--------|
| v0.1 | Pipeline inti + frontend | ✅ done |
| v0.2 | Multi-speaker, dynamic switching | ⬜ |
| v0.3 | TikTok/IG hardening, caption IG/TikTok, efek lanjutan | ⬜ |
| v1.0 | Mode 2 (Keyword), auth, Redis, produksi | ⬜ |

---

## 7. Keputusan & Catatan

- **Analisis dulu, download kemudian** (bukan download penuh dulu) → hemat bandwith.
- **Auto-provision key**: `OPENAI_API_KEY` harus diset pengguna (deploy sendiri).
- **YouTube memblokir IP datacenter** — uji end-to-end harus dari IP rumahan pengguna,
  bukan dari sandbox server.
