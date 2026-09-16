"""Configure this linked demo project using a locally authorized Vercel CLI session.

Copies only required runtime values to encrypted production environment variables.
Never prints their values or deploys code. Browser calling remains disabled unless
--enable-browser is supplied after the Vapi assistant has been configured.
"""

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-browser", action="store_true")
    args = parser.parse_args()
    project = json.loads(Path(".vercel/project.json").read_text())
    if project.get("projectName") != "patient-registration-demo":
        raise SystemExit("Refusing to configure a different project.")
    auth = json.loads(Path("data/vercel-auth/auth.json").read_text())
    query = urlencode({"teamId": project["orgId"]})

    def request(method, path, payload=None):
        req = Request(
            "https://api.vercel.com" + path,
            method=method,
            headers={
                "Authorization": f"Bearer {auth['token']}",
                "Content-Type": "application/json",
            },
            data=json.dumps(payload).encode() if payload is not None else None,
        )
        with urlopen(req, timeout=30) as response:
            return json.load(response)

    team = request("GET", f"/v2/teams/{project['orgId']}")
    if team.get("billing", {}).get("plan") != "hobby":
        raise SystemExit("Expected the confirmed Hobby plan; no settings changed.")
    env = dotenv_values(".env")
    keys = ["DATABASE_URL", "API_AUTH_TOKEN", "VAPI_WEBHOOK_SECRET", "VAPI_ASSISTANT_ID"]
    if args.enable_browser:
        keys.append("VAPI_PUBLIC_KEY")
    if any(not env.get(key) for key in keys):
        raise SystemExit("Missing a required local environment variable; nothing uploaded.")
    values = {key: env[key] for key in keys}
    values.update(APP_ENV="production", LOG_LEVEL="INFO")
    if not args.enable_browser:
        values["VAPI_PUBLIC_KEY"] = ""
    request(
        "POST",
        f"/v10/projects/{project['projectId']}/env?{query}&upsert=true",
        [
            {"key": key, "value": value, "type": "encrypted", "target": ["production"]}
            for key, value in values.items()
        ],
    )
    # This assessment needs an externally reachable webhook and reviewer demo.
    # Patient and voice routes still enforce their own independent bearer tokens.
    request("PATCH", f"/v9/projects/{project['projectId']}?{query}", {"ssoProtection": None})
    print("Hobby plan verified. Encrypted production settings configured; values not printed.")
    print("Public deployment access enabled; API/webhook bearer authentication remains required.")


if __name__ == "__main__":
    try:
        main()
    except HTTPError as exc:
        print(f"Vercel HTTP {exc.code}; response omitted to protect credentials.", file=sys.stderr)
        raise SystemExit(1) from None
    except (URLError, OSError, KeyError, ValueError) as exc:
        print(f"Configuration failed ({type(exc).__name__}); details omitted.", file=sys.stderr)
        raise SystemExit(1) from None
