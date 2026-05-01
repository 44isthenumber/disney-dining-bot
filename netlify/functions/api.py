"""Netlify Function: wraps the FastAPI app via Mangum for Lambda/API-Gateway."""
import sys
import os

# In Lambda, included_files (auth.py, storage.py, app.py) and pip-installed
# packages all land at the function root alongside api.py.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mangum import Mangum
from app import app

_mangum = Mangum(app, lifespan="off")


def handler(event, context):
    return _mangum(event, context)
