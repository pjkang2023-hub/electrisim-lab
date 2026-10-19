@echo off
rem The electrisim-lab dashboard on http://127.0.0.1:8502 (this machine only).
rem Electrisim's own servers keep 5000 and 5501; this does not touch them.
cd /d "%~dp0"
echo Electrisim lab dashboard -^> http://127.0.0.1:8502/   (Ctrl+C to stop)
".venv\Scripts\streamlit.exe" run dashboard\app.py
