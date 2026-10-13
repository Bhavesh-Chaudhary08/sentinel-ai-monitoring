# Deploying so your friends just create an account and go

The goal: **you** do the setup once, on a free cloud VM. Your friends do zero
technical work — no Docker, no Python, no environment, no API URLs. They
install one zip, click "Create account", and the extension works.

## How it works

```
                        one public origin: https://your.domain
  ┌──────────────┐      ┌─────────────────────────────────────────────┐
  │ friend's     │ HTTPS│  your free VM (docker compose prod stack)    │
  │ browser +    ├─────>│  Caddy (auto HTTPS) ─> frontend nginx ─> API │
  │ extension    │      │                          │        │         │
  └──────────────┘      │                       Postgres  Redis/Celery│
                        │  (db, redis, api publish NO host ports)     │
                        └─────────────────────────────────────────────┘
```

* The extension is **built once** with `PUBLIC_API_URL` / `PUBLIC_DASHBOARD_URL`
  baked in ([extension/build.mjs](extension/build.mjs)) — every copy you share
  already points at your VM. Friends never configure a URL.
* The dashboard, REST API and alert WebSocket share **one origin**, so there is
  no CORS setup and the live alert feed just works.
* Self-registration is built in ([backend/app/api/v1/auth.py](backend/app/api/v1/auth.py)):
  role is forced to `employee`, and capture only starts after the user accepts
  consent in the popup. Nothing to seed.

---

## 0. One-time prerequisites (you)

| Thing | Cost | Notes |
|---|---|---|
| A VM | $0 | **Oracle Cloud Always Free** (A1 shape: 4 OCPU / 24 GB — runs the full ML stack) or **GCP free tier** e2-micro (use the lightweight settings below) |
| A DNS name | ~$0–10/yr | Any domain, or a free subdomain provider — you need an **A record** pointing at your VM's public IP (Caddy needs a real name for the HTTPS cert) |
| Chrome Web Store (optional) | $5 once | Only if you want friends to install from the store instead of a zip |

Open **TCP 80 and 443** (and 22 for SSH) in your cloud firewall:
* Oracle Cloud: *Virtual Cloud Network → Security Lists → Add Ingress Rules*
  (its default list only allows SSH).
* GCP: `gcloud compute firewall-rules create allow-web --allow tcp:80,tcp:443`

---

## 1. Set up the server (once)

```bash
# Docker (Ubuntu/Debian)
curl -fsSL https://get.docker.com | sudo sh

# Your project
git clone <your-repo-url> aidlp && cd aidlp

# Configure
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste as SECRET_KEY
# then edit .env and set:
#   DOMAIN=ai.example.com          (your DNS name, pointing at the VM IP)
#   SECRET_KEY=<the value you just generated>
#   POSTGRES_PASSWORD=<another generated value>
```

Start everything (fails fast with a clear message if `.env` is incomplete):

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Verify:

```bash
curl -s https://your.domain/health          # {"status":"ok",...}
open https://your.domain                    # dashboard loads
docker compose -f docker-compose.prod.yml ps # all services Up / healthy
```

The first build pulls the ML/NLP image layers — on a small VM use the
lightweight mode instead (see [DEPLOY.md §5](#5-rolling-out--scaling)):

```bash
INSTALL_NLP=0 INSTALL_ML=0 SEMANTIC_ENABLED=false docker compose -f docker-compose.prod.yml up -d --build
```

Certificates are issued and renewed automatically by Caddy; nothing to do.

---

## 2. Build the extension once (with your URL baked in)

```bash
cd extension
npm ci
PUBLIC_API_URL=https://your.domain/api/v1 \
PUBLIC_DASHBOARD_URL=https://your.domain \
npm run build
```

Package the `dist/` folder as a zip (Windows: right-click `dist` → *Compress to
ZIP*; macOS: *Compress*) and share it — Google Drive, GitHub Release, whatever:

```bash
# or from a terminal:
cd dist && zip -r ../sentinel-extension.zip . && cd ..
```

That zip is the **entire** technical setup your friends will ever touch.

---

## 3. What your friends do (the whole list)

1. Download the zip, unzip it.
2. Open `chrome://extensions`, turn on **Developer mode** (top-right), click
   **Load unpacked**, pick the unzipped folder.
3. Open `https://your.domain` → **Create one** → enter email + password.
4. Click the extension icon → **Sign in** with the same email + password →
   **Enable monitoring**.

Done — capture runs, the dashboard shows their usage, alerts stream live.
No environment, no config, no terminal.

> **Even smoother (optional, $5 once):** publish the zip to the Chrome Web
> Store and friends install it with one click — no Developer-mode step.

---

## 4. Day-2 operations

```bash
# Update after pulling new code
docker compose -f docker-compose.prod.yml up -d --build

# Logs
docker compose -f docker-compose.prod.yml logs -f api worker

# Restart a single service
docker compose -f docker-compose.prod.yml restart worker

# One-off demo data (optional)
docker compose -f docker-compose.prod.yml --profile tools run --rm seed
```

**Backup Postgres** (cron, daily):

```bash
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U aidlp aidlp | gzip > /backups/aidlp-$(date +%F).sql.gz
```

---

## 5. Rolling out / scaling

* **Small VM (GCP e2-micro, 1 GB):** build the lightweight image —
  `INSTALL_NLP=0 INSTALL_ML=0 SEMANTIC_ENABLED=false` in `.env` (drops spaCy,
  Presidio, sentence-transformers; falls back to the lexical scorer) and set
  `CLASSIFY_SYNC=true` so classification runs in the API process instead of a
  separate worker.
* **More throughput:** with `CLASSIFY_SYNC=false` (default), classification runs
  in Celery workers — add replicas without any code change:
  `docker compose -f docker-compose.prod.yml up -d --scale worker=3`.
  The API is stateless and can be scaled the same way; nginx re-resolves the
  `api` hostname, so replicas load-balance automatically.
* **Bigger data:** move Postgres to a managed service (Cloud SQL / Neon) later —
  only `DATABASE_URL` changes; the app never assumes localhost.

## Security notes

* `db`, `redis`, `api` and `frontend` publish **no host ports** — only Caddy
  (80/443) is reachable from the internet; everything else lives on the
  internal Docker network.
* Never commit `.env`; `SECRET_KEY` signs every session token.
* HTTPS is mandatory (Caddy), so tokens and captured content never travel
  in clear text.
* Signup is public but can only create `employee` accounts, and **nothing is
  captured until each user explicitly accepts consent** in the popup.
