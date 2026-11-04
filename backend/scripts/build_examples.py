"""Writes the saved examples the website shows, by running saved Muse Spark outputs through FAIR's real pipeline.

No key is read and no model request can be made (see scripts/demo_replay.py). Run from backend/:
    .venv\\Scripts\\python.exe -m scripts.build_examples
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from scripts.demo_replay import OUTPUTS_PATH, _block_external_access, configure

TARGET = Path(__file__).resolve().parents[2] / "frontend" / "src" / "examples" / "saved_examples.json"


def build() -> dict:
    configure(app)
    client = TestClient(app)
    cases = []
    for case in json.loads(OUTPUTS_PATH.read_text(encoding="utf-8"))["outputs"]:
        response = client.post("/api/analyze", json={"terms": case["terms"], "expectation": case["expectation"], "language": "en"})
        response.raise_for_status()
        cases.append({"id": case["case_id"], "terms": case["terms"], "expectation": case["expectation"], "response": response.json()})
    return {"note": "Synthetic offers and recorded Muse Spark outputs, processed by FAIR's checks when this file was built. Not live.", "cases": cases}


if __name__ == "__main__":
    _block_external_access()
    TARGET.parent.mkdir(exist_ok=True)
    TARGET.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {TARGET}")
