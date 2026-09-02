#!/usr/bin/env python3
"""Clipper - setup & launcher (pengganti setup.bat yang rusak).

Tugas:
1. Tanya OPENAI_API_KEY (WAJIB)  - diketik tersembunyi (getpass), tidak tercetak.
2. Tanya HUGGINGFACE_TOKEN (OPSIONAL) - Enter = pertahankan status,
   ketik token = ON (multi-speaker), ketik "off" = matikan.
3. Tulis ke .env (tanpa duplikat; variabel lain dipertahankan).
4. Sinkronkan dependencies (sekali).
5. Jalankan backend + frontend di proses terpisah + buka browser.

Jalankan:  python setup.py
"""

from __future__ import annotations

import importlib.util
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

MANAGED = ("OPENAI_API_KEY", "HUGGINGFACE_TOKEN", "CLIPPER_MULTI_SPEAKER")


def banner() -> None:
    print("=" * 62)
    print("  CLIPPER - Setup AI Key + Launch Backend & Frontend")
    print("=" * 62)
    print()


def read_env(path: Path = ENV_PATH) -> dict:
    env: dict = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key, _, value = s.partition("=")
            env[key.strip()] = value.strip()
    return env


def write_env(env: dict, path: Path = ENV_PATH) -> None:
    """Tulis .env: perbarui kunci MANAGED, pertahankan sisanya & urutannya."""
    lines = []
    seen = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                lines.append(line)
                continue
            key = s.partition("=")[0].strip()
            if key in env:
                lines.append(f"{key}={env[key]}")
                seen.add(key)
            else:
                lines.append(line)
    for key in MANAGED:
        if key not in seen and key in env:
            lines.append(f"{key}={env[key]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def mask(value: str, keep: int = 7) -> str:
    if not value:
        return "(kosong)"
    return value[:keep] + "..."


def ask_openai_key(existing: str) -> str:
    print("[1/2] OPENAI_API_KEY  (WAJIB - Whisper + GPT analisis)")
    if existing:
        print(f"      Tersimpan: {mask(existing, 9)}")
        print("      [Enter] = pakai yang tersimpan   [ketik baru] = ganti")
    else:
        print("      [ketik] = masukkan key baru")
    while True:
        key = getpass("      Masukkan: ").strip()
        if key:
            return key
        if existing:
            print("      [i] Memakai key yang tersimpan.")
            return existing
        print("      [X] OPENAI_API_KEY WAJIB diisi - tidak boleh kosong.")


def ask_hf_token(existing: str, currently_on: bool):
    print()
    print("[2/2] HUGGINGFACE_TOKEN  (OPSIONAL - multi-speaker)")
    if currently_on:
        print(f"      Status: AKTIF (ON)  {mask(existing)}")
        print("      [Enter] = tetap ON   [ketik token] = ganti   [ketik 'off'] = matikan")
    else:
        print("      Status: OFF (single-speaker)")
        print("      [Enter] = tetap OFF   [ketik token] = ON")
    val = getpass("      Masukkan: ").strip()
    if val.lower() == "off":
        return "", ""
    if not val:
        if currently_on:
            return existing, "1"
        return "", ""
    return val, "1"


def deps_ok() -> bool:
    missing = [m for m in ("openai", "yt_dlp", "fastapi", "cv2", "dotenv")
               if importlib.util.find_spec(m) is None]
    return not missing


def sync_deps() -> None:
    py_ok = deps_ok()
    fe_ok = (FRONTEND_DIR / "node_modules").exists()
    if py_ok and fe_ok:
        print("[i] Dependencies sudah terpasang - dilewati.")
        return
    if not py_ok:
        print("[..] Install dependencies Python (sekali saja)...")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                           cwd=str(ROOT))
        if r.returncode != 0:
            print("[!] Install deps Python gagal. Manual: pip install -r requirements.txt")
    if not fe_ok:
        print("[..] Install dependencies frontend (sekali saja)...")
        r = subprocess.run(["npm", "install"], cwd=str(FRONTEND_DIR))
        if r.returncode != 0:
            print("[!] npm install gagal. Manual: cd frontend && npm install")


def launch() -> None:
    print("[..] Menjalankan backend + frontend...")
    flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
    subprocess.Popen([sys.executable, "backend/run.py"], cwd=str(ROOT), creationflags=flags)
    subprocess.Popen(["npm", "run", "dev"], cwd=str(FRONTEND_DIR), creationflags=flags)
    print("[..] Menunggu server siap, lalu membuka browser...")
    time.sleep(6)
    webbrowser.open("http://localhost:3000")


def main() -> int:
    banner()

    if shutil.which("ffmpeg") is None:
        print("[!] ffmpeg tidak ditemukan di PATH - subtitle & video TIDAK akan berfungsi.\n")
    if shutil.which("npm") is None:
        print("[!] npm/node tidak ditemukan - frontend tidak akan berjalan.\n")

    env = read_env()
    existing_key = env.get("OPENAI_API_KEY", "")
    hf = env.get("HUGGINGFACE_TOKEN", "")
    multi = env.get("CLIPPER_MULTI_SPEAKER", "").strip().lower()
    currently_on = bool(hf) and multi in ("1", "true", "yes", "on")

    key = ask_openai_key(existing_key)
    new_hf, new_multi = ask_hf_token(hf, currently_on)

    env["OPENAI_API_KEY"] = key
    env["HUGGINGFACE_TOKEN"] = new_hf
    env["CLIPPER_MULTI_SPEAKER"] = new_multi
    write_env(env)

    print()
    print("[OK] .env tersimpan:")
    print(f"      OPENAI_API_KEY    : {mask(key, 9)}   (WAJIB - siap)")
    if new_hf:
        print(f"      HUGGINGFACE_TOKEN : {mask(new_hf)}   (multi-speaker ON)")
    else:
        print("      HUGGINGFACE_TOKEN : (kosong - multi-speaker OFF)")
    print()

    sync_deps()
    launch()

    print()
    print("Backend : http://localhost:8000   (cek key: GET /health)")
    print("Frontend: http://localhost:3000")
    print("Tutup jendela ini - server tetap berjalan di jendelanya sendiri.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
