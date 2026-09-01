# TESTING — Checklist Uji End-to-End (Fase A0)

> **PENTING:** ini TIDAK bisa dijalankan dari sandbox CodeWords karena YouTube
> memblokir IP datacenter. Jalankan di **PC kamu** dengan internet rumahan +
> `OPENAI_API_KEY` aktif.

## Prasyarat

```bash
cd clipper
pip install -r requirements.txt          # (opsional) pip install -r requirements-multispeaker.txt
export OPENAI_API_KEY="sk-..."
python backend/run.py                     # http://localhost:8000
```

Buka frontend: `cd frontend && npm install && BACKEND_URL=http://localhost:8000 npm run dev`

## A0 — Alur uji (berurutan)

### 1. Smoke test (health)
```bash
curl http://localhost:8000/health
# → {"status":"ok","ffmpeg":true}
```

### 2. Video pendek (1–3 menit) — jalur captions-first
1. Tempel URL YouTube pendek yang **punya subtitle/caption**.
2. Amati log: harus muncul stage `transcript_captions` (TANPA unduh audio penuh).
3. Hasil: 6–10 clip 9:16 + subtitle word-by-word.
4. Cek: tiap clip punya audio + video, subtitle menyala pas kata diucapkan.

### 3. Video yang TIDAK punya caption — jalur fallback
1. Tempel URL tanpa caption (atau pakai video non-Inggris).
2. Log: stage `download_audio` → `transcribe` (Whisper full, auto-chunk >25 MiB).
3. Hasil tetap OK, subtitle tetap word-by-word.

### 4. Podcast panjang (30–60 menit) — auto-chunk
1. Tempel podcast panjang.
2. Log: audio >25 MiB harus ter-chunk otomatis (banyak `whisper_chunk_*`).
3. Hasil tidak error, timestamp tidak melompat antar-chunk.

### 5. Klip akurat (A1)
```bash
export CLIPPER_CUT_MODE=accurate   # default sudah accurate
```
- Cek awal/akhir clip pas (tidak kepotong di tengah kata).

### 6. Multi-speaker (opsional, butuh token HF)
```bash
export CLIPPER_MULTI_SPEAKER=1
export HUGGINGFACE_TOKEN="hf_..."
pip install -r requirements-multispeaker.txt
```
- Tempel podcast wawancara 2 orang.
- Hasil: clip dengan split-screen duo (kiri/kanan) + dynamic switching.

### 7. Cleanup (A7)
```bash
export CLIPPER_RETENTION_DAYS=0    # matikan utk uji; default 7 hari
```
- Folder job lama harus bersih dari `output/`.

## Form laporan bug (untuk agent masa depan)

Saat menemukan error, catat:
- URL video (jika publik)
- Tahap yang gagal (dari log `stage=`)
- Pesan error persis
- `OPENAI_API_KEY` valid / tidak (YA/TIDAK, jangan tempel key-nya)
- Versi yt-dlp + ffmpeg (`yt-dlp --version`, `ffmpeg -version`)
