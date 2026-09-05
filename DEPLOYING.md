# Deploying

Two hosts, because the frontend is static and the API is a container. Neither
needs a database, a volume, or a secret — the briefings travel inside the image
(see `data/snapshot.db` and the note in `.gitignore`).

## 1. API

Render reads `render.yaml`, so the only manual step is the one value that
differs per environment:

1. New → Blueprint → pick this repo.
2. Set `TRADEWATCH_ALLOWED_ORIGINS` to the frontend's origin once step 2 gives
   you one (e.g. `https://tradewatch.vercel.app`). Comma-separate to allow more.
3. Note the service URL — `https://tradewatch-api.onrender.com` or similar.

Fly or Railway work identically; both take the Dockerfile as-is.

The free tier sleeps when idle, so the first request after a quiet spell takes a
few seconds. That is a cold start, not a fault.

### Verifying the image before you push it anywhere

```bash
docker build -t tradewatch-api .
docker run --rm -p 8080:8000 tradewatch-api
curl localhost:8080/api/documents?min_significance=4
```

It should return briefings with no further configuration. If it does, the
deployment will too — there is nothing else for the platform to supply.

## 2. Frontend

1. Vercel → Add New Project → this repo.
2. **Root directory: `frontend`.** Vercel detects Vite from there.
3. Environment variable `VITE_API_URL` = the API URL from step 1, no trailing
   slash.
4. Redeploy after setting it — Vite inlines env vars at build time, so a
   variable added after a build does not reach the bundle.

Then go back and set `TRADEWATCH_ALLOWED_ORIGINS` on the API to the Vercel URL.
Until you do, the API answers and the browser discards the response — the
failure looks like a broken API and is really a CORS policy doing its job.

## Keeping the data fresh

The snapshot is a point-in-time export. If it is worth updating, a scheduled
GitHub Action can run the pipeline with `ANTHROPIC_API_KEY` from repository
secrets, commit the regenerated `data/snapshot.db`, and let the push trigger a
redeploy. Deliberately not built yet: it adds a scheduled job and a key to a
system that currently needs neither, and a stale week of briefings costs a
demo nothing.
