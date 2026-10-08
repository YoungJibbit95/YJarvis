@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows.ps1" %*
set "setupResult=%ERRORLEVEL%"
if not "%setupResult%"=="0" echo YJarvis Setup fehlgeschlagen. Siehe Fehlermeldung oben.
echo.
echo Anleitung: setup\README.md
pause
exit /b %setupResult%
