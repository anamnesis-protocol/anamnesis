@echo off
REM demo_mainnet.bat — Start the Sovereign AI Context demo server on mainnet.
REM
REM Prerequisites: .env exists with OPERATOR_ID, OPERATOR_KEY, TREASURY_ID, TREASURY_KEY,
REM                HCS_TOPIC_ID, VALIDATOR_CONTRACT_ID (populated by scripts/init_mainnet.py)
REM
REM Then open: http://localhost:8001/demo
REM
REM For the full split demo (Demo Mode=testnet, HashPack=mainnet), use demo_both.bat instead.

cd /d "%~dp0"

if not exist ".env" (
    echo [ERROR] .env not found.
    echo   Run scripts/init_mainnet.py to set up the mainnet deployment.
    pause
    exit /b 1
)

echo Starting Sovereign AI Context demo on MAINNET (port 8001)...
echo Open http://localhost:8001/demo in your browser.
echo.

set SOVEREIGN_ENV=mainnet
python -m uvicorn api.main:app --reload --port 8001
