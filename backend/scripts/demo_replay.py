"""Local demo mode: the real app with saved Muse Spark outputs instead of model requests.

FAIR's validation and calculations run for real on outputs saved during benchmark runs.
No key is read and no model request can be made: .env is not loaded, the SDK client is blocked,
and non-local connections are refused. The UI labels every result as a replay, never as live.
Only the saved cases in demo_outputs.json answer; any other input gets an error, not a result.

Build the frontend first (frontend/: npm run build), then run from backend/:
    .venv\\Scripts\\python.exe -m scripts.demo_replay
Open http://127.0.0.1:8010

With --earlier-prompt-catch it answers only FAIR-012 with the saved Prompt v4 output, in which the model
wrongly answered MATCH and FAIR's check changed it. The model name carries prompt-v4, so the UI says so.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ["FAIR_DISABLE_DOTENV"] = "1"  # must be set before app.main is imported

import openai  # noqa: E402
from fastapi import FastAPI  # noqa: E402

from app.config import Settings, get_settings  # noqa: E402
from app.main import app, get_meta_client, get_rate_limiter  # noqa: E402
from app.meta_client import MetaClient, ModelUnavailableError  # noqa: E402
from app.ratelimit import RateLimiter  # noqa: E402

OUTPUTS_PATH = Path(__file__).with_name("demo_outputs.json")
V4_OUTPUTS_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "phase12_raw_outputs.json"
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
REPLAY_MODEL = "replay:muse-spark-1.3"  # the frontend labels anything with this prefix as a replay
REPLAY_MODEL_V4 = f"{REPLAY_MODEL}:prompt-v4"  # the frontend also says this answer came from an earlier prompt
PORT = 8010


def replay_client(outputs: list[dict], model: str = REPLAY_MODEL) -> MetaClient:
    def create(**kwargs):
        for case in outputs:
            if all(json.dumps(case[k], ensure_ascii=False) in kwargs["input"] for k in ("terms", "expectation")):
                return SimpleNamespace(output_text=case["raw_output"], status="completed")
        raise ModelUnavailableError("Replay mode only answers its saved demo cases.")

    settings = Settings(api_key="replay-not-a-key", live_calls_enabled=True, model=model)
    return MetaClient(settings, sdk_client=SimpleNamespace(responses=SimpleNamespace(create=create)))


def earlier_prompt_outputs() -> list[dict]:
    current = next(o for o in json.loads(OUTPUTS_PATH.read_text(encoding="utf-8"))["outputs"] if o["case_id"] == "FAIR-012")
    saved = next(o for o in json.loads(V4_OUTPUTS_PATH.read_text(encoding="utf-8"))["outputs"] if o["case_id"] == "FAIR-012")
    return [{"terms": current["terms"], "expectation": current["expectation"], "raw_output": saved["raw_output"]}]


def configure(target: FastAPI, earlier_prompt_catch: bool = False) -> None:
    outputs = earlier_prompt_outputs() if earlier_prompt_catch else json.loads(OUTPUTS_PATH.read_text(encoding="utf-8"))["outputs"]
    model = REPLAY_MODEL_V4 if earlier_prompt_catch else REPLAY_MODEL
    client = replay_client(outputs, model)
    target.dependency_overrides[get_settings] = lambda: client.settings
    target.dependency_overrides[get_meta_client] = lambda: replay_client(outputs, model)
    target.dependency_overrides[get_rate_limiter] = lambda: RateLimiter(0, 0)


def _block_external_access() -> None:
    real_connect = socket.socket.connect

    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and address[0] not in ("127.0.0.1", "::1", "localhost"):
            raise RuntimeError("Replay mode refuses external connections.")
        return real_connect(self, address)

    def no_sdk(*_args, **_kwargs):
        raise RuntimeError("Replay mode never builds a real model client.")

    socket.socket.connect = connect
    openai.OpenAI = no_sdk


def main() -> None:
    import uvicorn
    from fastapi.staticfiles import StaticFiles

    for name in [k for k in os.environ if k.startswith("MODEL_")]:
        del os.environ[name]
    _block_external_access()
    configure(app, "--earlier-prompt-catch" in sys.argv[1:])
    app.mount("/", StaticFiles(directory=str(DIST), html=True))
    print(f"Replay mode, not live: http://127.0.0.1:{PORT}")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
