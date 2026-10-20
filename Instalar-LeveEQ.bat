@echo off
rem ==========================================================================
rem  Instalador do LeveEQ / LeveEQ installer
rem  Codigo aberto: leia este arquivo antes de rodar, ele so faz o que esta aqui.
rem  Open source: read this file before running it, it only does what is here.
rem
rem  O que ele faz / What it does:
rem   1. Procura o Python 3.8+ (se nao tiver, oferece instalar pelo winget)
rem   2. Instala as bibliotecas pystray e pillow (icone na bandeja)
rem   3. Copia o LeveEQ para %LOCALAPPDATA%\Programs\LeveEQ (sem precisar de admin)
rem   4. Cria atalhos na Area de Trabalho e no menu Iniciar
rem   5. Verifica se o Equalizer APO esta instalado
rem ==========================================================================
setlocal EnableExtensions
title Instalador do LeveEQ
cd /d "%~dp0"
set "DEST=%LOCALAPPDATA%\Programs\LeveEQ"

echo.
echo  =============================================
echo   LeveEQ - instalador / installer
echo  =============================================
echo.

if not exist "%~dp0leveeq.pyw" (
    echo  [ERRO] leveeq.pyw nao encontrado ao lado deste .bat.
    echo         Extraia o ZIP inteiro antes de rodar o instalador.
    echo  [ERROR] leveeq.pyw not found. Extract the whole ZIP first.
    goto :fail
)

rem ---------------------------------------------------------------- Python
echo  [1/5] Procurando o Python / Looking for Python...
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY goto :nopython

%PY% -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Seu Python nao tem o Tkinter. Reinstale o Python marcando "tcl/tk and IDLE".
    echo  [ERROR] Your Python has no Tkinter. Reinstall Python with "tcl/tk and IDLE".
    goto :fail
)

for /f "usebackq delims=" %%i in (`%PY% -c "import sys, os; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))"`) do set "PYW=%%i"
if not exist "%PYW%" goto :nopythonw
echo         OK: %PYW%

rem ---------------------------------------------------------------- bibliotecas
echo  [2/5] Instalando bibliotecas / Installing libraries (pystray, pillow)...
%PY% -m pip install --user --disable-pip-version-check --quiet -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo  [ERRO] Falha ao instalar as bibliotecas. Verifique sua internet.
    echo  [ERROR] Could not install the libraries. Check your internet connection.
    goto :fail
)

rem ---------------------------------------------------------------- arquivos
echo  [3/5] Copiando arquivos / Copying files to %DEST%...
rem fecha o LeveEQ se ele estiver aberto (para poder atualizar)
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'pythonw.exe' -and $_.CommandLine -match 'leveeq' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
if not exist "%DEST%" mkdir "%DEST%"
copy /y "%~dp0leveeq.pyw" "%DEST%\leveeq.pyw" >nul || goto :fail
if exist "%~dp0LICENSE" copy /y "%~dp0LICENSE" "%DEST%\LICENSE" >nul
if exist "%~dp0README.md" copy /y "%~dp0README.md" "%DEST%\README.md" >nul
copy /y "%~dp0Desinstalar-LeveEQ.bat" "%DEST%\Desinstalar-LeveEQ.bat" >nul
%PY% "%DEST%\leveeq.pyw" --make-icon "%DEST%\leveeq.ico"
if errorlevel 1 echo         (aviso: icone nao gerado / warning: icon not created)

rem ---------------------------------------------------------------- atalhos
echo  [4/5] Criando atalhos / Creating shortcuts...
set "LNK_DIRS='Desktop','Programs'"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$q=[char]34; $ws=New-Object -ComObject WScript.Shell; foreach ($d in @(%LNK_DIRS%)) { $s=$ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath($d)) 'LeveEQ.lnk')); $s.TargetPath=$env:PYW; $s.Arguments=$q+$env:DEST+'\leveeq.pyw'+$q; $s.WorkingDirectory=$env:DEST; $s.IconLocation=$env:DEST+'\leveeq.ico,0'; $s.Description='LeveEQ - equalizador de fone e microfone'; $s.Save() }"
if errorlevel 1 (
    echo  [ERRO] Nao consegui criar os atalhos / Could not create shortcuts.
    goto :fail
)

rem iniciar com o Windows: mesma chave do registro que o app usa (abre direto na bandeja).
rem Pode ser ligado/desligado depois pelo proprio LeveEQ.
set "RUNKEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\LeveEQ.lnk" >nul 2>&1
choice /c SN /n /m "         Abrir o LeveEQ junto com o Windows? / Start with Windows? [S/N] "
if errorlevel 2 goto :no_autostart
reg add "%RUNKEY%" /v LeveEQ /t REG_SZ /d "\"%PYW%\" \"%DEST%\leveeq.pyw\" --tray" /f >nul
goto :after_autostart
:no_autostart
reg delete "%RUNKEY%" /v LeveEQ /f >nul 2>&1
:after_autostart

rem ---------------------------------------------------------------- Equalizer APO
echo  [5/5] Verificando o Equalizer APO / Checking Equalizer APO...
reg query "HKLM\SOFTWARE\EqualizerAPO" /v ConfigPath >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ---------------------------------------------------------------
    echo   O Equalizer APO NAO esta instalado. Ele e o motor de audio que
    echo   o LeveEQ controla - gratuito e de codigo aberto.
    echo     1. Baixe e instale pela pagina que vai abrir agora
    echo     2. No "Configurator", marque seu fone e seu microfone
    echo     3. Reinicie o PC
    echo.
    echo   Equalizer APO is NOT installed. It is the free, open source
    echo   audio engine LeveEQ controls. Install it from the page that
    echo   will open, select your headphones and microphone in the
    echo   Configurator, then restart your PC.
    echo  ---------------------------------------------------------------
    start "" "https://sourceforge.net/projects/equalizerapo/"
) else (
    echo         OK: Equalizer APO encontrado / found.
)

echo.
echo  Pronto! / Done! O LeveEQ foi instalado em / was installed to:
echo    %DEST%
echo.
choice /c SN /n /m " Abrir o LeveEQ agora? / Open LeveEQ now? [S/N] "
rem abre pelo atalho via Explorer, separado desta janela (fechar o instalador nao fecha o app)
if not errorlevel 2 powershell -NoProfile -Command "$q=[char]34; Start-Process explorer.exe -ArgumentList ($q + (Join-Path ([Environment]::GetFolderPath('Programs')) 'LeveEQ.lnk') + $q)"
goto :end

rem ---------------------------------------------------------------- sem Python
:nopython
echo.
echo  O Python 3.8 ou mais novo nao foi encontrado.
echo  Python 3.8 or newer was not found.
echo.
where winget >nul 2>&1
if errorlevel 1 goto :python_site
choice /c SN /n /m " Instalar o Python 3.12 agora pelo winget? / Install Python 3.12 now with winget? [S/N] "
if errorlevel 2 goto :python_site
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
echo.
echo  Python instalado. FECHE esta janela e rode o instalador de novo.
echo  Python installed. CLOSE this window and run the installer again.
goto :end

:python_site
echo  Instale o Python pelo site que vai abrir (marque "Add python.exe to PATH")
echo  e depois rode este instalador de novo.
echo  Install Python from the site that will open (check "Add python.exe to PATH")
echo  and run this installer again.
start "" "https://www.python.org/downloads/windows/"
goto :end

:nopythonw
echo  [ERRO] pythonw.exe nao encontrado / not found:
echo         "%PYW%"

:fail
echo.
echo  A instalacao nao terminou. / Installation did not finish.

:end
echo.
pause
endlocal
