@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Clipper - Setup & Launch
cd /d "%~dp0"

echo ============================================================
echo    CLIPPER - Setup AI Key + Launch Backend & Frontend
echo ============================================================
echo.

rem ---- sanity checks ----
where python >nul 2>nul
if errorlevel 1 (
    echo [X] Python tidak ditemukan. Install Python 3.11 dulu, lalu jalankan lagi.
    pause
    exit /b 1
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [!] ffmpeg TIDAK ditemukan. Subtitle & video TIDAK akan berfungsi.
    echo     Install ffmpeg dan pastikan ada di PATH.
)

rem ---- load existing values dari .env ----
set "OLD_KEY="
set "OLD_HF="
set "OLD_MULTI="
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if /I "%%A"=="OPENAI_API_KEY" set "OLD_KEY=%%B"
        if /I "%%A"=="HUGGINGFACE_TOKEN" set "OLD_HF=%%B"
        if /I "%%A"=="CLIPPER_MULTI_SPEAKER" set "OLD_MULTI=%%B"
    )
)

rem ============================================================
rem  1. OPENAI_API_KEY  (WAJIB)
rem ============================================================
:ASK_KEY
echo.
echo [1/2] OPENAI_API_KEY  (WAJIB - AI key untuk Whisper + GPT analisis)
if defined OLD_KEY (
    echo        Status: TERSIMPAN & terverifikasi  !OLD_KEY:~0,9!...
    echo        [Enter] = pakai key tersimpan
)
echo        [ketik baru] = ganti key
echo.
set "KEY_IN="
set /p "KEY_IN=        Masukkan: "
if not defined KEY_IN (
    if defined OLD_KEY (
        set "NEW_KEY=!OLD_KEY!"
        echo        [i] Memakai key tersimpan.
    ) else (
        echo.
        echo        [X] OPENAI_API_KEY WAJIB diisi ^(tidak boleh kosong^).
        goto ASK_KEY
    )
) else (
    set "NEW_KEY=!KEY_IN!"
)

rem ============================================================
rem  2. HUGGINGFACE_TOKEN  (OPSIONAL - multi-speaker)
rem ============================================================
echo.
echo [2/2] HUGGINGFACE_TOKEN  (OPSIONAL - aktifkan multi-speaker)
if defined OLD_HF (
    echo        Status saat ini: AKTIF (ON)  !OLD_HF:~0,7!...
    echo        [Enter] = tetap ON   [ketik token] = ganti   [ketik off] = matikan
) else (
    echo        Status saat ini: OFF (single-speaker)
    echo        [Enter] = tetap OFF   [ketik token] = ON
)
echo.
set "HF_IN="
set /p "HF_IN=        Masukkan: "

if /I "!HF_IN!"=="off" (
    set "NEW_HF="
    set "NEW_MULTI="
    echo        [i] Multi-speaker dimatikan (OFF).
) else if not defined HF_IN (
    if defined OLD_HF (
        set "NEW_HF=!OLD_HF!"
        set "NEW_MULTI=1"
        echo        [i] Multi-speaker tetap ON.
    ) else (
        set "NEW_HF="
        set "NEW_MULTI="
        echo        [i] Multi-speaker tetap OFF.
    )
) else (
    set "NEW_HF=!HF_IN!"
    set "NEW_MULTI=1"
    echo        [i] Multi-speaker diaktifkan (ON).
)

rem ============================================================
rem  simpan ke .env (pertahankan variabel lain)
rem ============================================================
set "TMP_ENV=%TEMP%\clipper_env_%RANDOM%.tmp"
> "%TMP_ENV%" echo OPENAI_API_KEY=!NEW_KEY!
>> "%TMP_ENV%" echo HUGGINGFACE_TOKEN=!NEW_HF!
>> "%TMP_ENV%" echo CLIPPER_MULTI_SPEAKER=!NEW_MULTI!

if exist ".env" (
    for /f "usebackq delims=" %%A in (".env") do (
        set "LINE=%%A"
        set "NAME=!LINE!"
        for /f "tokens=1 delims==" %%N in ("!LINE!") do set "NAME=%%N"
        if /I not "!NAME!"=="OPENAI_API_KEY" if /I not "!NAME!"=="HUGGINGFACE_TOKEN" if /I not "!NAME!"=="CLIPPER_MULTI_SPEAKER" (
            >> "%TMP_ENV%" echo !LINE!
        )
    )
)
move /y "%TMP_ENV%" ".env" >nul

echo.
echo [OK] .env tersimpan:
echo        OPENAI_API_KEY    : !NEW_KEY:~0,9!...   (WAJIB - siap)
if defined NEW_HF (
    echo        HUGGINGFACE_TOKEN : !NEW_HF:~0,7!...   (multi-speaker ON)
) else (
    echo        HUGGINGFACE_TOKEN : (kosong - multi-speaker OFF)
)

rem ============================================================
rem  sinkronisasi dependencies (sekali)
rem ============================================================
echo.
echo [..] Menyinkronkan dependencies Python...
pip install -q -r requirements.txt

if not exist "frontend\node_modules" (
    echo [..] Menginstall dependencies frontend (sekali saja)...
    pushd frontend
    call npm install
    popd
)

rem ============================================================
rem  jalankan backend + frontend + buka browser
rem ============================================================
echo.
echo [OK] Menjalankan backend + frontend di jendela terpisah...
start "Clipper Backend" cmd /k "python backend\run.py"
pushd frontend
start "Clipper Frontend" cmd /k "npm run dev"
popd

timeout /t 4 /nobreak >nul
start "" "http://localhost:3000"

echo.
echo Selesai.  Backend : http://localhost:8000   (cek key: GET /health)
echo           Frontend: http://localhost:3000
echo Tutup jendela ini.
timeout /t 3 /nobreak >nul
exit /b 0
