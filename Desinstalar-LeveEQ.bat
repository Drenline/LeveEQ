@echo off
rem ==========================================================================
rem  Desinstalador do LeveEQ / LeveEQ uninstaller
rem  Remove o LeveEQ, os atalhos e a configuracao que ele criou no Equalizer APO.
rem  O Equalizer APO em si continua instalado (desinstale pelo Windows se quiser).
rem  Removes LeveEQ, its shortcuts and the Equalizer APO config it created.
rem  Equalizer APO itself stays installed (uninstall it from Windows if you want).
rem ==========================================================================
setlocal EnableExtensions
title Desinstalador do LeveEQ
set "DEST=%LOCALAPPDATA%\Programs\LeveEQ"

echo.
echo  LeveEQ - desinstalador / uninstaller
echo.
choice /c SN /n /m " Remover o LeveEQ deste PC? / Remove LeveEQ from this PC? [S/N] "
if errorlevel 2 goto :end

rem fecha o app se estiver aberto
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'pythonw.exe' -and $_.CommandLine -match 'leveeq' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

rem devolve a configuracao do Equalizer APO como estava antes do LeveEQ
set "APOCFG="
for /f "tokens=2,*" %%a in ('reg query "HKLM\SOFTWARE\EqualizerAPO" /v ConfigPath 2^>nul ^| find "ConfigPath"') do set "APOCFG=%%b"
if not defined APOCFG goto :shortcuts
if exist "%APOCFG%\leveeq.txt" del /q "%APOCFG%\leveeq.txt"
if exist "%APOCFG%\config.txt.antes-leveeq" (
    copy /y "%APOCFG%\config.txt.antes-leveeq" "%APOCFG%\config.txt" >nul
    del /q "%APOCFG%\config.txt.antes-leveeq"
) else (
    type nul > "%APOCFG%\config.txt"
)
echo  Configuracao do Equalizer APO restaurada / Equalizer APO config restored.

:shortcuts
powershell -NoProfile -Command "foreach ($d in 'Desktop','Programs','Startup') { $p = Join-Path ([Environment]::GetFolderPath($d)) 'LeveEQ.lnk'; if (Test-Path $p) { Remove-Item $p -Force } }"
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v LeveEQ /f >nul 2>&1
echo  Atalhos removidos / Shortcuts removed.

choice /c SN /n /m " Apagar tambem seus presets e ajustes? / Also delete your presets and settings? [S/N] "
if not errorlevel 2 (
    if exist "%APPDATA%\LeveEQ" rmdir /s /q "%APPDATA%\LeveEQ"
    echo  Presets apagados / Presets deleted.
)

echo.
echo  LeveEQ removido. / LeveEQ removed.
echo.
pause
rem apaga a pasta do programa por ultimo (este .bat pode estar dentro dela)
cd /d "%TEMP%"
start "" /b cmd /c "ping -n 2 127.0.0.1 >nul & rmdir /s /q "%DEST%""
exit /b

:end
endlocal
