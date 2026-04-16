@echo off
setlocal

rem Backward-compatible wrapper: launch.bat now handles .venv setup too.

cd /d "%~dp0"
call "%~dp0launch.bat"
set "EXIT_CODE=%ERRORLEVEL%"
endlocal
exit /b %EXIT_CODE%
