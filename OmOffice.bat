@echo off
setlocal
rem OmOffice launcher. First run: creates .venv and installs requirements.
rem Keep this file ASCII: cmd.exe does not read UTF-8 batch files reliably.
set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"
set "STAMP=%VENV%\requirements.installed"

if not exist "%VENV%\Scripts\pythonw.exe" goto setup
fc /b "%ROOT%requirements.txt" "%STAMP%" >nul 2>&1
if errorlevel 1 goto setup
goto run

:setup
title OmOffice kurulumu
echo OmOffice hazirlaniyor. Ilk kurulum internet ister ve birkac dakika surebilir...
if exist "%VENV%\Scripts\python.exe" goto install

set "BASE="
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 set "BASE=py -3.12"
if defined BASE goto mkvenv
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 set "BASE=python"
if defined BASE goto mkvenv
echo.
echo Python bulunamadi. Python 3.12 kurun: https://www.python.org/downloads/
echo Kurulumda "Add python.exe to PATH" secenegini isaretleyin, sonra tekrar deneyin.
goto fail

:mkvenv
%BASE% -m venv "%VENV%"
if errorlevel 1 goto fail

:install
"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -r "%ROOT%requirements.txt"
if errorlevel 1 goto fail
copy /y "%ROOT%requirements.txt" "%STAMP%" >nul
if errorlevel 1 goto fail

:run
rem Do not cd: relative file arguments must keep resolving from the caller's folder.
set "PYTHONPATH=%ROOT%"
start "" "%VENV%\Scripts\pythonw.exe" -m omoffice %*
exit /b 0

:fail
echo.
echo Kurulum tamamlanamadi. Yukaridaki hata mesajina bakin.
pause
exit /b 1
