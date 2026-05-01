"""Netlify Function: wraps the FastAPI app via Mangum for Lambda/API-Gateway."""
import sys
import os

# Add project root to path so we can import app.py, auth.py, etc.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from mangum import Mangum
from app import app

handler = Mangum(app, lifespan="off")
