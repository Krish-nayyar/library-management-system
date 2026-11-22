@echo off
cd /d "%~dp0"
where py >nul 2>nul && (py -3 app.py & goto :end)
where python >nul 2>nul && (python app.py & goto :end)
echo Python was not found. Install it from https://www.python.org/downloads/ (tick "Add Python to PATH"), then double-click this file again.
:end
pause
