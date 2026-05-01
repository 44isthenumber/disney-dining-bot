#!/usr/bin/env python3
"""
Deploy to Netlify via REST API: static files + hand-built Python Lambda ZIPs.
Bypasses zip-it-and-ship-it, which has never supported Python.

Usage (in CI):
  pip install -r netlify/functions/requirements.txt -t /tmp/lambda_pkg
  NETLIFY_AUTH_TOKEN=... python _netlify_deploy.py
"""
import hashlib
import io
import json
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

SITE_ID = "b1f7efc5-da94-4159-ade0-568de33ed24f"
API = "https://api.netlify.com/api/v1"
TOKEN = os.environ["NETLIFY_AUTH_TOKEN"]
LAMBDA_PKG = Path(os.environ.get("LAMBDA_PKG", "/tmp/lambda_pkg"))


def sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def api_call(method: str, path: str, body=None, content_type="application/json"):
    url = API + path
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": content_type,
    }
    if isinstance(body, dict):
        data = json.dumps(body).encode()
    elif isinstance(body, bytes):
        data = body
    else:
        data = None

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        print(f"  HTTP {e.code} from {method} {url}: {body_text[:300]}", file=sys.stderr)
        raise


def build_zip(func_py: Path, pkg_dir: Path, extras: dict) -> bytes:
    """Create a Lambda-ready ZIP: handler + installed packages + extra files."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(func_py, func_py.name)
        for arc_name, src in extras.items():
            src = Path(src)
            if src.exists():
                zf.write(src, arc_name)
        if pkg_dir.exists():
            for f in pkg_dir.rglob("*"):
                if f.is_file():
                    # skip dist-info / __pycache__ to keep the zip lean
                    rel = f.relative_to(pkg_dir)
                    parts = rel.parts
                    if any(p.endswith(".dist-info") or p == "__pycache__" for p in parts):
                        continue
                    zf.write(f, rel)
    return buf.getvalue()


def main():
    # ── 1. Hash static files ──────────────────────────────────────────────────
    static: dict[str, str] = {}
    static_content: dict[str, tuple[str, bytes]] = {}
    public = Path("public")
    for p in sorted(public.rglob("*")):
        if p.is_file():
            data = p.read_bytes()
            site_path = "/" + p.relative_to(public).as_posix()
            h = sha1(data)
            static[site_path] = h
            static_content[h] = (site_path, data)
    print(f"[static] {len(static)} files")

    # ── 2. Build function ZIPs ────────────────────────────────────────────────
    funcs_dir = Path("netlify/functions")
    # Files to include in EVERY Python function bundle
    shared_extras = {
        "auth.py": "auth.py",
        "storage.py": "storage.py",
        "app.py": "app.py",
        "restaurants.json": "public/restaurants.json",
    }

    func_zips: dict[str, tuple[str, bytes]] = {}
    for py_file in sorted(funcs_dir.glob("*.py")):
        fname = py_file.stem
        if fname == "ping":
            # Minimal diagnostics function — no deps needed
            zip_bytes = build_zip(py_file, Path("/nonexistent"), {})
        else:
            zip_bytes = build_zip(py_file, LAMBDA_PKG, shared_extras)
        h = sha1(zip_bytes)
        func_zips[fname] = (h, zip_bytes)
        print(f"[func]   {fname}.zip  {len(zip_bytes) // 1024}KB  sha={h[:8]}")

    # ── 3. Create deploy (send SHA digest lists) ──────────────────────────────
    deploy = api_call(
        "POST",
        f"/sites/{SITE_ID}/deploys",
        body={
            "files": static,
            "functions": {name: h for name, (h, _) in func_zips.items()},
        },
    )
    deploy_id = deploy["id"]
    print(f"[deploy] id={deploy_id}  state={deploy['state']}")

    # ── 4. Upload required static files ──────────────────────────────────────
    required = set(deploy.get("required", []))
    for h, (path, data) in static_content.items():
        if h in required:
            api_call("PUT", f"/deploys/{deploy_id}/files{path}", body=data,
                     content_type="application/octet-stream")
            print(f"[upload] {path}")

    # ── 5. Upload required function ZIPs ─────────────────────────────────────
    # runtime=python3.9 is required — the Netlify API maps this to the Lambda runtime.
    required_funcs = set(deploy.get("required_functions", []))
    for fname, (h, zip_bytes) in func_zips.items():
        if h in required_funcs:
            api_call("PUT", f"/deploys/{deploy_id}/functions/{fname}?runtime=python3.9",
                     body=zip_bytes, content_type="application/zip")
            print(f"[upload] function/{fname}")

    url = deploy.get("ssl_url") or deploy.get("url") or ""
    print(f"[done]   {url}")


if __name__ == "__main__":
    main()
