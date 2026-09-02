@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Clipper - Set Keys
cd /d "%~dp0"

echo ============================================================
echo   CLIPPER - Set OPENAI_API_KEY & HUGGINGFACE_TOKEN
echo ============================================================
echo.

rem ---------- 1. OPENAI_API_KEY (wajib) ----------
set "OPENAI_API_KEY="
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if /I "%%A"=="OPENAI_API_KEY" set "OPENAI_API_KEY=%%B"
    )
)
if defined OPENAI_API_KEY (
    echo [i] OPENAI_API_KEY ditemukan: !OPENAI_API_KEY:~0,7!...
    echo     (Enter = pertahankan yang lama, ketik baru = ganti)
)
set /p "KEY=OPENAI_API_KEY: "
if defined KEY set "NEW_OPENAI=!KEY!"
if not defined KEY set "NEW_OPENAI=!OPENAI_API_KEY!"
if not defined NEW_OPENAI (
    echo [X] OPENAI_API_KEY wajib diisi. Tidak ada perubahan disimpan.
    pause
    exit /b 1
)

rem ---------- 2. HUGGINGFACE_TOKEN (opsional; kosong = OFF) ----------
set "HUGGINGFACE_TOKEN="
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if /I "%%A"=="HUGGINGFACE_TOKEN" set "HUGGINGFACE_TOKEN=%%B"
    )
)
echo.
if defined HUGGINGFACE_TOKEN (
    echo [i] Multi-speaker saat ini AKTIF (token terdeteksi).
    echo     Enter         = OFF (hapus token, kembali single-speaker)
    echo     ketik token   = ganti token (tetap ON)
) else (
    echo [i] Multi-speaker saat ini OFF.
    echo     Enter         = tetap OFF
    echo     ketik token   = ON (aktifkan multi-speaker)
)
set /p "HF=HUGGINGFACE_TOKEN (Enter = OFF / isi = ON): "
if defined HF (
    set "MULTI_SPEAKER=1"
    set "NEW_HF=!HF!"
) else (
    set "MULTI_SPEAKER="
    set "NEW_HF="
)

rem ---------- 3. tulis .env tanpa duplikat ----------
set "TMP_ENV=%TEMP%\clipper_env_%RANDOM%.tmp"
> "%TMP_ENV%" echo OPENAI_API_KEY=!NEW_OPENAI!
>> "%TMP_ENV%" echo HUGGINGFACE_TOKEN=!NEW_HF!
>> "%TMP_ENV%" echo CLIPPER_MULTI_SPEAKER=!MULTI_SPEAKER!

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
echo     OPENAI_API_KEY    : !NEW_OPENAI:~0,7!...
if defined NEW_HF (
    echo     HUGGINGFACE_TOKEN : !NEW_HF:~0,7!... (multi-speaker ON)
    echo     CLIPPER_MULTI_SPEAKER = 1
) else (
    echo     HUGGINGFACE_TOKEN : (kosong - multi-speaker OFF)
    echo     CLIPPER_MULTI_SPEAKER = (kosong)
)
echo.
echo Selesai. Tutup jendela ini, lalu mulai backend & frontend secara manual.
pause >nul
exit /b 0