"""
api/limiter.py — Shared rate limiter instance (slowapi).

Import `limiter` from here in every route file that needs rate limiting.
Register on `app` in main.py.

Storage: in-memory (default). Works correctly for a single-process deployment
(Railway with one uvicorn worker). For multi-worker/multi-instance deployments,
switch to Redis storage:
 limiter = Limiter(key_func=get_remote_address, storage_uri="redis://...")

Rate limiting is automatically disabled in testnet mode (SOVEREIGN_ENV=testnet)
so that test suites are not rate-throttled by the in-memory store.
"""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

_testnet = os.getenv("SOVEREIGN_ENV", "").strip().lower() == "testnet"

limiter = Limiter(key_func=get_remote_address, enabled=not _testnet)
