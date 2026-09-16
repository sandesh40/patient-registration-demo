# Assessment coverage

Source: the supplied **Voice AI Agent — Patient Registration System** PDF.
Status reflects verified behavior, not merely planned implementation. Optional
bonuses are separated from required work. This document is updated at each stage.

## Part 1 — database and REST API

- [x] FastAPI with a separate shared patient service and SQLAlchemy data layer.
- [x] Every required and optional demographic field from page 3.
- [x] Required/optional semantics; preferred language defaults to English.
- [x] DOB format/calendar/future validation, sex enum, names, email, phone, state,
      ZIP, and alphanumeric insurance member ID validation.
- [x] Automatic UUID and UTC creation/modification timestamps.
- [x] Persistent on-disk SQLite for local development; PostgreSQL-compatible schema.
- [x] Versioned Alembic migration with SQL column types and constraints.
- [x] GET collection with all three optional filters.
- [x] GET individual patient by UUID.
- [x] POST creation with 201 and generated patient ID.
- [x] PUT partial updates without erasing omitted values.
- [x] DELETE soft deletion using deleted_at; exclude deleted records from active queries.
- [x] Consistent data/error envelope and appropriate 200/201/400/404/422/500 responses.
- [x] Input validation independent of the LLM; parameterized database statements.
- [x] Environment configuration and ignored secret files; optional local API token,
      required in production.
- [x] README: local setup, architecture, stack choices, variables, limitations.
- [x] Verify automated tests: 95 backend tests passed; the separate PostgreSQL 18
      integration test passed. Application coverage: 98% on the SQLite suite.
- [x] Ruff lint/format, dependency consistency, migration drift, and upgrade/downgrade checks.
- [x] Connect the supplied Supabase project, apply migrations through 0002, and
      verify schema drift and the fictional voice/database smoke test.

## Part 2 — Vapi agent and persistence integration

- [x] Verify via Vapi API that the assigned U.S. number is active and routes to the
      supplied assistant (telephone reachability still requires a real call).
- [x] Prepare Gemini 2.5 Flash, Deepgram transcriber/voice, and ten-minute call limit
      configuration; render a reviewable preview. Applying it is tracked in Part 3.
- [x] Implement prompt for natural greeting, flexible collection, out-of-order
      answers, spelling, interruptions, corrections, required and optional fields.
- [x] Validate fields and return targeted errors; prompt instructs specific re-prompts.
- [x] Produce a complete readback and require a fresh confirmation token before save.
      Actual spoken confirmation is interpreted by the LLM and needs live testing.
- [x] Tool handler calls the shared patient service; patient and retry receipt commit
      atomically. Simultaneous retries verified against Supabase.
- [x] Return success only after commit; tested database failure rollback/error response.
- [x] Prompt defines success/failure speech and graceful endCall behavior.
- [x] Start-over and disconnection handlers do not save unconfirmed patient data.
- [x] Include documented agent prompt, tool definitions, and configuration script.
- [x] Log final confirmed fictional payload after commit; test excludes secrets/tokens.
- [x] 122 tests pass; 98% application coverage. Live Supabase smoke test verifies
      restart persistence, returning update, transcript linkage, and soft deletion.
- [ ] Verify natural conversation, spoken readback/confirmation, interruption behavior,
      success speech, and graceful ending with a real Vapi call (Part 3).

## Part 3 — deployment and review

- [x] Deploy public API to Vercel Hobby with persistent Supabase storage.
- [x] Configure encrypted production secrets and separate API/webhook bearer tokens.
- [x] Apply Gemini/Deepgram assistant configuration and authenticated tool URLs;
      verify saved settings and phone routing through Vapi's API.
- [x] Add browser voice backup, call controls, microphone errors, and live captions;
      document its difference from phone access. Five mocked browser tests pass.
- [x] Confirm public health/readiness, assets/docs, authentication, and tool URLs;
      deployed synthetic prepare/confirm/retry/retrieve/soft-delete smoke test passes.
- [ ] Complete a real phone registration and a second call; verify retained data.
- [ ] Verify caller reachability from Pakistan, or document actual vendor blocker
      and provide the runnable fallback permitted by the PDF.
- [x] Automated edge cases: invalid DOB/phone, correction, start over, dropped call,
      DB failure, and cancellation during browser connection. Spoken tests remain above.
- [ ] Push repository and supply reviewer access if private.
- [x] README contains live phone number, API base URL, testing notes, and Next Steps.
- [x] Prepare URLs and private reviewer bearer token in ignored, owner-readable
      `data/reviewer-access.txt`; public docs never contain the token.
- [ ] Check remaining voice credits and project availability at review time.

## Optional bonuses

- [x] Returning-patient detection and confirmed update backend; automated and Supabase
      tests pass. Live conversational verification is pending.
- [ ] Mock appointment scheduling.
- [ ] Spanish or other multilingual conversation.
- [x] End-of-call transcript persistence linked to patient; synthetic webhook tested.
      Receipt of a real Vapi transcript is pending.
- [ ] Patient dashboard.
- [x] Automated API and database tests implemented (verification tracked above).
- [ ] Optional seed records (fictional example JSON supplied; no auto-seeding).
