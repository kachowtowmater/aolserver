@echo off
rem Start the aolserver host.  Close this window or press Ctrl+C to stop.
cd /d "%~dp0\..\.."
python start.py %*
if errorlevel 9009 py start.py %*
