# 02 — Security Groups

Security groups (SGs) are **stateful, instance-level virtual firewalls**. "Stateful" means: if inbound traffic is allowed in, the matching response traffic is automatically allowed out — you never need a matching outbound rule for replies. We'll allow all outbound by default on every SG (standard practice) and lock down **inbound** only.

The key technique here — used constantly in real AWS architectures — is **referencing another security group as the source**, instead of an IP/CIDR. E.g., "allow port 8000 inbound, but only from anything that belongs to `msa-lab-sg-backend`" — not from an IP range. This means the rule stays correct even if instances get replaced/re-IP'd, and it precisely encodes "only these specific machines," which a CIDR range never can as precisely.

Create all 5 first (so they all exist and can reference each other), then fill in rules.

## Step 1 — Create all 5 security groups (empty first)

VPC → **Security Groups** → **Create security group**, repeat 5 times, all inside `msa-lab-vpc`:

| Name | Description |
|---|---|
| `msa-lab-sg-alb` | ALB — public HTTP/HTTPS entrypoint |
| `msa-lab-sg-frontend` | Frontend EC2 (React/nginx container) |
| `msa-lab-sg-backend` | Backend EC2 (FastAPI container) |
| `msa-lab-sg-database` | Database EC2 (Postgres container) |
| `msa-lab-sg-agent` | Azure DevOps self-hosted agent EC2 |

For each, leave the default outbound rule (**All traffic, 0.0.0.0/0**) — that's fine; egress is filtered by the NAT Gateway/route tables at the network level, and further restricting egress per-SG is a hardening step you can add later but isn't required for the lab to function correctly.

## Step 2 — Inbound rules: `msa-lab-sg-alb`

| Type | Protocol | Port | Source |
|---|---|---|---|
| HTTP | TCP | 80 | `0.0.0.0/0` (anywhere — needed so HTTP requests arrive at all, to be redirected to HTTPS) |
| HTTPS | TCP | 443 | `0.0.0.0/0` |

This is the **only** security group in the whole setup that allows traffic from the open internet. Everything else only ever allows traffic from specific other security groups.

## Step 3 — Inbound rules: `msa-lab-sg-frontend`

| Type | Protocol | Port | Source |
|---|---|---|---|
| Custom TCP | TCP | 3000 (or whatever port your frontend container listens on — we'll use 3000) | Source: **security group** `msa-lab-sg-alb` |

No SSH rule needed at all — remember, we're using SSM Session Manager (approved earlier), which needs **zero inbound ports open**. This is one of SSM's biggest security advantages over a bastion-host approach: there is no port for an attacker to even find.

## Step 4 — Inbound rules: `msa-lab-sg-backend`

| Type | Protocol | Port | Source |
|---|---|---|---|
| Custom TCP | TCP | 8000 | Source: security group `msa-lab-sg-frontend` |
| Custom TCP | TCP | 8000 | Source: security group `msa-lab-sg-agent` (so the deploy pipeline can health-check it) |

Only the frontend (and the deploy agent) can reach the backend — nothing else in the VPC, and certainly nothing from the internet, can hit port 8000 directly. This is defense-in-depth: even though the backend has no public IP anyway, this SG rule means that even a *misconfiguration* elsewhere couldn't accidentally expose it.

## Step 5 — Inbound rules: `msa-lab-sg-database`

| Type | Protocol | Port | Source |
|---|---|---|---|
| PostgreSQL | TCP | 5432 | Source: security group `msa-lab-sg-backend` |

Only the backend can reach Postgres. Not the frontend, not the internet, not even the devops agent (the agent deploys containers via SSM commands, it doesn't need a direct SQL connection).

## Step 6 — Inbound rules: `msa-lab-sg-agent`

No inbound rules needed at all. The self-hosted agent works by **polling out** to Azure DevOps (outbound HTTPS), it never receives inbound connections — Azure DevOps never initiates a connection *into* your VPC, which is precisely why this pattern doesn't require opening any inbound port for CI/CD to work. Leave inbound empty.

## Why this design is correct — the traffic path, security-group by security-group

```
Internet
   │  :80/:443
   ▼
[sg-alb]  ← only SG open to 0.0.0.0/0
   │  :3000
   ▼
[sg-frontend]  ← only reachable from sg-alb
   │  (frontend JS in the user's browser calls the backend API —
   │   see note below on how this routing works)
   ▼
[sg-backend]  ← only reachable from sg-frontend + sg-agent
   │  :5432
   ▼
[sg-database]  ← only reachable from sg-backend
```

**Important nuance worth understanding now, not later:** your React app's JavaScript runs in the **user's browser**, not on the frontend EC2. So when the frontend code calls the backend API, that HTTP request originates from the *user's browser*, over the *public internet*, not from inside the VPC. This means the backend must also be reachable from outside — **unless** we route backend calls through the same ALB (as a second path/rule), OR we make the frontend container act as a reverse proxy to the backend internally.

We will use the **ALB path-based routing** approach: the same ALB gets a second listener rule (`/api/*` → backend target group), so the browser always talks to one public HTTPS endpoint (your domain), and the ALB internally forwards `/api/*` calls to the backend EC2, `/*` to the frontend EC2. This keeps the backend's security group rule (`sg-backend` allows only `sg-frontend` and `sg-agent`) technically about *server-to-server* trust, while the ALB itself becomes the actual internet-facing router for both. We'll set this up precisely in doc 05. I'm flagging it now so the SG design above makes sense in context — you'll add one more rule to `sg-backend` in doc 05 allowing `sg-alb` too.

Let's fix that now so doc 05 doesn't require you to backtrack:

**Add to `msa-lab-sg-backend`:**

| Type | Protocol | Port | Source |
|---|---|---|---|
| Custom TCP | TCP | 8000 | Source: security group `msa-lab-sg-alb` |

Add this now. Final `sg-backend` inbound rules: 8000 from `sg-frontend`, 8000 from `sg-agent`, 8000 from `sg-alb`.

## Verification checklist

- [ ] 5 security groups created, all in `msa-lab-vpc`
- [ ] `sg-alb`: 80 + 443 from `0.0.0.0/0`
- [ ] `sg-frontend`: 3000 from `sg-alb` only
- [ ] `sg-backend`: 8000 from `sg-frontend`, `sg-agent`, and `sg-alb`
- [ ] `sg-database`: 5432 from `sg-backend` only
- [ ] `sg-agent`: no inbound rules
- [ ] No security group anywhere has an SSH (port 22) rule open — we don't need one with SSM

Next: `03-ec2-instances.md`
