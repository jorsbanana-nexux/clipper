# REQUIREMENTS — Clipper

> Dokumen ini adalah **sumber kebenaran (source of truth)** untuk spesifikasi,
> arsitektur, dan roadmap. **Wajib diperbarui setiap ada tindakan/update/upgrade.**

**Terakhir diperbarui:** 2026-09-02 (setup.py full rewrite: venv + deps + launch otomatis)

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

> **Fase A (hardening) selesai**: cut mode accurate/fast (A1), bundle font (A2),
> verifikasi A/V+durasi (A3), auto-deteksi bahasa native (A4), yt-dlp tangguh (A5),
> sequential default (A6), cleanup+retention (A7). Uji end-to-end: `docs/TESTING.md`.

---

## 3. Mode 1 — Spesifikasi Detail

### 3.1 Sumber video
- YouTube, TikTok, Instagram, dan platform lain (via `yt-dlp`).
- v1 fokus **YouTube** (paling stabil). Platform lain diuji bertahap.

### 3.2 Alur Pipeline

| # | Tahap | Komponen | Output |
|---|-------|----------|--------|
| 1 | Ambil transkrip dari captions (0 MB audio) | `downloader.fetch_captions` | segmen `{start,end,text}` |
| 2 | Analisis momen viral | `analyzer.py` (GPT) | 6–10 `ViralMoment` |
| 3 | Unduh segmen video terpilih (+ padding 1,5 detik) | `downloader.download_segment` | video rentang saja |
| 4 | Whisper HANYA segmen audio terpilih (+ padding) | `downloader.download_audio_segment` + `transcriber` | word timestamps |
| 5 | Face track + reframe 9:16 (single / duo split-screen) | `face_tracker.py` + `layout.py` | `vertical.mp4` |
| 6 | Subtitle word-by-word | `subtitles.py` + `renderer.py` | `final.mp4` |
| 7 | Library unduh | `jobs.py` + frontend | daftar clip |

**Fallback:** bila video tidak punya caption, langkah 1–2 diganti: unduh audio penuh → Whisper full → analisis.

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
| Auto-reframe 9:16 + pelacakan wajah aktif (ikuti pembicara) | ✅ v0.1 |
| Multi-face detection + split-screen duo (2 pembicara) | ✅ v0.2 |
| Split kiri/kanan untuk 2 pembicara berdampingan | ✅ v0.2 (`reframe_duo two_halves=True`) |
| Speaker diarization (siapa bicara kapan) — opsional (pyannote, gated HF token) | ✅ v0.2 (opsional) |
| Dynamic speaker switching halus dalam satu clip (single ↔ duo, crossfade) | ✅ v0.2 (`compositor.py`) |

> **Catatan multi-speaker:** diarization bersifat **opsional** (`CLIPPER_MULTI_SPEAKER=1` +
> `HUGGINGFACE_TOKEN`) karena menarik `torch` (berat untuk PC low-spec). Tanpa itu, pipeline
> otomatis fallback ke single-speaker — tidak crash. Template layout: `single`, `duo` (`layout.py`).

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

Roadmap **lengkap & detail untuk agent masa depan** pindah ke
[`docs/ROADMAP.md`](docs/ROADMAP.md) — berisi urutan fase prioritas (A→G),
daftar gap/kekurangan, acceptance criteria, dan konvensi proyek. Hanya Mode 1 (Podcast).

Ringkas fase Mode 1:

| Fase | Fokus | Prioritas |
|------|-------|-----------|
| A | Akurasi & hardening dasar | P0 |
| B | Multi-speaker split-screen + dynamic switching | P0 |
| C | Subtitle & efek profesional | P1 |
| D | Platform (TikTok/IG/X) & pengunduhan | P1 |
| E | State, storage, observability | P1 |
| F | Frontend UX | P1 |
| G | Deployment, testing, keamanan | P2 |

---

## 7. Keputusan & Catatan

- **Analisis dulu, download kemudian** (bukan download penuh dulu) → hemat bandwith.
- **Captions-first** — transkrip dari caption YouTube (0 MB audio) bila tersedia; Whisper
  hanya untuk segmen audio terpilih (word timestamps subtitle).
- **Auto-chunk 25 MiB** (`transcriber.py`) — jalur fallback (audio penuh) dipecah otomatis
  di bawah batas 25 MiB OpenAI Whisper, tiap potongan ditranskrip lalu digabung dengan
  offset timestamp yang benar. Chunk senyap/kosong ditoleransi tanpa menggagalkan proses.
  Ini membuat podcast panjang (>25 MB audio) tetap jalan.
- **Audio vs video**: audio ringan (~57 MB/jam), video berat (~0.6–1.5 GB/jam) — itulah
  kenapa penghematan difokuskan ke unduhan video (hanya segmen terpilih).
- **Padding 1,5 detik** (`CLIPPER_PADDING_SEC`): setiap segmen dipotong sedikit lebih lebar
  (1,5 detik sebelum & sesudah momen) agar momen tidak pernah terpotong walau timestamp
  Whisper meleset 1–2 detik. Tetap pakai `-c copy` (cepat & ringan).
- **Auto-provision key**: `OPENAI_API_KEY` **wajib** diset pengguna (via `setup.py` sekali;
  key diketik tersembunyi, disimpan ke `.env`, dan ditampilkan "tersimpan" saat setup ulang — bisa diganti).
- **Multi-speaker opsional**: `HUGGINGFACE_TOKEN` boleh kosong (OFF); isi = ON, `off` = matikan.
- **setup.py mandiri**: buat `.venv` Python 3.11 + install Python deps + npm install + set key
  (WAJIB, tersembunyi) + HF token (opsional) + auto-start backend/frontend + buka browser.
  Diagnostik: `GET /health` menampilkan `openai_key` (set/missing).
- **.env.example**: template manual — salin ke `.env`, isi `OPENAI_API_KEY`, tanpa perlu setup.py.
- **YouTube memblokir IP datacenter** — uji end-to-end harus dari IP rumahan pengguna,
  bukan dari sandbox server.
