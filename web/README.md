# ChemEAGLE Web

A shadcn-based workspace for the ChemEAGLE chemical-literature extraction API.

## Run locally

```bash
cp .env.example .env.local
# Add your ChemEAGLE API key to .env.local
pnpm install
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000).

## Configuration

| Variable | Purpose |
| --- | --- |
| `CHEMEAGLE_API_BASE_URL` | ChemEAGLE API host. Defaults to `https://app.chemeagle.net`. |
| `CHEMEAGLE_API_KEY` | API key sent from server routes as `X-API-Key`. It is never exposed to browser JavaScript. |

## Supported workflows

- Upload a reaction image for asynchronous extraction.
- Upload a full scientific PDF and poll the task until completion.
- Process a public image or PDF URL.
- Preview local sources, inspect normalized reaction records, copy JSON, and download results.

The UI proxies the public `/api/v1/process_image`, `/api/v1/process_pdf`,
`/api/v1/process_url`, and `/api/v1/status/:taskId` endpoints described by the
upstream ChemEAGLE SDK.
