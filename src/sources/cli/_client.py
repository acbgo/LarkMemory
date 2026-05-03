from __future__ import annotations

import json
import os
import urllib.request
from typing import Any


def get_api_base() -> str:
    return os.environ.get("LARKMEMORY_API_BASE", "http://127.0.0.1:8765")


def post_ingest(payload: dict[str, Any]) -> bool:
    url = f"{get_api_base().rstrip('/')}/api/v1/ingest"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=2)
    return True


def post_retrieve(payload: dict[str, Any]) -> list[dict[str, Any]]:
    url = f"{get_api_base().rstrip('/')}/api/v1/retrieve"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=5)
    body = json.loads(resp.read().decode("utf-8"))
    return body.get("results") or []
