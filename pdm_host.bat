@echo off
cd /d "%~dp0"
python -u -m pdm.browser_bridge.native_host
