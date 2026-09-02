#!/usr/bin/env python3
"""Clipper - Setup & Launcher.

Jalankan SATU KALI dari root project:  python setup.py

Yang dilakukan otomatis:
  1. Cari Python 3.11 dan buat .venv di root project
  2. Install semua Python deps ke .venv (pip)
  3. Install npm/Node deps (npm install di frontend/)
  4. Tanya OPENAI_API_KEY (WAJIB, tersembunyi / tidak tercetak)
  5. Tanya HUGGINGFACE_TOKEN (OPSIONAL, tersembunyi)
  6. Simpan ke .env (tanpa duplikat; variabel lain dipertahankan)
  7. Jalankan backend + frontend di jendela terpisah + buka browser

Jalankan lagi kapan saja untuk ganti key atau re-install deps.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import webbrowser
from getpass import getpass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
FRONTEND_DIR = ROOT / "frontend"
VENV_DIR = ROOT / ".venv"
VENV_PY = (
    VENV_DIR / "Scripts" / "python.exe"
    if os.name == "nt"
    else VENV_DIR / "bin" / "python"
)

MANAGED = ("OPENAI_API_KEY", "HUGGINGFACE_TOKEN", "CLIPPER_MULTI_SPEAKER")
SEP = "=" * 62


# ── helpers ──────────────────────────────────────────────────────

def banner() -> None:
    print(SEP)
    print("  CLIPPER - Setup & Launch  (Python 3.11 venv + npm)")
    print(SEP)
    print()


def read_env(path: Path = ENV_PATH) -> dict:
    env: dict = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, _, v = s.partition("=")
            env[k.strip()] = v.strip()
    return env


def write_env(env: dict, path: Path = ENV_PATH) -> None:
    """Perbarui kunci MANAGED; pertahankan kunci lain dan komentar."""
    lines: list = []
    seen: set = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                lines.append(line)
                continue
            k = s.partition("=")[0].strip()
            if k in env:
                lines.append(f"{k}={env[k]}")
                seen.add(k)
            else:
                lines.append(line)
    for k in MANAGED:
        if k not in seen and k in env:
            lines.append(f"{k}={env[k]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def mask(value: str, keep: int = 7) -> str:
    return value[:keep] + "..." if value else "(kosong)"


# ── venv ─────────────────────────────────────────────────────────

def find_python311() -> str | None:
    """Temukan path interpreter Python 3.11 di sistem."""
    if os.name == "nt":
        try:
            out = subprocess.check_output(
                ["py", "-3.11", "-c", "import sys; print(sys.executable)"],
                text=True, stderr=subprocess.DEVNULL,
            ).strip()
            if out and Path(out).exists():
                return out
        except Exception:
            pass
    for cand in ("python3.11", "python3", "python"):
        exe = shutil.which(cand)
        if not exe:
            continue
        try:
            ver = subprocess.check_output(
                [exe, "--version"], text=True, stderr=subprocess.STDOUT
            ).strip()
            if "3.11" in ver:
                return exe
        except Exception:
            pass
    return None


def ensure_venv() -> bool:
    if VENV_PY.exists():
        print(f"[OK] .venv sudah ada ({VENV_PY})")
        return True
    print("[..] Membuat .venv dengan Python 3.11...")
    py311 = find_python311()
    if not py311:
        print("[X] Python 3.11 tidak ditemukan di sistem.")
        print("    Download: https://www.python.org/downloads/release/python-31119/")
        print("    Setelah install, jalankan lagi: python setup.py")
        return False
    r = subprocess.run([py311, "-m", "venv", str(VENV_DIR)])
    if r.returncode != 0 or not VENV_PY.exists():
        print("[X] Gagal membuat .venv.")
        print(f"    Coba manual: {py311} -m venv .venv")
        return False
    print(f"[OK] .venv dibuat  ->  {VENV_PY}")
    return True


# ── python deps ───────────────────────────────────────────────────

def install_python_deps(multi_speaker: bool = False) -> bool:
    req = ROOT / "requirements.txt"
    if not req.exists():
        print("[!] requirements.txt tidak ditemukan - dilewati.")
        return True
    print("[..] Upgrade pip di .venv (sekali)...")
    subprocess.run(
        [str(VENV_PY), "-m", "pip", "install", "--upgrade", "pip", "-q"],
        capture_output=True,
    )
    print("[..] Install Python deps (requirements.txt)...")
    r = subprocess.run([str(VENV_PY), "-m", "pip", "install", "-r", str(req)])
    ok = r.returncode == 0
    if multi_speaker:
        req2 = ROOT / "requirements-multispeaker.txt"
        if req2.exists():
            print("[..] Install multi-speaker deps (requirements-multispeaker.txt)...")
            r2 = subprocess.run([str(VENV_PY), "-m", "pip", "install", "-r", str(req2)])
            ok = ok and r2.returncode == 0
    if ok:
        print("[OK] Python deps terpasang.")
    else:
        print("[!] Sebagian deps gagal - lihat pesan di atas.")
    return ok


# ── npm deps ──────────────────────────────────────────────────────

def install_npm_deps() -> bool:
    if not (FRONTEND_DIR / "package.json").exists():
        print("[!] frontend/package.json tidak ada - npm install dilewati.")
        return True
    if (FRONTEND_DIR / "node_modules").exists():
        print("[OK] node_modules sudah ada - dilewati.")
        return True
    npm = shutil.which("npm")
    if not npm:
        print("[X] npm tidak ditemukan. Install Node.js 18+ dulu:")
        print("    https://nodejs.org/")
        return False
    print("[..] Install frontend deps (npm install)...")
    r = subprocess.run(["npm", "install"], cwd=str(FRONTEND_DIR))
    if r.returncode == 0:
        print("[OK] Frontend deps terpasang.")
        return True
    print("[!] npm install gagal. Coba manual: cd frontend && npm install")
    return False


# ── key prompts ───────────────────────────────────────────────────

def ask_openai_key(existing: str) -> str:
    print("[KEY 1/2] OPENAI_API_KEY  (WAJIB - Whisper + GPT analisis)")
    if existing:
        print(f"          Tersimpan : {mask(existing, 9)}")
        print("          [Enter]   = pakai tersimpan")
        print("          [ketik]   = ganti key")
    while True:
        val = getpass("          Masukkan  : ").strip()
        if val:
            return val
        if existing:
            print("          [i] Memakai key tersimpan.")
            return existing
        print("          [X] WAJIB - tidak boleh kosong.")


def ask_hf_token(existing: str, on: bool):
    print()
    print("[KEY 2/2] HUGGINGFACE_TOKEN  (OPSIONAL - multi-speaker diarization)")
    if on:
        print(f"          Status    : AKTIF (ON) {mask(existing)}")
        print("          [Enter]   = tetap ON")
        print("          [token]   = ganti token")
        print("          ['off']   = matikan (OFF)")
    else:
        print("          Status    : OFF (single-speaker)")
        print("          [Enter]   = tetap OFF")
        print("          [token]   = aktifkan (ON)")
    val = getpass("          Masukkan  : ").strip()
    if val.lower() == "off":
        return "", ""
    if not val:
        return (existing, "1") if on else ("", "")
    return val, "1"


# ── launch ────────────────────────────────────────────────────────

def launch() -> None:
    flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
    subprocess.Popen([str(VENV_PY), "backend/run.py"], cwd=str(ROOT), creationflags=flags)
    npm = shutil.which("npm") or "npm"
    subprocess.Popen([npm, "run", "dev"], cwd=str(FRONTEND_DIR), creationflags=flags)
    print("[..] Menunggu server siap (6 detik)...")
    time.sleep(6)
    webbrowser.open("http://localhost:3000")


# ── main ──────────────────────────────────────────────────────────

def main() -> int:
    banner()
    warn = False
    if shutil.which("ffmpeg") is None:
        print("[!] ffmpeg tidak ditemukan - subtitle & video TIDAK berfungsi.")
        print("    Download: https://ffmpeg.org/download.html"); warn = True
    if shutil.which("npm") is None:
        print("[!] npm/Node.js tidak ditemukan - frontend tidak berjalan.")
        print("    Download: https://nodejs.org/"); warn = True
    if warn:
        print()

    print(SEP); print("  [1/4] Python 3.11 Virtual Environment"); print(SEP)
    if not ensure_venv():
        input("\nTekan Enter untuk keluar..."); return 1

    print(); print(SEP); print("  [2/4] Konfigurasi API Keys"); print(SEP)
    env = read_env()
    existing_key = env.get("OPENAI_API_KEY", "")
    hf = env.get("HUGGINGFACE_TOKEN", "")
    multi = env.get("CLIPPER_MULTI_SPEAKER", "").strip().lower()
    currently_on = bool(hf) and multi in ("1", "true", "yes", "on")

    key = ask_openai_key(existing_key)
    new_hf, new_multi = ask_hf_token(hf, currently_on)
    multi_speaker_on = bool(new_hf)

    env["OPENAI_API_KEY"] = key
    env["HUGGINGFACE_TOKEN"] = new_hf
    env["CLIPPER_MULTI_SPEAKER"] = new_multi
    write_env(env)
    print()
    print("[OK] .env tersimpan:")
    print(f"     OPENAI_API_KEY    : {mask(key, 9)}   (WAJIB - aktif)")
    print(f"     HUGGINGFACE_TOKEN : {mask(new_hf) if new_hf else '(kosong - multi-speaker OFF)'}")

    print(); print(SEP); print("  [3/4] Install Python Dependencies"); print(SEP)
    install_python_deps(multi_speaker=multi_speaker_on)

    print(); print(SEP); print("  [4/4] Install Frontend Dependencies (npm)"); print(SEP)
    install_npm_deps()

    print(); print(SEP); print("  Menjalankan Backend + Frontend"); print(SEP)
    launch()

    print()
    print("[OK] Selesai!")
    print("  Backend : http://localhost:8000   (GET /health = cek status key)")
    print("  Frontend: http://localhost:3000")
    print()
    print("  Jalankan 'python setup.py' lagi untuk ganti key atau re-install deps.")
    print("  Tutup jendela ini - server tetap jalan di jendelanya masing-masing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
