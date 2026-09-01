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
| 2 | Potongan `-c copy` menempel ke **keyframe** (bisa geser ~2–5 detik); padding 1,5s hanya menutupi sebagian | Batas clip bisa kurang presisi | A1 |
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

- [ ] **A0 — Uji end-to-end** (paling penting, pertama). Jalankan di IP rumahan pengguna
      dengan `OPENAI_API_KEY` asli. Uji dengan 1 video pendek (1–3 menit) dulu, lalu 1 podcast
      panjang (30–60 menit). Catat semua error, perbaiki sampai jalur captions & fallback sama-sama OK.
- [ ] **A1 — Potongan frame-accurate.** Tambah opsi di `renderer.clip_segment`: mode re-encode
      (`-ss` sebelum `-i`, tanpa `-c copy`) sebagai pilihan "akurat" vs mode "cepat". Bisa jadi
      konfig `CLIPPER_CUT_MODE=fast|accurate`.
- [ ] **A2 — Bundle font.** Taruh `assets/fonts/Montserrat-ExtraBold.ttf` (atau Bebas Neue) ke repo,
      set `fontsdir` di header ASS, dan fallback ke font sistem. Ini menjamin subtitle konsisten.
- [ ] **A3 — Verifikasi A/V & sinkron.** Setelah render, `ffprobe` output: pastikan ada stream
      video + audio, durasi mendekati `padded_end - padded_start`. Kalau tidak, retry 1× lalu flag.
- [ ] **A4 — Auto-detect bahasa.** Captions-first: ambil caption bahasa asli dulu (bukan paksa "en"),
      gunakan `language` dari metadata; kalau tidak ada, Whisper auto-detect.
- [ ] **A5 — yt-dlp tangguh.** Dukung `--cookies-from-browser`/file cookies (dari env path, BUKAN
      chat), proxy opsional, retry + backoff, dan rantai format fallback.
- [ ] **A6 — Batasi konkurensi.** Karena PC pengguna low-spec, proses clip **berurutan** (default).
      Tambah konfig `CLIPPER_MAX_PARALLEL=1..3` bila suatu saat ingin paralel.
- [ ] **A7 — Cleanup & retention.** Hapus folder job lama setelah N hari (env `CLIPPER_RETENTION_DAYS`,
      default 7), dan jangan simpan file antara (`full.*`, `aseg.*`, `vertical.mp4`) setelah selesai.

---

### Fase B — Multi-speaker & layout dinamis (P0, versi v0.2)

Inti "wawancara/podcast multi-orang" yang diminta user.

- [ ] **B1 — Speaker diarization.** Deteksi "siapa bicara kapan" (pakai service diarization atau
      pyannote-audio). Simpan sebagai `segments[{speaker, start, end}]`.
- [ ] **B2 — Analisis berbasis speaker.** Umpan label speaker ke GPT agar momen viral bisa
      disebut "pembicara A memotong pembicara B", dsb.
- [ ] **B3 — Multi-face tracking.** Deteksi >1 wajah, pilih **wajah pembicara aktif** (berdasarkan
      diarization/arah suara), bukan cuma wajah terbesar. Pertahankan smoothing anti-jitter.
- [ ] **B4 — Split-screen dua pembicara.** Bila 2 speaker aktif simultan, tampilkan dua panel
      (atas-bawah atau kiri-kanan) di 9:16. Template: `single` / `duo` / `screen-share`.
- [ ] **B5 — Dynamic speaker switching.** Transisi halus antar template (webcam ↔ screen share ↔
      face zoom) berdasarkan siapa/screen yang aktif, tanpa video robek/glitch.

**Acceptance B:** wawancara 2 orang menghasilkan clip dengan kedua wajah terlihat saat
berdialog, dan pindah panel dengan mulus mengikuti pembicara aktif.

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

## 7. Cara melanjutkan (mulai dari mana)

1. Clone repo, `pip install -r requirements.txt`, set `OPENAI_API_KEY`.
2. Jalankan backend (`python backend/run.py`) + frontend (`cd frontend && npm install && npm run dev`).
3. **Mulai dari Fase A0** — uji end-to-end dengan video pendek, catat semua error.
4. Kerjakan A1..A7, lalu B1..B5. Update dokumen setelah tiap fase selesai.
