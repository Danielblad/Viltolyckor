@echo off
cd /d "%~dp0"
echo Hamtar farsk viltolycksdata...
echo.
python hamta_ny_data.py
echo.
echo Klart! Stang detta fonster nar du last klart ovanstaende.
pause
