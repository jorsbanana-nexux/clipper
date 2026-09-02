> [!WARNING]
> ## ⚠️ STATUS: TAHAP PENGEMBANGAN AKTIF
> Dokumen ini adalah **panduan lengkap untuk agent masa depan** agar bisa melanjutkan
> pengembangan **tanpa kehilangan konteks**. Fokus **100% ke Mode 1 (Podcast)**.
> **Mode 2 (Keyword) TIDAK dibahas dan TIDAK dikerjakan di sini.**

---

# ROADMAP — Clipper (Mode 1 Podcast)

**Tujuan dokumen:** satu tempat berisi (1) apa yang sudah jadi, (2) apa yang masih
kurang, dan (3) rencana langkah demi langkah terurut prioritas sampai Mode 1 **matang**.

---

## 1. Cara kerja Mode 1 (ringkasan akurat saat ini)

```
tempel URL
  ├── caption ADA   → transkrip dari caption YouTube (0 MB audio) ──────────┐
  └── caption TIDAK → unduh audio full → auto-chunk <25 MiB → Whisper ──────┤
                                                                             ▼
                                                    GPT pilih 6–10 momen viral
                                                                             ▼
                          unduh segmen VIDEO terpilih (+ padding 1,5 detik)
                                                                             ▼
                          unduh segmen AUDIO terpilih → Whisper → word timestamps
                                                                             ▼
                          face-track & reframe 9:16 (ikuti wajah / blur-pad)
                                                                             ▼
                          subtitle word-by-word (ASS karaoke) + efek
                                                                             ▼
                          library unduh (video + audio + subtitle sinkron)
```

**Kunci arsitektur (jangan dilupakan agent):
- **Analisis dulu, download kemudian** — hanya segmen terpilih yang diunduh.
- **Captions-first** — transkrip gratis 0 MB bila caption tersedia.
- **Padding 1,5 detik** — momen tidak terpotong walau timestamp meleset.
- **Auto-chunk 25 MiB** — jalur fallback audio full aman untuk podcast panjang.

---

## 2. Status terkini (v0.1) — yang SUDAH jalan

| Komponen | File | Status |
|----------|------|--------|
| Download (audio-only, captions, segment ranges, per-clip audio) | `downloader.py` | ✅ |
| Transkripsi word-level + auto-chunk 25 MiB | `transcriber.py` | ✅ |
| Deteksi momen viral (GPT structured output) | `analyzer.py` | ✅ |
| Face tracking + reframe 9:16 (crop-follow + blur-pad) | `face_tracker.py` | ✅ |
| Subtitle word-by-word (ASS `\k`) | `subtitles.py` | ✅ |
| Clip + efek + thumbnail (ffmpeg) | `renderer.py` | ✅ |
| Job async + progress | `jobs.py` | ✅ |
| FastAPI app + static serving | `main.py` | ✅ |
| Frontend (paste URL → progress → library) | `frontend/` | ✅ |
| README + REQUIREMENTS | root + `docs/` | ✅ |

**Logika kunci SUDAH dites di sandbox**: ffmpeg reframe+burn, MediaPipe/OpenCV face
detection, crop-follow 9:16 mux audio, parser VTT/SRT, ASS word-by-word, auto-chunk split.

---

## 3. KEKURANGAN / GAP yang diketahui (penting dibaca agent)

> Ini daftar jujur hal-hal yang **belum beres**. Jangan dianggap sudah jalan.

| # | Gap / Bug | Dampak | Diperbaiki di fase |
|---|-----------|--------|-------------------|
| 1 | **Belum pernah uji end-to-end** (YouTube blokir IP sandbox + butuh `OPENAI_API_KEY` pengguna) | Risiko bug tersembunyi di integrasi nyata | A0 |
| 2 | ~~Potongan `-c copy` menempel ke **keyframe**~~ — diperbaiki A1 (`_ffmpeg_cut` re-encode) | Batas clip presisi (accurate default) | A1 ✅ |
| 3 | Font "Montserrat" hanya disebut **nama** — kalau font tidak terpasang di host, ffmpeg pakai font default | Subtitle bisa jelek/tidak konsisten | A2 |
| 4 | Captions-first hanya prioritaskan **English** (`startswith("en")`); auto-detect bahasa lain belum | Video non-Inggris bisa salah pilih caption | A4 |
| 5 | Belum ada **speaker diarization** (siapa yang bicara) | Tidak bisa label pembicara | B1 |
| 6 | Face tracking **single-speaker**; jitter masih mungkin | Multi-orang belum optimal | B3/B4 |
| 7 | Job **in-memory** — hilang saat restart; tidak ada resume | Proses hilang jika crash | E1 |
| 8 | Tidak ada **cleanup** folder output | Disk membesar tanpa batas | A7 |
| 9 | yt-dlp tanpa **cookies/proxy/retry** | Video age-restricted/login gagal | A5 |
| 10 | Platform selain YouTube **belum diuji** (TikTok/IG/X) | Bisa gagal di platform lain | D1 |
| 11 | Efek cuma **satu** (kontras/saturasi/sharpen) | Kurang "viral" | C3 |
| 12 | Tidak ada verifikasi A/V sinkron setelah render | Output rusak tak terdeteksi | A3 |
| 13 | Tidak ada **cost tracking** (Whisper detik + GPT token) | Biaya OpenAI tak terukur | E2 |
| 14 | Frontend minimal: tanpa thumbnail grid, download-all, copy caption, job history | UX belum matang | F1–F4 |
| 15 | CORS `*` + tanpa auth | Tidak aman untuk deploy publik | G3 |
| 16 | Tidak ada Dockerfile / .env.example / CI / test | Susah deploy & rawat | G1–G5 |

---

## 4. RENCANA KE DEPAN (fase terurut prioritas — HANYA Mode 1)

> Urutan yang disarankan: **A → B → C → D → E → F → G**.
> "Mode 1 sempurna" = **A + B selesai** (benar + multi-speaker).
> "Mode 1 matang" = tambah **C + D**. "Mode 1 produksi" = tambah **E + F + G**.

---

### Fase A — Akurasi & hardening dasar (P0, versi v0.1.x)

Mengamankan fondasi sebelum nambah fitur.

- [ ] **A0 — Uji end-to-end** ⏳ *checklist, belum dijalankan* — lihat `docs/TESTING.md`. Harus
      dijalankan di IP rumahan dengan `OPENAI_API_KEY` asli (sandbox tidak bisa: YouTube blokir IP
      datacenter). Mulai dari 1 video pendek (1–3 menit), lalu 1 podcast panjang (30–60 menit).
- [x] **A1 — Potongan frame-accurate.** ✅ `CLIPPER_CUT_MODE=fast|accurate` dipakai di
      `downloader._ffmpeg_cut` (dipanggil lewat fallback `downloader.download_full_and_cut`);
      accurate = re-encode `-ss` sebelum `-i` (default) — batas clip presisi, bukan `-c copy`.
      *(duplikat `renderer.clip_segment` yang tak pernah dipanggil sudah dibuang — lihat §6i)*.
- [x] **A2 — Bundle font.** ✅ `subtitles.py` mendukung `CLIPPER_FONT_DIR` -> `fontsdir` ASS +
      resolve nama font vs file `.ttf/.otf`, fallback font sistem.
- [x] **A3 — Verifikasi A/V & sinkron.** ✅ `renderer.verify_output` (ffprobe: cek stream video +
      audio + durasi), dipanggil setelah render tiap clip.
- [x] **A4 — Auto-detect bahasa.** ✅ `fetch_captions` kini native-first (bukan English-first) dan
      mengembalikan `(segments, lang)`; `lang` diteruskan sebagai hint ke Whisper.
- [x] **A5 — yt-dlp tangguh.** ✅ `YDL_COOKIES_FILE` (path, jangan tempel di chat), `YDL_PROXY`,
      `YDL_RETRIES` (default 3), retry + fallback format.
- [x] **A6 — Batasi konkurensi.** ✅ `CLIPPER_MAX_PARALLEL` kini benar-benar mengatur banyaknya
      render antar-clip via `asyncio.Semaphore` (default 1 = sequential, low-spec friendly).
- [x] **A7 — Cleanup & retention.** ✅ `_cleanup_old_jobs` + `CLIPPER_RETENTION_DAYS` (default 7).

---

### Fase B — Multi-speaker & layout dinamis (P0, versi v0.2)

Inti "wawancara/podcast multi-orang" yang diminta user.

- [x] **B1 — Speaker diarization.** ✅ `diarization.py` (pyannote-audio, **opsional**, gated
      `HUGGINGFACE_TOKEN` + `CLIPPER_MULTI_SPEAKER`). Fallback aman tanpa token.
- [x] **B2 — Analisis berbasis speaker.** ✅ `analyzer.find_viral_moments(..., turns=...)` menerima
      speaker turns; prompt menginstruksikan GPT memilih momen pertukaran 2 pembicara + mengisi
      field `speaker`/`speakers` tiap momen.
- [x] **B3 — Multi-face tracking.** ✅ `face_tracker.analyze_faces_all` deteksi banyak wajah
      (urut ukuran/confidence). Pemilihan pembicara aktif via diarization (B1).
- [x] **B4 — Split-screen dua pembicara.** ✅ `face_tracker.reframe_duo` (vstack atas-bawah 9:16).
      `two_halves=True` memotong **kiri/kanan** sumber (dua speaker berdampingan) lalu menumpuk
      vertikal — diuji dengan sumber kiri-merah/kanan-biru. Template `single`/`duo`/`share` di `layout.py`.
- [x] **B5 — Dynamic speaker switching.** ✅ `compositor.py` render timeline multi-template per clip
      (single ↔ duo) + crossfade `xfade`, audio di-mux ulang agar tetap sinkron. Aktif saat
      diarization tersedia dan clip punya >1 layout berbeda.

**Acceptance B:** ✅ v0.2 lengkap — wawancara 2 orang menghasilkan clip dengan kedua wajah
terlihat saat berdialog (duo), pindah panel mulus mengikuti pembicara aktif (dynamic switching).

---

### Fase C — Subtitle & efek profesional (P1, v0.3)

Membuat hasil terlihat "editor profesional, bukan robot".

- [ ] **C1 — Multi-template subtitle.** Buat beberapa style siap pakai: Hormozi word-pop,
      classic captions, highlight bar, warna tema. User pilih di frontend.
- [ ] **C2 — Animasi kata lanjutan.** Perbaiki word-by-word: efek pop/scale per kata, warna aktif
      berbeda, progress bar, latar semi-transparan, auto-wrap baris + auto-fit.
- [ ] **C3 — Library efek.** Zoom punch pada momen puncak, fade in/out, ken-burns, color grade
      preset (cinematic/warm/cool), glow, drop shadow, vignette.
- [ ] **C4 — Safe margin adaptif.** Margin subtitle beda per platform (TikTok/Reels/Shorts) dan
      auto-fit agar tidak tertutup tombol like/comment.
- [ ] **C5 — Musik latar opsional.** Musik bebas royalti (lokal/URL), auto-ducking saat bicara.
- [ ] **C6 — Branding/watermark opsional.** Logo/teks brand di pojok, bisa dimatikan.

---

### Fase D — Platform & pengunduhan (P1, v0.3)

Memperluas dari "hanya YouTube" ke "apa pun URL-nya".

- [ ] **D1 — Harden extractor.** Uji & perbaiki TikTok, Instagram Reels, X/Twitter, Facebook.
      Buat tabel status per platform di REQUIREMENTS.
- [ ] **D2 — Login/age-restricted.** Dukungan cookies (path file via env, jangan di chat).
- [ ] **D3 — Batch / playlist.** Terima banyak URL atau playlist sekali jalan (antrian job).
- [ ] **D4 — Resume parsial.** Jangan render ulang clip yang sudah jadi (skip by hash/status).

---

### Fase E — State, storage & observability (P1, v0.4)

Membuat sistem tahan restart dan terukur.

- [ ] **E1 — Job persistence.** Ganti dict in-memory dengan SQLite (sederhana) atau Redis
      (skala). Survive restart + resume.
- [ ] **E2 — Cost tracking.** Catat detik Whisper + token GPT per job, tampilkan estimasi biaya.
- [ ] **E3 — Observability.** Structured log + step log + metrik (durasi tiap tahap).
- [ ] **E4 — Cancel & retry.** Sempurnakan cancel (`_cancel` sudah ada) + retry otomatis on error.

---

### Fase F — Frontend UX (P1, v0.4)

- [ ] **F1 — Thumbnail grid + preview.** Tampilkan thumbnail (sudah dibuat server-side) + hover play.
- [ ] **F2 — Download all (zip)** + download per clip.
- [ ] **F3 — Caption/hook/title.** Tampilkan + tombol copy + edit + regenerate per clip.
- [ ] **F4 — Job history.** Riwayat job + resume + retry.
- [ ] **F5 — Progress detail.** Tampilkan stage aktif + ETA + status per clip (bukan hanya %).
- [ ] **F6 — Settings UI.** Preset kualitas (fast/balanced/quality), template subtitle, toggle efek.

---

### Fase G — Deployment, testing & keamanan (P2, v1.0)

- [ ] **G1 — Dockerfile + docker-compose.** Sertakan ffmpeg/ffprobe/font/OpenCV dalam image.
- [ ] **G2 — .env.example + validasi config.** Dokumentasikan tiap env var.
- [ ] **G3 — Auth + CORS ketat.** API key untuk frontend→backend; batasi origin.
- [ ] **G4 — Test.** Unit test (parser, subtitles, chunk-merge, padding) + 1 integration test
      pakai video sampel kecil.
- [ ] **G5 — CI (GitHub Actions).** Lint + test otomatis di tiap push.
- [ ] **G6 — Tuning low-spec.** Preset ffmpeg (threads, resize cap 720p fallback, preset speed).

---

## 5. Prioritas ringkas

1. **SEKARANG (P0):** A0 uji end-to-end → A1..A7 hardening → B1..B5 multi-speaker.
2. **LALU (P1):** C subtitle/efek → D platform → E state/observability → F frontend.
3. **TERAKHIR (P2):** G deployment/testing/keamanan.

> **JANGAN** menyentuh Mode 2. Semua di atas cukup untuk membuat Mode 1 menjadi clipper matang.

---

## 6. Konvensi proyek (untuk agent)

- **Selalu update `README.md`, `docs/REQUIREMENTS.md`, dan `docs/ROADMAP.md`** setiap ada
  perubahan/modifikasi. Ini aturan mutlak.
- Tiap file backend modular (satu tanggung jawab). Jangan taruh logika pipeline di `main.py`.
- Gunakan `config.py` untuk semua nilai yang bisa diubah (env var), jangan hardcode angka.
- Jaga prinsip **ringan**: unduh hanya yang perlu, `-c copy` default, proses berurutan.
- Subtitle word-by-word **harus** dari timestamp kata Whisper (bukan estimasi).
- Semua kunci/rahasia lewat **environment variable**, jangan pernah hardcode atau di chat.

---

## 6a. Review mikroskopis reframe_duo (2026-09-01)

- `reframe_duo` **selalu** crop kiri/kanan (cabang `two_halves` dihapus, menghilangkan
  prilaku "vstack bingkai sama" yang salah untuk podcast side-by-side).
- `_xcx_at` bebas dead-code + memiliki guard `b == a` (mencegah `ZeroDivisionError`).
- Terverifikasi: sumber kiri-merah / kanan-biru → band atas MERAH, band bawah BIRU,
  audio ikut tersalin. Semua 13 modul backend lolos `py_compile`.


## 7. Cara melanjutkan (mulai dari mana)

1. Clone repo, `pip install -r requirements.txt`, set `OPENAI_API_KEY`.
2. Jalankan backend (`python backend/run.py`) + frontend (`cd frontend && npm install && npm run dev`).
3. **Mulai dari Fase A0** — uji end-to-end dengan video pendek, catat semua error.
4. Kerjakan A1..A7, lalu B1..B5. Update dokumen setelah tiap fase selesai.

---

## 6b. Perbaikan bug & hardening (2026-09-02)

- `fetch_captions` selalu mengembalikan tuple 3 elemen `(segments, lang, title)` dan
  `lang` dinormalisasi ke kode ISO 639-1 (fix crash saat metadata tidak bisa diambil).
- Detektor wajah (MediaPipe + Haar) di-inisialisasi **sekali**, bukan per frame.
- `reframe` crop-follow fallback ke blur-pad bila sumber lebih sempit dari 9:16.
- Diarization kini selalu memakai WAV 16 kHz mono (bukan mp3 mentah).
- `verify_output` kini menegakkan keberadaan stream audio (A/V sinkron benar-benar dijaga).
- `download_full_and_cut` / `download_full_audio_and_cut` memberi error jelas bila unduhan
  tidak menghasilkan file (bukan `IndexError`).
- Bersihkan dead code: `fill_note`, `transcript_text`, variabel `title` tak terpakai.
- `README.md` + `setup.bat`: referensi `launcher.bat` (file sudah dihapus) diperbaiki.

---

## 6c. Wire A1/A6 (2026-09-02)

- `GET /health` kini menampilkan status `openai_key` (set/missing) & `multi_speaker`,
  dan `/jobs` memberi pesan error yang jelas bila key belum diset.
- A1 ter-wire penuh (`downloader._ffmpeg_cut` taat `CLIPPER_CUT_MODE`).
- A6 aktif (`asyncio.Semaphore(CLIPPER_MAX_PARALLEL)` membatasi render antar-clip).

## 6d. Hapus setup.bat — ganti setup.py (2026-09-02)

- **Penyebab bug**: `setup.bat` hasil suntingan memakai line-ending **LF** (bukan CRLF yang
  diwajibkan `cmd.exe`) dan karakter `&` di `echo ... Backend & Frontend`. Keduanya merusak
  batch: prompt key tampil, lalu jendela langsung menutup tanpa menyimpan `.env`, tanpa
  menanyakan token HF, dan tanpa menjalankan server.
- **Solusi permanen**: `setup.bat` **dihapus**. Penggantinya `setup.py` (Python) yang:
  - memakai `getpass` sehingga key/token **tidak tercetak** saat diketik,
  - key AI wajib (loop), HF token opsional (Enter = pertahankan / isi = ON / `off` = matikan),
  - menulis `.env` tanpa duplikat, lalu auto-start backend + frontend + buka browser,
  - error selalu tampil di konsol (tidak pernah menutup senyap).
- **Manual fallback**: salin `.env.example` → `.env`, isi `OPENAI_API_KEY=...`.
- **Pelajaran untuk agent**: jangan edit file `.bat` dari sandbox Linux tanpa menormalkan
  line-ending ke CRLF; jangan letakkan `&` mentah di `echo` batch. Gunakan `setup.py` (Python).

---

## 6e. setup.py full rewrite: venv + deps otomatis (2026-09-02)

- `setup.py` dirombak menjadi satu perintah mandiri (`python setup.py`):
  1. **Buat `.venv` Python 3.11** otomatis (Windows: `py -3.11 -m venv .venv`).
  2. **Install Python deps** ke `.venv` (`pip install -r requirements.txt`; +multispeaker jika HF token ON).
  3. **`npm install`** di `frontend/` (dilewati jika `node_modules` sudah ada).
  4. **Tanya key** dengan `getpass` (tidak tercetak); simpan ke `.env` tanpa duplikat.
  5. **Launch** backend via `.venv` Python + frontend via `npm run dev` + buka browser.
- `.venv` dan `node_modules` tetap di `.gitignore` (tidak di-push; dibuat lokal).
- Alur pengguna: clone → `python setup.py` → isi key → selesai.
- Agent masa depan: `.venv` Python = `.venv/Scripts/python.exe` (Win) / `.venv/bin/python` (Unix).

## 6f. Bug-fix batch (2026-09-02)

Batch perbaikan bug mikro & risiko hasil review mikroskopis:

- **Model palsu diperbaiki**: `ANALYSIS_MODEL` default `gpt-5.4-mini` (bukan model
  OpenAI nyata → HTTP 404 saat analisis) diganti ke **`gpt-4o-mini`** (structured
  output didukung). Tetap override via env `ANALYSIS_MODEL`. `reasoning_effort`
  kini di-gate lewat `ANALYSIS_REASONING` (hanya o-series yang menerimanya).
- **Timescale diarization diperbaiki**: `_render_one_clip` menghitung timeline
  layout dalam koordinat **lokal** (`layout_timeline(turns, 0.0, loc_dur)`),
  bukan absolut + `rel_timeline` (yang double-shift). `rel_timeline` dihapus
  (dead code). Dynamic switching single/duo kini sinkron.
- **CORS diperketat**: `allow_origins=["*"]` diganti `config.CORS_ORIGINS`
  (default localhost:3000/8000). Override via env `CLIPPER_CORS_ORIGINS`.
- **Chunk stream-copy diperbaiki**: `transcriber._split_audio` memakai ekstensi
  source (bukan hardcode `.mp3`) — mencegah mux rusak saat source opus/webm.
- **Pesan usang diperbaiki**: referensi `setup.bat` (sudah dihapus) di `main.py`
  & `config.py` → `setup.py`.
- **Label DEPRECATED dihapus** dari `face_tracker.analyze_faces` (memang helper
  single-speaker yang sah, bukan alias usang).

Semua 13 modul backend tetap lolos `py_compile` setelah perubahan ini.

## 6g. Hapus setup.py — beralih ke setup manual (2026-09-02)

- **Keputusan**: `setup.py` (auto venv + deps + npm + prompt key + auto-launch)
  **dihapus** karena terlalu besar, sulit di-debug, dan kaku (kunci Python 3.11,
  auto-launch server tidak stabil).
- **Ganti**: setup 100% manual — bikin `.venv`, install deps, isi `.env`
  (`OPENAI_API_KEY` WAJIB + `HUGGINGFACE_TOKEN` opsional), jalankan backend +
  frontend. Panduan step-by-step ada di `README.md` ("Menjalankan Secara Lokal").
- `setup.py` sendiri tidak lagi dipakai/diwartu oleh `config.py`; `config.py`
  tetap load `.env` via python-dotenv (tidak bergantung pada setup.py).
- `.env.example` diperbarui: komentar berisi alur manual + link tempat ambil key.
- Agent masa depan: JANGAN hidupkan ulang `setup.py`. Setup = manual (README).

## 6h. FIX KRITIS: POST /jobs selalu 500 "no running event loop" (2026-09-02)

- **Gejala**: set key benar + ffmpeg ada, tapi tempel URL → klik Generate →
  **Internal Server Error** selalu, di setiap job.
- **Akar masalah**: `main.create_job` adalah endpoint **sync** (`def`). FastAPI
  menjalankan fungsi sync di threadpool thread yang **tidak punya asyncio event
  loop**. `jobs.JobManager.start` memanggil `asyncio.create_task(...)` yang
  wajib berada dalam event loop → `RuntimeError: no running event loop` → 500.
- **Perbaikan**: `create_job` diubah jadi **`async def`** (FastAPI menjalankan
  async endpoint di event loop utama). `manager.start` tetap sync (membuat task),
  dipanggil tanpa `await` dari konteks async yang sudah punya loop.
- **Verifikasi (sandbox)**: `POST /jobs` → `200 OK` status `queued`; pipeline
  maju sampai tahap `analyze` (progress 0.35) — hanya gagal di auth OpenAI karena
  key placeholder, bukan bug. Rantai render (blur-pad, duo, crop-follow,
  subtitle+efek, thumbnail) lolos semua verifikasi ffprobe (audio+video sinkron).
- **Pelajaran**: endpoint FastAPI yang menjadwalkan task asyncio (via
  `asyncio.create_task`) HARUS `async def`; fungsi sync di threadpool tidak punya
  event loop.

## 6i. Verifikasi A/B + buang dead code (2026-09-02)

Semua klaim "selesai/berfungsi" di Fase A (A1-A7) & Fase B (B1-B5) **diuji nyata
  dengan video sintetis + ffmpeg + ffprobe** — 13/13 PASS:
  A1 cut accurate (2.08s utk 2.0s) & fast; A2 fontsdir line + ffmpeg burn OK;
  A3 tolak no-audio; A4 parser caption + normalisasi lang; A5 retries/cookies/
  proxy; A6 Semaphore (MAX_PARALLEL=1); A7 cleanup retention; B1 diarization
  gated aman; B2 analisis pakai turns; B3 multi-face; B4 split-screen duo;
  B5 dynamic switching single→duo (video+audio sinkron).
- **Dead code dibuang**: `renderer.clip_segment` (duplikat `_ffmpeg_cut`, tak
  pernah dipanggil pipeline), `downloader.extract_metadata` (tak pernah dipanggil),
  `config.DEFAULT_MAX_CLIPS` (0 referensi). `LAYOUT_SHARE` & `mode="keyword"`
  dipertahankan sebagai template/mode ter-reserve (dokumentasi).
- **Catatan**: sandbox punya `OPENAI_API_KEY` env berisi placeholder `cf-...`
  (bukan key asli) — jangan dikira key Anda. Key asli user = `sk-...` di `.env`.
- **Satu-satunya yang belum bisa diuji di sandbox**: unduhan + captions YouTube
  (IP datacenter diblokir). Harus diuji dari PC rumahan (Fase A0).
