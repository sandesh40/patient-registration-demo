# Vapi registration workflow

The backend is deployed on Vercel and the assistant configuration is applied.
Real conversation tests are still required before calling the assessment complete.

## Configuration and LLM

The versioned [system prompt](../app/voice/prompt.md) instructs the assistant to
collect every required field, offer optional fields, clarify ambiguity, accept
corrections, read back all details, and wait for explicit confirmation.
[Tool definitions](../app/voice/configuration.py) derive demographic schemas from
the same Pydantic model as the REST API.

The configured stack is Gemini 2.5 Flash through Vapi, Deepgram Nova 3 transcription,
and Deepgram Asteria speech. A separate LLM key is not included in this setup.
Provider usage is billed through Vapi; existing trial credits are finite and this
is not unlimited free calling. Rendering/testing the backend does not place calls.

Official references: [Gemini models](https://docs.vapi.ai/providers/model/gemini),
[Deepgram voices](https://docs.vapi.ai/providers/voice/deepgram),
[custom tools](https://docs.vapi.ai/tools/custom-tools),
[server events](https://docs.vapi.ai/server-url/events), and
[server authentication](https://docs.vapi.ai/server-url/server-authentication).

## Tool sequence and persistence

| Tool | Effect |
| --- | --- |
| `validate_fields` | Validate supplied fields, normalize phone punctuation, return targeted errors, invalidate earlier preparation |
| `lookup_patient` | Find active patients by phone AND DOB; scope eligible update IDs to this call |
| `prepare_registration` | Validate a full registration or merge an update; persist a draft and return every field, readback, and fresh token |
| `confirm_registration` | Require strict `confirmed=true` and the current token; atomically save the prepared patient and a replay receipt |
| `start_over` | Discard unconfirmed draft and patient selection |
| Vapi `endCall` | Gracefully end the conversation after success or cancellation |

`POST /vapi/webhook` requires `Authorization: Bearer <VAPI_WEBHOOK_SECRET>`.
It implements Vapi's `results`/`toolCallId`/JSON-string `result` protocol. REST routes
retain their separate `data`/`error` envelope and `API_AUTH_TOKEN` authentication.

No patient record is created by preparation, transcript delivery, or disconnect.
A caller's negative confirmation clears the draft; corrections require another
preparation and readback. Confirmation is rejected in a batch with another tool.
The LLM must wait for a new caller turn: the server does not inspect audio to prove
spoken consent. This distinction must be checked in live conversation testing.

PostgreSQL row locks serialize tool execution per call. An identical tool ID and
payload replays the original result; changed arguments under the same ID fail.
Another confirmation ID with the same token returns the already-saved patient.
Patient writes and receipt writes commit together. Failures roll back and return
an error that explicitly forbids claiming success. Confirmed updates also compare
the previously read record timestamp to avoid overwriting a concurrent edit.

The tables are `patients`, `voice_sessions`, and `voice_tool_receipts`. All have
PostgreSQL RLS enabled with no public Data API policies. The trusted backend uses
the supplied database-owner connection. End-of-call reports can store a transcript
linked to the saved patient. Audio recording is disabled in the proposed config.
Final confirmed fictional payloads are logged after successful commit; credentials
and confirmation tokens are not logged. No automatic retention purge is implemented.

## Render and apply

Use the repository root and a local `.env` based on `.env.example`. Supply the
private Vapi key, assistant/phone resource IDs, a random webhook token, and the
database/API credentials. Keep `.env` private and never commit it.

```bash
python scripts/check_integrations.py
python scripts/configure_vapi.py
```

The second command renders `data/vapi-assistant-preview.json` without modifying
Vapi. Before applying, deploy the backend and configure its `DATABASE_URL`,
`APP_ENV=production`, `API_AUTH_TOKEN`, `VAPI_ASSISTANT_ID`, and
`VAPI_WEBHOOK_SECRET`. Apply migrations explicitly; startup never runs migrations.

In Vapi **Integrations → Server Configuration**, create a Bearer credential using
the exact webhook token, header `Authorization`, and bearer prefix enabled. Save
its ID as `VAPI_SERVER_CREDENTIAL_ID` in the local `.env`. Then run:

```bash
python scripts/configure_vapi.py --api-base-url https://YOUR-DEPLOYMENT --apply
```

The script checks database readiness and authenticated webhook access, backs up
the existing assistant in an ignored file, applies the prompt/tools/model/voice,
and links the assigned phone number. The server credential ID is used on both
assistant and tool URLs. An incomplete configuration is never applied. Applying
does not itself place a call; live usage tests remain necessary.

## Tests

```bash
pytest -q tests/test_voice.py
python scripts/smoke_voice.py
```

The automated tests use isolated SQLite databases, real migrations, and FastAPI's
TestClient. They cover validation, corrections, confirmation, retries, rollback,
updates, restart persistence, transcript linkage, disconnects, and webhook auth.

The smoke script uses **the database configured in `.env`**. It creates one
fictional patient, delivers simultaneous confirmation retries, reconstructs the
app, retrieves the record, updates it through a second simulated call, and stores
a synthetic transcript. It finally soft-deletes its patient and checks that the
row is retained but excluded from active API results. It does not truncate any
tables, call Vapi, or spend voice credits. Synthetic voice audit records remain.

## Live review checklist (Part 3)

1. Complete a fictional registration, including optional fields. Hear every field
   read back; decline or correct once, then confirm. Verify only the final data saves.
2. Call again with the same phone and DOB; consent to an update. Verify unchanged
   optional fields survive and the patient ID is retained.
3. Try an impossible/future DOB, short phone, invalid ZIP, ambiguous date, and
   spelled/hyphenated names; verify targeted questions and no invented data.
4. Ask to start over, then disconnect before confirmation. Verify no new patient.
5. Confirm success speech follows the tool's save result, and the call ends politely.
6. Verify transcript linkage if a report arrives and REST retrieval after restart.
7. Confirm real telephone reachability from Pakistan and remaining Vapi credits.
   A browser fallback alone does not prove the PDF's phone requirement.
