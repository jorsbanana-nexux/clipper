@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Clipper Launcher
cd /d "%~dp0"

echo.
echo  ================================================
echo    CLIPPER - Set API Key, Token, Launch Server
echo  ================================================
echo.

rem ---------- load existing .env ----------
set "OPENAI_API_KEY="
set "HUGGINGFACE_TOKEN="
set "CLIPPER_MULTI_SPEAKER=0"
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do set "%%A=%%B"
)

rem ---------- 1. OPENAI_API_KEY ----------
echo [1/2] OPENAI_API_KEY  ^(wajib - Whisper + GPT^)
if defined OPENAI_API_KEY (
    echo        [Status: terisi]
    set "OA_NEW="
    set /p "OA_NEW=        Key baru ^(Enter = pakai yang lama^): "
    if defined OA_NEW set "OPENAI_API_KEY=!OA_NEW!"
) else (
    echo        [Status: kosong]
    set /p "OPENAI_API_KEY=        Masukkan key ^(sk-...^): "
)

rem ---------- 2. HUGGINGFACE_TOKEN ----------
echo.
echo [2/2] HUGGINGFACE_TOKEN  ^(optional - multi-speaker, Enter = OFF^)
if defined HUGGINGFACE_TOKEN (
    echo        [Status: ON]
    set "HF_NEW="
    set /p "HF_NEW=        Token baru ^(Enter = matikan^): "
    if defined HF_NEW (
        set "HUGGINGFACE_TOKEN=!HF_NEW!"
        set "CLIPPER_MULTI_SPEAKER=1"
    ) else (
        set "HUGGINGFACE_TOKEN="
        set "CLIPPER_MULTI_SPEAKER=0"
    )
) else (
    echo        [Status: OFF]
    set "HF_NEW="
    set /p "HF_NEW=        Masukkan token ^(Enter = tetap OFF^): "
    if defined HF_NEW (
        set "HUGGINGFACE_TOKEN=!HF_NEW!"
        set "CLIPPER_MULTI_SPEAKER=1"
    )
)

rem ---------- 3. tulis .env ----------
> ".env" echo OPENAI_API_KEY=!OPENAI_API_KEY!
>> ".env" echo HUGGINGFACE_TOKEN=!HUGGINGFACE_TOKEN!
>> ".env" echo CLIPPER_MULTI_SPEAKER=!CLIPPER_MULTI_SPEAKER!

if not defined OPENAI_API_KEY (
    echo.
    echo [X] OPENAI_API_KEY kosong - tidak bisa lanjut.
    pause
    exit /b 1
)

echo.
echo [OK] .env tersimpan.
if "!HUGGINGFACE_TOKEN!"=="" (
    echo        OPENAI_API_KEY    : terisi
    echo        HuggingFace Token : OFF
) else (
    echo        OPENAI_API_KEY    : terisi
    echo        HuggingFace Token : ON
)

rem ---------- 4. pip install (pastikan python-dotenv dll up to date) ----------
echo.
echo [i] Sinkronisasi dependensi Python...
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
) else (
    python -m pip install -r requirements.txt --quiet
)

rem ---------- 5. start backend ----------
echo [i] Menjalankan backend...
if exist ".venv\Scripts\python.exe" (
    start "Clipper Backend" cmd /k ".venv\Scripts\python.exe backend\run.py"
) else (
    start "Clipper Backend" cmd /k "python backend\run.py"
)

rem ---------- 6. start frontend ----------
echo [i] Menjalankan frontend...
start "Clipper Frontend" cmd /k "cd /d "%CD%\frontend" && npm run dev"

rem ---------- 7. tunggu sebentar lalu buka browser ----------
echo [i] Menunggu server siap (8 detik)...
timeout /t 8 /nobreak >nul
start "" http://localhost:3000

echo.
echo [OK] Clipper berjalan!
echo      Backend : http://localhost:8000/health
echo      Frontend: http://localhost:3000
echo.
echo Jendela ini bisa ditutup. Backend + Frontend tetap berjalan.
pause >nul
exit /b 0