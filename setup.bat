@echo off
setlocal
cd /d "%~dp0"
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 goto fail
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto fail
".venv\Scripts\dy.exe" --version
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m dy_cli.utils.browser
if errorlevel 1 goto fail
echo Installed. Run .venv\Scripts\dy.exe login to sign in yourself.
exit /b 0
:fail
echo Installation failed. Check the error above. Python 3.10+ and Google Chrome are required.
exit /b 1
