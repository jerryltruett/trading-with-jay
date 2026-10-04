@echo off
setlocal
title Trading with Jay - Local Website
cd /d "%~dp0"
if errorlevel 1 (
  echo The website folder could not be opened.
  pause
  exit /b 1
)
if not exist "%~dp0.runtime\python\python.exe" (
  echo The bundled Python program is missing. Keep the entire website folder together.
  pause
  exit /b 1
)
echo Starting Trading with Jay...
echo Open http://127.0.0.1:8002/ in your browser.
echo Keep this window open while using the website.
echo Press Ctrl+C to stop the website.
echo.
"%~dp0.runtime\python\python.exe" -I -B "%~dp0manage.py" runserver 127.0.0.1:8002 --noreload
echo.
echo The website server has stopped. If the port was already in use, the website may already be running.
pause
