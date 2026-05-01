"""Netlify Function: wraps the FastAPI app via Mangum for Lambda/API-Gateway."""
import sys
import os

# In Lambda, included_files (auth.py, storage.py, app.py) and pip-installed
# packages all land at the function root alongside api.py.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Lazy-initialize so the module can be imported during bundling without
# requiring app.py and its deps to be present on the bundler's sys.path.
_handler = None


def handler(event, context):
    global _handler
    if _handler is None:
        from mangum import Mangum
        from app import app  # noqa: PLC0415
        _handler = Mangum(app, lifespan="off")
    return _handler(event, context)
