@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Clipper - Set API Key & Token
cd /d "%~dp0"

echo.
echo  ================================================
echo    CLIPPER - Set API Key & Hugging Face Token
echo  ================================================
echo.

rem ---------- load existing .env ----------
set "OPENAI_API_KEY="
set "HUGGINGFACE_TOKEN="
set "CLIPPER_MULTI_SPEAKER=0"
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do set "%%A=%%B"
)

rem ---------- OPENAI_API_KEY ----------
echo [1/2] OPENAI_API_KEY  ^(wajib - Whisper + analisis GPT^)
if defined OPENAI_API_KEY (
    echo        [Status: terisi]
    set "OA_FINAL="
    set /p "OA_FINAL=        Key baru ^(Enter = pakai yang lama^): "
    if defined OA_FINAL set "OPENAI_API_KEY=!OA_FINAL!"
) else (
    echo        [Status: kosong]
    set /p "OPENAI_API_KEY=        Masukkan key ^(sk-...^): "
)

rem ---------- HUGGINGFACE_TOKEN ----------
echo.
echo [2/2] HUGGINGFACE_TOKEN  ^(optional - multi-speaker^)
if defined HUGGINGFACE_TOKEN (
    echo        [Status: ON]
    set "HF_FINAL="
    set /p "HF_FINAL=        Token baru ^(Enter = OFF/matikan^): "
    if defined HF_FINAL (
        set "HUGGINGFACE_TOKEN=!HF_FINAL!"
        set "CLIPPER_MULTI_SPEAKER=1"
    ) else (
        set "HUGGINGFACE_TOKEN="
        set "CLIPPER_MULTI_SPEAKER=0"
    )
) else (
    echo        [Status: OFF]
    set "HF_FINAL="
    set /p "HF_FINAL=        Masukkan token ^(Enter = tetap OFF, isi = ON^): "
    if defined HF_FINAL (
        set "HUGGINGFACE_TOKEN=!HF_FINAL!"
        set "CLIPPER_MULTI_SPEAKER=1"
    ) else (
        set "HUGGINGFACE_TOKEN="
        set "CLIPPER_MULTI_SPEAKER=0"
    )
)

rem ---------- write .env ----------
> ".env" echo OPENAI_API_KEY=!OPENAI_API_KEY!
>> ".env" echo HUGGINGFACE_TOKEN=!HUGGINGFACE_TOKEN!
>> ".env" echo CLIPPER_MULTI_SPEAKER=!CLIPPER_MULTI_SPEAKER!

echo.
echo [OK] Tersimpan ke .env
if not defined OPENAI_API_KEY (
    echo        OPENAI_API_KEY       : KOSONG ^(backend tidak bisa jalan^)
) else (
    echo        OPENAI_API_KEY       : terisi
)
if "!HUGGINGFACE_TOKEN!"=="" (
    echo        HUGGINGFACE_TOKEN    : OFF
) else (
    echo        HUGGINGFACE_TOKEN    : ON
)
echo.
echo Membuka browser...
start "" http://localhost:3000
echo.
pause >nul
exit /b 0