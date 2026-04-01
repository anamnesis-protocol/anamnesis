@echo off
REM demo_testnet.bat — Start the Sovereign AI Context demo server on testnet.
REM
REM Prerequisites:
REM   1. .env.testnet exists with OPERATOR_ID, OPERATOR_KEY, TREASURY_ID, TREASURY_KEY
REM   2. python scripts/init_testnet.py has been run (fills HCS_TOPIC_ID + VALIDATOR_CONTRACT_ID)
REM
REM Then open: http://localhost:8000/demo

cd /d "%~dp0"

if not exist ".env.testnet" (
    echo [ERROR] .env.testnet not found.
    echo   Copy .env.testnet.example to .env.testnet and fill in your testnet credentials.
    echo   Then run: python scripts/init_testnet.py
    pause
    exit /b 1
)

echo Starting Sovereign AI Context demo on TESTNET...
echo Open http://localhost:8000/demo in your browser.
echo.

set SOVEREIGN_ENV=testnet
python -m uvicorn api.main:app --reload --port 8000
