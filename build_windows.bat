@echo off
REM Run this on Windows from the pdfedit folder. Produces dist\PDFEditor\PDFEditor.exe
python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --windowed --name PDFEditor app.py
echo.
echo Done. Your app is in dist\PDFEditor\PDFEditor.exe
pause
