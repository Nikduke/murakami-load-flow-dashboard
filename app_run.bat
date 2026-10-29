@echo off
setlocal
set "APP_DIR=%~dp0"
set "APP_PYTHON=%APP_DIR%.venv\Scripts\python.exe"

if not exist "%APP_PYTHON%" (
    echo The dashboard environment was not found at:
    echo   %APP_DIR%.venv
    echo Create the Python 3.12 environment and install requirements first.
    echo See README.md for setup instructions.
    pause
    exit /b 1
)

cd /d "%APP_DIR%"
"%APP_PYTHON%" -m streamlit run app.py --server.address=127.0.0.1
endlocal
