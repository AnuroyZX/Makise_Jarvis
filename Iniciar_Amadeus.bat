@echo off
setlocal
title Amadeus System // Makise Kurisu

:: Clean any inherited Node/Electron environment flags
set ELECTRON_RUN_AS_NODE=

for %%I in ("%~dp0desktop") do set "DESKTOP_DIR=%%~fI"
if exist "%DESKTOP_DIR%\node_modules\electron\dist\electron.exe" (
    start "" "%DESKTOP_DIR%\node_modules\electron\dist\electron.exe" "%DESKTOP_DIR%"
    exit /b 0
)

if exist "%~dp0dist\AmadeusKurisu\AmadeusKurisu.exe" (
    start "" "%~dp0dist\AmadeusKurisu\AmadeusKurisu.exe" --onboarding
    exit /b 0
)

echo [!] Error: No se encontro el entorno de escritorio ni AmadeusKurisu.exe.
pause
