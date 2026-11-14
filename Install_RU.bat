@echo off
chcp 65001 >nul
setlocal
set "PYTHONUTF8=1"
if exist "%~dp0runtime\python.exe" (
  "%~dp0runtime\python.exe" "%~dp0installer\existing.py" %*
) else (
  python "%~dp0installer\existing.py" %*
)
set "RESULT=%ERRORLEVEL%"
if "%~1"=="" pause
exit /b %RESULT%
