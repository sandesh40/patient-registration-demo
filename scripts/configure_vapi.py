"""Render a safe configuration, or apply it after the public backend is ready."""

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dotenv import dotenv_values, set_key

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.voice.configuration import assistant_configuration  # noqa: E402


def api_request(config, method, path, payload=None):
    request = Request(
        "https://api.vapi.ai" + path,
        method=method,
        headers={
            "Authorization": f"Bearer {config['VAPI_API_KEY']}",
            "User-Agent": "patient-registration-demo/0.2",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload).encode() if payload is not None else None,
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url")
    parser.add_argument("--credential-id")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", default="data/vapi-assistant-preview.json")
    args = parser.parse_args()
    env = dotenv_values(".env")
    credential_id = args.credential_id or env.get("VAPI_SERVER_CREDENTIAL_ID")
    if args.apply and (not args.api_base_url or not credential_id):
        parser.error(
            "--apply requires --api-base-url and --credential-id (or VAPI_SERVER_CREDENTIAL_ID)"
        )
    if args.apply and not env.get("VAPI_WEBHOOK_SECRET"):
        parser.error("--apply requires VAPI_WEBHOOK_SECRET in .env")
    config = assistant_configuration(
        api_base_url=args.api_base_url,
        credential_id=credential_id,
        model=env.get("VAPI_MODEL") or "gemini-2.5-flash",
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(config, indent=2) + "\n")
    print(f"Configuration preview written to {output}; no private API keys included.")
    if not args.apply:
        return
    # Check backend reachability and webhook auth before altering the live assistant.
    with urlopen(args.api_base_url.rstrip("/") + "/ready", timeout=30) as response:
        if json.load(response).get("data", {}).get("status") != "ready":
            raise SystemExit("Backend is not ready; assistant was not changed.")
    probe = Request(
        args.api_base_url.rstrip("/") + "/vapi/webhook",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {env['VAPI_WEBHOOK_SECRET']}",
        },
        data=json.dumps(
            {"message": {"type": "configuration-check", "call": {"id": "config-probe"}}}
        ).encode(),
    )
    with urlopen(probe, timeout=30) as response:
        if not json.load(response).get("data", {}).get("received"):
            raise SystemExit("Webhook check failed; assistant was not changed.")
    previous = api_request(env, "GET", f"/assistant/{env['VAPI_ASSISTANT_ID']}")
    backup = Path("data/vapi-assistant-before-update.json")
    backup.write_text(json.dumps(previous, indent=2) + "\n")
    backup.chmod(0o600)
    api_request(env, "PATCH", f"/assistant/{env['VAPI_ASSISTANT_ID']}", config)
    api_request(
        env,
        "PATCH",
        f"/phone-number/{env['VAPI_PHONE_NUMBER_ID']}",
        {"assistantId": env["VAPI_ASSISTANT_ID"]},
    )
    set_key(".env", "VAPI_SERVER_CREDENTIAL_ID", credential_id)
    print(
        "Assistant configuration and phone routing updated. "
        "A real conversation test is still required."
    )


if __name__ == "__main__":
    try:
        main()
    except HTTPError as exc:
        print(
            f"Vapi or backend HTTP error {exc.code}; credentials were not printed.", file=sys.stderr
        )
        raise SystemExit(1) from None
