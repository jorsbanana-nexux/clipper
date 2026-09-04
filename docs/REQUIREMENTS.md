# REQUIREMENTS — Clipper

> Dokumen ini adalah **sumber kebenaran (source of truth)** untuk spesifikasi,
> arsitektur, dan roadmap. **Wajib diperbarui setiap ada tindakan/update/upgrade.**

**Terakhir diperbarui:** 2026-09-04 (v0.3.0 — human steer, skor 5 dimensi, metadata posting bahasa konten, preset subtitle, multi-aspek, ZIP, smoke test offline)

## 0a-ter3. Changelog v0.3.3 (2026-09-04 — duo face-aware + anti-smear)

1. reframe_duo REWRITE: tracking 2 identitas wajah (stabil kiri/kanan,
   nearest-identity, carry-forward), tiap band crop-follow sendiri, EMA
   smoothing — bukan lagi belah statis 50/50 tanpa otak.
2. BUGFIX subtitle: clamp anti-smear — tak pernah 2 kata solid biru
   bersamaan saat timestamp Whisper overlap.
3. tests/smoke_duo_facetrack.py: 7 test PASS (logika + bukti render warna
   mengikuti track + handoff warna presisi).

## 0a-ter2. Changelog v0.3.2 (2026-09-04 — replikasi video referensi MrBeast + 2 bugfix subtitle)

1. **mrbeast preset v2** (analisis frame-by-frame video referensi): aktif
   #00E5FF (ASS &H00FFE500), em 150, outline 12, Komika Axis.
2. **BUGFIX**: \N manual di WrapStyle 2 — cue panjang tidak lagi menembus layar.
3. **BUGFIX**: _reframe_blur_pad mengabaikan ass_path — konten faceless kini
   ber-subtitle.
4. **Cue sadar-kalimat** + posisi 61-78% tinggi frame (aman UI, perspektif
   penonton). Verifikasi OpenCV objektif.

## 0a-ter. Changelog v0.3.1 (2026-09-04 — audit fase A/B, 2 bugfix kritis, fallback model Gemini, quality gate)

1. **layout.py BUGFIX**: reset `solo_run` saat giliran pembicara berganti —
   sebelumnya duo TIDAK PERNAH aktif pada diarization bergantian normal
   (penyebab nyata keluhan "split gagal aktif meski HF token diisi").
2. **jobs.py BUGFIX**: snap-cut `<= floor` → `< floor - 0.001` — konklusi yang
   berakhir tepat di min_dur kini dipotong benar (dead air ekor hilang).
3. **Dead code**: `window_has_two_faces` dihapus (audit: tidak pernah dipanggil).
4. **Duo semantics**: `CLIPPER_DUO_AUTO_FACES` default 0; HF ON = duo split
   otomatis (lead 2,5s, anti-telat, validasi wajah), HF OFF = solo mulus.
5. **Analyzer**: `GEMINI_FALLBACK_MODELS` rantai fallback gratis +
   `CLIPPER_MIN_VIRAL_SCORE` quality gate (anti clip asal).
6. **Bukti**: 7/7 unit test logika PASS; smoke test render offline PASS.

## 0a-bis. Changelog v0.3.0 (2026-09-04 — riset kompetitor: Opus, Vizard, Klap, 2short, Clip.fm, quso, Wisecut, Riverside, Munch, SubMagic, Captions, CapCut, Eklipse, Spikes)

> Dirancang dari keluhan pengguna nyata lintas platform (moment selection meleset,
> klip repetitif, subtitle buruk terutama non-English, kontrol kreatif rendah,
> metadata posting tidak ada). Detail: `docs/ROADMAP.md` §2b.

1. **Human steer** — `ClipRequest.keywords` + `instruction` masuk prompt analyzer
   (prioritas tertinggi). Keluhan #1 semua platform: "AI picked the boring parts".
2. **Skor multi-dimensi** — `models.ClipScores` (hook/payoff/emotion/quotability/
   energy, 1-10, tanpa inflasi) di tiap `ViralMoment` & `ClipInfo`.
3. **Metadata posting** — `caption` + `hashtags` per clip, dalam BAHASA KONTEN
   (language rule eksplisit di prompt).
4. **Preset subtitle** — `config.SUBTITLE_PRESETS`: mrbeast / hormozi / minimal /
   karaoke / none; `subtitles.words_to_ass(..., style=...)`; karaoke = \kf
   progressive fill dengan fix timing (durasi fill → start kata berikutnya).
5. **Multi-aspek** — `config.ASPECTS` + `renderer.convert_aspect()` (blur-pad
   face-safe); `jobs._render_one_clip` konversi final pass; `9:16|1:1|4:5`.
6. **Endpoint baru** — `GET /styles`, `GET /jobs/{id}/zip` (ZIP semua clip +
   `metadata.json` berisi caption/hashtag/skor).
7. **Frontend** — form steer (topik + instruksi), selector style & aspek, kartu
   clip dengan bar skor 5 dimensi, caption/hashtag + tombol copy, download ZIP.
8. **`tests/smoke_render.py`** — uji rantai render end-to-end OFFLINE (sintetis
   via lavfi): precise_trim, 5 preset ASS, burn efek, reframe 9:16, konversi
   1:1/4:5, verifikasi, thumbnail. **PAS** di lingkungan bersih (Python 3.11,
   ffmpeg 5.1, tanpa mediapipe/torch/Gemini).

## 0b. Changelog v0.2.2 (evaluasi pengguna: performa, AI, kamera, duo HF, subtitle)

1. **Subtitle MrBeast strict** — teks 100% tanpa tanda baca; maks 2 baris di tengah layar; bounce per kata 100→120→95→100% sinkron dengan pengucapan; HANYA kata aktif menyala kuning lalu kembali putih; stroke hitam tebal. (`subtitles.py`, config `SUBTITLE_POP/DIP/POP_COLOR`)
2. **FIX duo HuggingFace di jalur caption** — gating `not used_captions` membuat diarization level-analisis TIDAK PERNAH berjalan di jalur default (captions) walau token HF + `CLIPPER_MULTI_SPEAKER=1` sudah diisi. Kini: mode multi-speaker aktif → audio penuh diunduh sekali (ter-cache) untuk diarization di SEMUA jalur; nonaktif → tetap ringan, solo crop-follow mulus.
3. **Diagnostik multi-speaker** — penyebab nonaktifnya HF (env off / token kosong / torch / pyannote belum diinstall) dilaporkan ke pesan job dan `/health` (`multi_speaker_reason`) — gagal senyap tidak terjadi lagi.
4. **Anti dead-air (cut rule di KODE, bukan cuma prompt)** — `_snap_cut_boundaries`: akhir tiap klip ditarik ke akhir kalimat konklusi / sebelum jeda hening; filler dan dead air di akhir klip dibuang. Prompt analyzer kini mewajibkan struktur HOOK → INTI → KONKLUSI dan melarang ekor hening.
5. **Kamera** — EMA dua arah (forward+backward): pan eases in-out, tidak lagi telat/kaku; zoom-out default 0.86→0.80, headroom 0.30→0.32: wajah proporsional, tidak menempel layar.
6. **Verifikasi fase A/B** — tidak ada dead code: seluruh fungsi renderer/layout/diarization/downloader terpanggil. Batch render paralel (bounded `CLIPPER_MAX_PARALLEL`, CPU-aware, gagal satu klip tidak membatalkan job) diverifikasi bekerja.

## 0. Changelog v0.2.1 (bug-fix audit)

Perbaikan hasil audit mikroskopis (semua sudah diverifikasi + unit test):

1. **CRITICAL** `analyzer` — batas keras 200 segmen membuat LLM mengabaikan 70-80% transkrip video >15 menit. Sekarang transkrip PENUH dikirim (budget karakter 400k, konfigurable `CLIPPER_TRANSCRIPT_MAX_CHARS`).
2. **HIGH** `subtitles` — `	()` ASS memakai milidetik, bukan centidetik; animasi pop selesai ~10x terlalu cepat. Diperbaiki (`ms0/ms1`).
3. **HIGH** `downloader` — regex VTT mensyaratkan HH:MM:SS; auto-caption YouTube `<1 jam` memakai MM:SS.mmm → parse gagal. Diperbaiki.
4. **HIGH** `downloader` — `fetch_captions` sekarang menerima + mem-parse `json3`/`srv1`/`srv3` (auto-caption YouTube sering HANYA tersedia dalam format itu) → fallback unduh audio penuh jauh lebih jarang.
5. **HIGH** `downloader` — fallback full-download sekarang di-CACHE per URL (video & audio): sebelumnya N klip = N x unduh penuh (bisa gigabytes); sekarang 1x per URL.
6. **HIGH** `transcriber` — WhisperModel kini singleton lazy (dulu dimuat ULANG per klip → thrash CPU/RAM paralel).
7. **HIGH** `jobs` — remap timing subtitle setelah xfade: dulu rescale LINEER (makin nyaris out-of-sync tiap transisi layout); kini offset PER-SEGMENT eksak (`_remap_words_for_xfade`).
8. **MEDIUM** `compositor` — xfade offset negatif saat segmen < crossfade → fallback concat (tidak crash lagi); file antara `.cut/.ref` dibersihkan.

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
| Transkripsi | **faster-whisper lokal** (gratis, default) / OpenAI Whisper (`whisper-1`) |
| Analisis | **Gemini** (gratis, default) / OpenAI GPT (`gpt-4o-mini`, structured output) |
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
- **Auto-provision key**: `OPENAI_API_KEY` **wajib** diisi pengguna via file `.env`
  (salin dari `.env.example`, isi `OPENAI_API_KEY=sk-...`).
- **Multi-speaker opsional**: `HUGGINGFACE_TOKEN` boleh kosong (OFF); isi = ON.
  Aktifkan juga `CLIPPER_MULTI_SPEAKER=1`.
- **Setup manual (setup.py dihapus)**: bikin `.venv` Python 3.11 + install Python deps
  + `npm install` + isi `.env` + jalankan backend (`backend/run.py`) + frontend.
  Diagnostik: `GET /health` menampilkan `openai_key` (set/missing).
  Panduan step-by-step: `README.md` (section "Menjalankan Secara Lokal").
- **.env.example**: template contoh — salin ke `.env`, isi `OPENAI_API_KEY`.
- **YouTube memblokir IP datacenter** — uji end-to-end harus dari IP rumahan pengguna,
  bukan dari sandbox server.
