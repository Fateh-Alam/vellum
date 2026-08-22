"""Small safe JSON transport helper for Anki WebViews."""

from __future__ import annotations

import base64
import json
from typing import Any


def encoded_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")
