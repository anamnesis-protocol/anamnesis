@echo off
REM demo_both.bat — Start BOTH servers for the split demo:
REM
REM   Port 8000  →  testnet  →  Demo Mode (operator key signs, no wallet, no HBAR cost)
REM   Port 8001  →  mainnet  →  HashPack Mode (real wallet signs, real Hedera)
REM
REM Prerequisites:
REM   .env.testnet  — testnet credentials (HCS_TOPIC_ID + VALIDATOR_CONTRACT_ID filled in)
REM   .env          — mainnet credentials (HCS_TOPIC_ID + VALIDATOR_CONTRACT_ID filled in)
REM
REM Then open: http://localhost:8000/demo  (serves the frontend; API routes by mode)

cd /d "%~dp0"

if not exist ".env.testnet" (
    echo [ERROR] .env.testnet not found. Run demo_testnet.bat setup first.
    pause
    exit /b 1
)
if not exist ".env" (
    echo [ERROR] .env not found. Run scripts/init_mainnet.py first.
    pause
    exit /b 1
)

echo Starting testnet server on port 8000...
start "Sovereign AI — Testnet :8000" cmd /k "cd /d %~dp0 && set SOVEREIGN_ENV=testnet && python -m uvicorn api.main:app --port 8000"

echo Starting mainnet server on port 8001...
start "Sovereign AI — Mainnet :8001" cmd /k "cd /d %~dp0 && python -m uvicorn api.main:app --port 8001"

echo.
echo Both servers starting. Open http://localhost:8000/demo in your browser.
echo   Demo Mode   ^(testnet^)  →  port 8000
echo   HashPack    ^(mainnet^)  →  port 8001
echo.
pause
