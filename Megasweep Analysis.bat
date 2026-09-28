@echo off
setlocal

rem Megasweep Analysis - Windows launcher
rem Creates/updates the local .venv when needed, then runs the GUI app.

cd /d "%~dp0"

set "VENV_DIR=%~dp0.venv"
set "REQ_FILE=%~dp0requirements.txt"
set "ACTIVATE_BAT=%VENV_DIR%\Scripts\activate.bat"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PYTHONW=%VENV_DIR%\Scripts\pythonw.exe"
set "APP_ENTRY=%~dp0main.py"
set "SHORTCUT_SCRIPT=%~dp0Create_Megasweep_Shortcut.ps1"
set "APP_SHORTCUT=%~dp0Megasweep Analysis.lnk"

if not exist "%APP_ENTRY%" (
    echo.
    echo [ERROR] App entry file not found:
    echo         %APP_ENTRY%
    goto error_exit
)

if not exist "%REQ_FILE%" (
    echo.
    echo [ERROR] requirements.txt not found:
    echo         %REQ_FILE%
    goto error_exit
)

if not exist "%VENV_PYTHON%" (
    echo.
    echo [SETUP] Local virtual environment not found. Creating .venv ...

    where py > nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        call py -3 -m venv "%VENV_DIR%"
        goto after_venv_create
    )

    where python > nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        call python -m venv "%VENV_DIR%"
        goto after_venv_create
    )

    echo.
    echo [ERROR] Python was not found on PATH.
    echo         Install Python, then run this launcher again.
    goto error_exit
)

goto activate_and_run

:after_venv_create
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to create .venv.
    goto error_exit
)

if not exist "%VENV_PYTHON%" (
    echo.
    echo [ERROR] .venv creation finished, but python.exe is still missing.
    echo         Expected: %VENV_PYTHON%
    goto error_exit
)

echo [SETUP] Activating .venv ...
call "%ACTIVATE_BAT%"
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to activate .venv.
    goto error_exit
)

echo [SETUP] Upgrading pip ...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to upgrade pip.
    goto error_exit
)

echo [SETUP] Installing requirements ...
python -m pip install -r "%REQ_FILE%"
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install requirements.
    goto error_exit
)

:activate_and_run
echo [SETUP] Activating local .venv ...
call "%ACTIVATE_BAT%"
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to activate .venv.
    echo         Rebuild the environment by deleting .venv and running %~nx0 again.
    goto error_exit
)

if not exist "%VENV_PYTHONW%" (
    echo.
    echo [ERROR] GUI Python launcher not found:
    echo         %VENV_PYTHONW%
    goto error_exit
)

if exist "%SHORTCUT_SCRIPT%" if not exist "%APP_SHORTCUT%" (
    echo [SETUP] Creating Megasweep Analysis shortcut ...
    rem The script defaults AppRoot to its own directory, avoiding a quoted
    rem argument ending in a backslash at the native PowerShell boundary.
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SHORTCUT_SCRIPT%"
    if errorlevel 1 (
        echo [WARNING] Shortcut creation failed. The application can still run.
    )
)

echo [RUN] Starting Megasweep PL Analysis ...
rem START can preserve a previous command's failure code after succeeding.
cmd /c exit 0
start "" "%VENV_PYTHONW%" "%APP_ENTRY%"
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start the application.
    goto error_exit
)

endlocal
exit /b 0

:error_exit
echo.
echo Press any key to close this window...
pause > nul
endlocal
exit /b 1
