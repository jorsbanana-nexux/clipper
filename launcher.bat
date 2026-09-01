@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Clipper Launcher

rem ============================================================
rem   CLIPPER - Smart Launcher (idempotent + safe self-heal)
rem ============================================================
cd /d "%~dp0"

set "READY=1"
set "PY="
set "NODE="
set "NPM="

rem ---------- 1. locate Python ----------
where py >nul 2>nul && (set "PY=py -3")
if not defined PY (
    where python >nul 2>nul && (set "PY=python")
)
if not defined PY (
    echo [X] Python tidak ditemukan.
    call :try_install_python
)
if not defined PY (
    set "READY=0"
    echo [i] Silakan install Python 3.11 dari https://www.python.org lalu jalankan ulang.
)

rem ---------- 2. version check (>= 3.10) ----------
if defined PY (
    %PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
    if errorlevel 1 (
        echo [X] Python terlalu lama. Butuh 3.10+. Install yang terbaru.
        set "READY=0"
    )
)

rem ---------- 3. ffmpeg ----------
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [X] ffmpeg tidak ditemukan.
    call :try_install_ffmpeg
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
    set "READY=0"
    echo [i] ffmpeg penting untuk potong/subtitle video. Install dari https://ffmpeg.org
)

rem ---------- 4. node + npm ----------
where node >nul 2>nul && (set "NODE=node")
where npm >nul 2>nul && (set "NPM=npm")
if not defined NODE (
    echo [X] Node.js tidak ditemukan.
    call :try_install_node
)
if not defined NODE (
    set "READY=0"
    echo [i] Install Node.js 18+ dari https://nodejs.org
)
if not defined NPM (set "READY=0")

rem ---------- 5. venv ----------
if not exist ".venv\Scripts\python.exe" (
    echo [i] Membuat virtual environment...
    %PY% -m venv .venv
)
set "VENV_PY=.venv\Scripts\python.exe"

rem ---------- 6. python deps ----------
echo [i] Menyinkronkan dependensi Python (aman & cepat jika sudah ada)...
%VENV_PY% -m pip install --upgrade pip --quiet
%VENV_PY% -m pip install -r requirements.txt --quiet

rem ---------- 7. .env (API key) ----------
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do set "%%A=%%B"
)
if not defined OPENAI_API_KEY (
    echo.
    echo [i] OPENAI_API_KEY belum ditemukan.
    set /p "KEY_INPUT=Paste OpenAI API key (sk-...): "
    if defined KEY_INPUT (
        > .env call :write_env OPENAI_API_KEY %KEY_INPUT%
        set "OPENAI_API_KEY=%KEY_INPUT%"
    )
)
if not defined OPENAI_API_KEY (
    echo [X] Tanpa OPENAI_API_KEY backend tidak bisa jalan.
    set "READY=0"
)

rem ---------- 8. optional multi-speaker deps ----------
if defined HUGGINGFACE_TOKEN (
    echo [i] Multi-speaker aktif - install dep tambahan...
    %VENV_PY% -m pip install -r requirements-multispeaker.txt --quiet
)

rem ---------- 9. frontend ----------
if not exist "frontend\node_modules" (
    echo [i] Install dependensi frontend (npm)...
    pushd frontend
    call npm install
    popd
)

rem ---------- 10. launch ----------
if "%READY%"=="0" (
    echo.
    echo [X] Ada prasyarat yang belum terpenuhi. Perbaiki di atas lalu jalankan ulang.
    pause
    exit /b 1
)

echo.
echo [OK] Menjalankan Backend + Frontend, lalu membuka browser...
start "Clipper Backend" cmd /k "cd /d "%CD%" && .venv\Scripts\python.exe backend\run.py"
start "Clipper Frontend" cmd /k "cd /d "%CD%\frontend" && npm run dev"
timeout /t 6 /nobreak >nul
start "" http://localhost:3000
echo.
echo [OK] Launcher selesai. Browser akan terbuka otomatis.
echo      Backend : http://localhost:8000  (jendela terpisah)
echo      Frontend: http://localhost:3000
echo.
echo Tekan tombol apa saja untuk menutup jendela ini (server tetap jalan).
pause >nul
exit /b 0

rem ============================================================
rem   Safe-install helpers (only via existing package managers)
rem ============================================================
:try_install_python
where winget >nul 2>nul && (
    echo [i] Mencoba install Python via winget...
    winget install -e --id Python.Python.3.11 --scope user --accept-source-agreements --accept-package-agreements
    where python >nul 2>nul && (set "PY=python")
) else (
    echo [i] winget tidak ada - install Python manual dari python.org
)
exit /b 0

:try_install_ffmpeg
where winget >nul 2>nul && (
    echo [i] Mencoba install ffmpeg via winget...
    winget install -e --id Gyan.FFmpeg --scope user --accept-source-agreements --accept-package-agreements
)
exit /b 0

:try_install_node
where winget >nul 2>nul && (
    echo [i] Mencoba install Node.js via winget...
    winget install -e --id OpenJS.NodeJS.LTS --scope user --accept-source-agreements --accept-package-agreements
    where node >nul 2>nul && (set "NODE=node")
    where npm >nul 2>nul && (set "NPM=npm")
)
exit /b 0

:write_env
echo %2=%3
exit /b 0
