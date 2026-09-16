"""Verify a deployed API and voice save with fictional data, without placing a call."""

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    args = parser.parse_args()
    if not args.base_url.startswith("https://"):
        parser.error("An HTTPS deployment URL is required")
    base = args.base_url.rstrip("/")
    env = dotenv_values(".env")
    call_id = f"deployment-smoke-{uuid4()}"

    def request(method, path, payload=None, token=None):
        headers = {"Content-Type": "application/json", "User-Agent": "patient-demo-check/0.3"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = Request(
            base + path,
            method=method,
            headers=headers,
            data=json.dumps(payload).encode() if payload is not None else None,
        )
        try:
            with urlopen(req, timeout=45) as response:
                body = response.read()
                return response.status, json.loads(body) if "json" in response.headers.get(
                    "Content-Type", ""
                ) else body.decode()
        except HTTPError as exc:
            return exc.code, None

    def tool(name, arguments, tool_id=None):
        status, response = request(
            "POST",
            "/vapi/webhook",
            {
                "message": {
                    "type": "tool-calls",
                    "call": {"id": call_id, "assistantId": env["VAPI_ASSISTANT_ID"]},
                    "toolCallList": [
                        {
                            "id": tool_id or str(uuid4()),
                            "function": {"name": name, "arguments": arguments},
                        }
                    ],
                }
            },
            env["VAPI_WEBHOOK_SECRET"],
        )
        assert status == 200, f"Webhook HTTP {status}"
        result = json.loads(response["results"][0]["result"])
        assert result["ok"], "Tool returned failure"
        return result

    for path in [
        "/",
        "/assets/demo.js",
        "/assets/demo.css",
        "/health",
        "/ready",
        "/docs",
        "/openapi.json",
    ]:
        status, _ = request("GET", path)
        assert status == 200, f"{path}: HTTP {status}"
    assert request("GET", "/patients")[0] == 401
    assert (
        request(
            "POST",
            "/vapi/webhook",
            {"message": {"type": "configuration-check", "call": {"id": call_id}}},
        )[0]
        == 401
    )
    for path in ["/.env", "/.env.local", "/data/vercel-auth/auth.json"]:
        assert request("GET", path)[0] == 404, "Private file route unexpectedly accessible"
    _, config = request("GET", "/demo/config")
    assert set(config["data"]) == {"enabled", "public_key", "assistant_id"}
    print("PASS: public site/assets/docs, database readiness, auth, secret-file exclusion")

    patient_id = None
    try:
        patient = json.loads(Path("examples/patient.json").read_text())
        patient.update(first_name="Deployment", last_name="Smoke", phone_number="2025550198")
        draft = tool("prepare_registration", {"patient": patient})
        status, results = request(
            "GET", "/patients?last_name=Smoke&phone_number=2025550198", token=env["API_AUTH_TOKEN"]
        )
        assert status == 200 and not results["data"], "Preparation unexpectedly created a patient"
        confirmation = {"confirmation_token": draft["confirmation_token"], "confirmed": True}
        saved = tool("confirm_registration", confirmation, "confirm-once")
        patient_id = saved["patient"]["patient_id"]
        assert tool("confirm_registration", confirmation, "confirm-once") == saved
        status, loaded = request("GET", f"/patients/{patient_id}", token=env["API_AUTH_TOKEN"])
        assert status == 200 and loaded["data"]["first_name"] == "Deployment"
        print("PASS: public webhook preparation, confirmed save, retry, REST retrieval")
    finally:
        if patient_id:
            status, _ = request("DELETE", f"/patients/{patient_id}", token=env["API_AUTH_TOKEN"])
            assert status == 200, "Synthetic patient cleanup failed"
            assert request("GET", f"/patients/{patient_id}", token=env["API_AUTH_TOKEN"])[0] == 404
            print("PASS: synthetic patient soft-deleted")
    print("Deployment smoke test passed. No Vapi call or audio test was performed.")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, HTTPError, URLError, OSError, ValueError, KeyError) as exc:
        # Don't echo raw HTTP responses or exceptions containing request credentials.
        print(
            f"Deployment check failed ({type(exc).__name__}); inspect the failed step.",
            file=sys.stderr,
        )
        if isinstance(exc, AssertionError):
            print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
