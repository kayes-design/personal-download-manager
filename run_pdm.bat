@echo off
cd /d "%~dp0"
if exist "%~dp0dist\PDM\PDM.exe" (
    start "" "%~dp0dist\PDM\PDM.exe" %*
) else (
    start "" pythonw -m pdm.main %*
)
