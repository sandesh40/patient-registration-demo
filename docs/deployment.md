# Deployment and review

The demo uses the user's existing Vercel **Hobby** project, Supabase database, and
Vapi account. No paid plan or subscription was enabled. Calls consume available
Vapi credits; phone calls may also incur the caller's carrier charges. Free-tier
availability and limits still apply. This is a fictional-data assessment demo.

## Current endpoints

- Site / API base: https://patient-registration-demo-roan.vercel.app
- Swagger: https://patient-registration-demo-roan.vercel.app/docs
- Health: `/health`; database/table readiness: `/ready`
- Voice tools/events: `POST /vapi/webhook`
- US phone: +1 (406) 635-1082

The laptop can be off after deployment. For browser calling the caller keeps their
browser open. Vapi owns the audio session; Vercel does not run a persistent audio
WebSocket or background worker. Supabase stores patient and call state across
function shutdowns. The database region and Vercel function region are US East.

## Reproduce deployment

1. Follow the README local setup. Configure `.env` without committing it.
2. Run migrations explicitly against the intended database: `alembic upgrade head`.
3. Build browser assets: `npm ci --prefix web && npm run build --prefix web`.
4. Run the backend and browser tests before deployment.
5. Log into the Vercel CLI, link `patient-registration-demo`, then configure encrypted
   production variables: `DATABASE_URL`, `APP_ENV=production`, `API_AUTH_TOKEN`,
   `LOG_LEVEL=INFO`, `VAPI_ASSISTANT_ID`, and `VAPI_WEBHOOK_SECRET`.
6. Leave `VAPI_PUBLIC_KEY` empty until the assistant points at a ready backend.
7. Deploy: `vercel deploy --prod`. This project uses native FastAPI support through
   `index.py`, with `public/` served by the CDN. The Python function must not require
   that static directory to exist; it is absent from Vercel's function bundle.
8. Ensure this demo is publicly accessible so Vapi can reach it. REST patient routes
   still require the API bearer token, and voice webhooks require their separate token.
9. Run `python scripts/check_deployment.py https://YOUR-DEPLOYMENT`. This creates and
   soft-deletes one fictional patient through the deployed voice tools; no call is placed.
10. Create the Vapi bearer credential and configure the assistant as described in
    [voice integration](voice-integration.md). Restrict the public key to the final
    production origin and the registration assistant, with transient assistants disabled.
11. Set `VAPI_PUBLIC_KEY` in production, redeploy, then perform a real browser call.

The local setup in this workspace keeps CLI sessions under ignored `data/vercel-auth`
and `data/github-auth`. Commands using those sessions must specify that config path.
For example:

```bash
vercel login --global-config data/vercel-auth
vercel link --yes --project patient-registration-demo --global-config data/vercel-auth
python scripts/configure_vercel.py
vercel deploy --prod --yes --global-config data/vercel-auth
python scripts/configure_vapi.py --api-base-url https://YOUR-DEPLOYMENT --apply
python scripts/configure_vercel.py --enable-browser
vercel deploy --prod --yes --global-config data/vercel-auth
```

The Vercel helper validates the linked project name and Hobby plan, copies only
runtime values as encrypted production variables, and enables public deployment
access. It never uploads the Vapi private management key. The browser configuration
endpoint exposes only the public SDK key and assistant ID. `.vercelignore` excludes
environment files, CLI sessions, local databases, and test data from deployment.

## Reviewer test

Use the on-page fictional example or `examples/patient.json`. Click **Start demo call**,
grant microphone access, answer naturally, request a correction, listen to the full
readback, then confirm. Saving should be acknowledged only after it succeeds.

In Swagger click **Authorize** and enter the separately supplied REST token. Query
`GET /patients` with last name, DOB, or phone; retrieve the generated patient UUID.
Repeat with the same phone/DOB and request an update. Try starting over or hanging
up before confirmation and verify no new patient appears.

Backend/UI automation and the deployed synthetic tool smoke test are verified.
Actual audio, Vapi transcript delivery, and international telephone reachability
remain manual acceptance checks. A browser call helps demonstrate the workflow but
does not substitute for verifying the PDF's real-phone requirement. If the provider
blocks international access, document the actual result and use the PDF's stated
vendor-issue fallback with these local setup instructions.

Official hosting reference: [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi).

## Account integration limits

The repository is published, but GitHub Actions reported that jobs could not start
because the GitHub account is locked by a billing issue. This is a runner startup
restriction, not a reported test failure. The tests run locally without that service.
No paid plan, credit purchase, or billing change was made.

Vercel also denied automatic GitHub repository linking. Direct CLI deployments
work and the current site is live. Until repository access is enabled in the
Vercel/GitHub integration, deploy new revisions with the CLI commands above.
