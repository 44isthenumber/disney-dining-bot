"""Netlify Function: wraps the FastAPI app via Mangum for Lambda/API-Gateway."""
import sys
import os

# In Lambda, all files are at the function root. Packages are in packages/.
_fn_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _fn_dir)
sys.path.insert(0, os.path.join(_fn_dir, "packages"))

from mangum import Mangum
from app import app

_mangum = Mangum(app, lifespan="off")


def handler(event, context):
    return _mangum(event, context)
