"""Read-only connection check; print identifiers/status, never credentials or patient data."""

import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import build_engine  # noqa: E402


def main() -> int:
    config = dotenv_values(".env")
    failed = False
    for resource, key in (
        ("assistant", "VAPI_ASSISTANT_ID"),
        ("phone-number", "VAPI_PHONE_NUMBER_ID"),
    ):
        request = Request(
            f"https://api.vapi.ai/{resource}/{config[key]}",
            headers={
                "Authorization": f"Bearer {config['VAPI_API_KEY']}",
                "User-Agent": "patient-registration-demo/0.2",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                value = json.load(response)
            safe = {
                key: value.get(key) for key in ("id", "name", "number", "assistantId", "status")
            }
            if resource == "assistant":
                safe["model"] = {
                    key: value.get("model", {}).get(key) for key in ("provider", "model")
                }
                safe["voice"] = {
                    key: value.get("voice", {}).get(key) for key in ("provider", "voiceId")
                }
                safe["has_server_url"] = bool(value.get("server", {}).get("url"))
            print(json.dumps({resource: safe}))
        except HTTPError as exc:
            print(f"{resource}: HTTP {exc.code}")
            detail = exc.read(4096).decode("utf-8", errors="replace")
            for value in config.values():
                if value and len(value) > 8:
                    detail = detail.replace(value, "[redacted]")
            print(json.dumps({"response_detail": detail[:1200]}))
            failed = True
        except (URLError, TimeoutError):
            print(f"{resource}: network connection failed")
            failed = True
    engine = build_engine(config["DATABASE_URL"])
    try:
        with engine.connect() as connection:
            existing = connection.scalar(text("SELECT to_regclass('public.patients')"))
            print(json.dumps({"supabase": "connected", "patient_table_exists": bool(existing)}))
    except SQLAlchemyError as exc:
        original = str(getattr(exc, "orig", ""))
        reason = "connection_failed"
        for pattern, label in (
            ("password authentication failed", "authentication_failed"),
            ("Tenant or user not found", "tenant_or_user_not_found"),
            ("Name or service not known", "dns_failed"),
            ("could not translate host name", "dns_failed"),
            ("timeout", "connection_timeout"),
        ):
            if pattern.lower() in original.lower():
                reason = label
                break
        print(json.dumps({"supabase": reason, "error_class": type(exc).__name__}))
        failed = True
    finally:
        engine.dispose()
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
