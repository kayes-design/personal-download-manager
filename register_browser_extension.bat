@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo   Registering PDM Native Messaging Host for Chrome/Edge
echo ========================================================

set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"
set "HOST_BAT=%BASE_DIR%\pdm_host.bat"
set "JSON_PATH=%BASE_DIR%\pdm\browser_bridge\com.pdm.native_host.json"

:: Escape backslashes for JSON
set "ESCAPED_PATH=%HOST_BAT:\=\\%"

:: Generate JSON host manifest
(
echo {
echo   "name": "com.pdm.native_host",
echo   "description": "Personal Download Manager Native Messaging Host",
echo   "path": "!ESCAPED_PATH!",
echo   "type": "stdio",
echo   "allowed_origins": [
echo     "chrome-extension://flgedopgbfolfficdllcjacamhgkhkga/",
echo     "chrome-extension://jdkngeepecifohmmoeldklojellkdgmm/"
echo   ]
echo }
) > "%JSON_PATH%"

:: Register in Chrome
reg add "HKCU\Software\Google\Chrome\NativeMessagingHosts\com.pdm.native_host" /ve /t REG_SZ /d "%JSON_PATH%" /f >nul

:: Register in Microsoft Edge
reg add "HKCU\Software\Microsoft\Edge\NativeMessagingHosts\com.pdm.native_host" /ve /t REG_SZ /d "%JSON_PATH%" /f >nul

:: Register in Opera / Opera GX
reg add "HKCU\Software\Opera Software\NativeMessagingHosts\com.pdm.native_host" /ve /t REG_SZ /d "%JSON_PATH%" /f >nul
reg add "HKCU\Software\Opera Software\Opera GX Stable\NativeMessagingHosts\com.pdm.native_host" /ve /t REG_SZ /d "%JSON_PATH%" /f >nul
reg add "HKCU\Software\Opera Software\Opera Stable\NativeMessagingHosts\com.pdm.native_host" /ve /t REG_SZ /d "%JSON_PATH%" /f >nul
echo [OK] Registered with Opera GX, Chrome, and Edge.

echo.
echo ========================================================
echo   HOW TO ENABLE IN CHROME / EDGE:
echo ========================================================
echo 1. Open your browser and go to:
echo      chrome://extensions   (for Chrome)
echo      edge://extensions     (for Edge)
echo.
echo 2. Enable "Developer mode" in the top-right corner.
echo.
echo 3. Click "Load unpacked" and select this folder:
echo      %BASE_DIR%\extension
echo.
echo Done! Now any download clicked in the browser or
echo right-click "Download with PDM" will directly send to PDM!
echo ========================================================
echo.
pause
