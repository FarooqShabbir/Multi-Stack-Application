# 04 — Application Code, Dockerfiles, and Local Testing

All code referenced here has already been written and verified to build correctly:
- `frontend/` — React app (verified: `npm run build` compiles successfully)
- `backend/` — FastAPI app (verified: imports cleanly, all routes register correctly)
- `docker-compose.local.yml` — for testing all 3 pieces together **on your own machine**, before touching AWS at all

## Design decisions and why

**Frontend calls a relative `/api/entries` path, never a hardcoded backend IP.** The React JS runs in the *user's browser*, which only ever talks to your public domain (via the ALB). The ALB will path-route `/api/*` to the backend target group and everything else to the frontend target group (set up in doc 05). This is what makes "frontend talks to backend, backend talks to database, browser never touches the database" actually true at the network level, not just in application logic — the backend has no public IP at all, so the browser *couldn't* reach it directly even if the frontend code tried to.

**Backend never trusts a client-supplied timestamp.** Per the lab spec ("backend will append date and time"), `datetime.now(timezone.utc)` is generated **server-side**, inside `create_entry()`, not read from the request body. This is also just good practice — client clocks are unreliable and client input is untrusted.

**Backend retries its DB connection on startup.** This addresses the `depends_on` readiness gap discussed earlier: a container starting doesn't mean the app inside it (Postgres) is ready to accept connections yet. `get_connection()` retries up to 5 times with a 2-second delay rather than crashing immediately.

**Frontend Docker image is a multi-stage build.** Stage 1 (Node) compiles the React app; stage 2 (nginx, alpine) serves only the compiled static files. The final image never contains Node.js, npm, or your source code — only compiled JS/CSS/HTML plus nginx. Smaller image, smaller attack surface, faster to pull on the EC2 instance.

**Backend container runs as a non-root user (`appuser`).** Ties back to the OS/namespaces material: containers share the host kernel, so root inside a container is not fully equivalent to a harmless sandboxed root — running as a non-privileged user inside the container is real defense-in-depth against container-escape-class vulnerabilities.

---

## Step 1 — Test everything locally first (do this before AWS)

On your own machine, with Docker installed:

```bash
cd lab/
docker compose -f docker-compose.local.yml up --build
```

Then:
- Open `http://localhost:3000` → you should see the React UI
- Since there's no ALB locally to route `/api/*`, either:
  - (a) temporarily edit `frontend/src/App.js`'s `API_BASE` to `http://localhost:8000/api` for this local test only, rebuild, and revert before deploying, **or**
  - (b) just test the backend directly: `curl -X POST http://localhost:8000/api/entries -H "Content-Type: application/json" -d '{"text":"hello"}'` then `curl http://localhost:8000/api/entries` and confirm you get back JSON with your text plus a server-generated `created_at`.

Option (b) is faster and doesn't require touching frontend code — I'd suggest doing that first to validate the backend+database wiring in isolation, since that's the part most likely to have a real bug (network, env vars, SQL) versus the frontend (which is just UI).

**Do not proceed to AWS deployment until this local test passes.** Debugging a broken backend-database connection is minutes of work locally, and potentially an hour of work across SSM sessions on EC2 if you skip this step.

## Step 2 — Push your code to GitHub

```bash
cd lab/
git init
git add .
git commit -m "Initial commit: frontend, backend, compose"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

(Create the empty repo on GitHub first via the website, without a README/gitignore, so this push isn't rejected for divergent histories.)

Add a `.gitignore` so you don't commit build artifacts or dependencies:

```
node_modules/
build/
__pycache__/
*.pyc
.env
```

## Step 3 — Manual deployment commands (for now — the pipeline in doc 06 automates this)

These are the exact commands you'll run **once manually** (via SSM session) to prove each service works standalone on its real EC2 instance, before wiring up the CI/CD pipeline. Doing this manually first means that if the pipeline fails later, you already know the *application* works and the problem is in the *pipeline*, not the app — an important debugging separation.

### On `msa-lab-database`:

```bash
sudo docker run -d \
  --name postgres \
  --restart unless-stopped \
  -e POSTGRES_DB=labdb \
  -e POSTGRES_USER=labuser \
  -e POSTGRES_PASSWORD='<choose-a-real-password>' \
  -v pgdata:/var/lib/postgresql/data \
  -p 5432:5432 \
  postgres:16
```

`-p 5432:5432` here binds to the instance's private IP (it has no public one) — reachable only from within the VPC, and per the `sg-database` rules, only from things in `sg-backend`.

### On `msa-lab-backend`:

First, get the database instance's **private IP** (EC2 console → select `msa-lab-database` → copy "Private IPv4 address").

```bash
# Clone your repo (or copy just the backend/ folder over)
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>/backend

sudo docker build -t msa-backend .

sudo docker run -d \
  --name backend \
  --restart unless-stopped \
  -e DB_HOST='<database-private-ip>' \
  -e DB_PORT=5432 \
  -e DB_NAME=labdb \
  -e DB_USER=labuser \
  -e DB_PASSWORD='<same-password-as-above>' \
  -e ALLOWED_ORIGINS='*' \
  -p 8000:8000 \
  msa-backend
```

Verify from the backend instance itself: `curl http://localhost:8000/api/health` → should return `{"status":"ok"}`.

### On `msa-lab-frontend`:

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>/frontend

sudo docker build -t msa-frontend .

sudo docker run -d \
  --name frontend \
  --restart unless-stopped \
  -p 3000:3000 \
  msa-frontend
```

Verify: `curl http://localhost:3000` from the frontend instance itself should return the React app's HTML.

**Note on `--restart unless-stopped`**: this tells the Docker daemon to automatically restart the container if it crashes, or if the EC2 instance itself reboots and the daemon comes back up — without this flag, an instance reboot would leave your containers stopped even though the instance is running.

## Verification checklist

- [ ] Local `docker compose -f docker-compose.local.yml up --build` works end-to-end
- [ ] Code pushed to GitHub
- [ ] Postgres container running on `msa-lab-database`, reachable on port 5432 from within the VPC
- [ ] Backend container running on `msa-lab-backend`, `/api/health` returns `{"status":"ok"}` when curled from that instance
- [ ] Frontend container running on `msa-lab-frontend`, port 3000 returns the React app HTML when curled from that instance

Next: `05-alb-acm-route53-hostinger.md` — wiring the ALB, ACM certificate, and DNS so this becomes reachable at your actual domain over HTTPS.
