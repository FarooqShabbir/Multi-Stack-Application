# 05 — ALB, Target Groups, ACM Certificate, Route 53 + Hostinger DNS

This is where the browser-facing side comes together: one HTTPS endpoint at your domain, routing `/*` to the frontend and `/api/*` to the backend, with HTTP automatically redirecting to HTTPS.

Verified against current AWS documentation: ACM certificates for an ALB must be in the **same region** as the ALB; DNS validation via a CNAME record is the recommended method (simpler renewal story than email validation, and ACM auto-renews as long as the validation CNAME stays in place — never delete it).

---

## Step 1 — Create two target groups

EC2 Console → **Target Groups** → **Create target group**, twice:

**Target group 1 — frontend:**
1. Target type: **Instances**
2. Name: `msa-lab-tg-frontend`
3. Protocol: HTTP, Port: `3000`
4. VPC: `msa-lab-vpc`
5. Health check path: `/` (nginx will return 200 for the React app's index)
6. Next → select `msa-lab-frontend` instance → Include as pending below → Create target group

**Target group 2 — backend:**
1. Target type: **Instances**
2. Name: `msa-lab-tg-backend`
3. Protocol: HTTP, Port: `8000`
4. VPC: `msa-lab-vpc`
5. Health check path: `/api/health` (matches the endpoint we built specifically for this)
6. Next → select `msa-lab-backend` instance → Create target group

**Why the backend has its own dedicated health-check endpoint** (`/api/health`) rather than reusing `/api/entries`: a health check should be cheap, side-effect-free, and not depend on the database being populated — hitting `/api/entries` would tie your ALB's health status to database state, which is the wrong coupling. `/api/health` returns a static `{"status": "ok"}` with no DB dependency at all, so the ALB is only checking "is the FastAPI process alive and responding," which is exactly what a load balancer health check should verify.

## Step 2 — Create the ALB

EC2 Console → **Load Balancers** → **Create load balancer** → **Application Load Balancer**

1. Name: `msa-lab-alb`
2. Scheme: **Internet-facing** (this is what makes it reachable from outside the VPC at all)
3. IP address type: IPv4
4. VPC: `msa-lab-vpc`
5. Mappings: check **both** `msa-lab-public-a` and `msa-lab-public-b` (the 2-AZ requirement from doc 00/01)
6. Security groups: remove the default, select `msa-lab-sg-alb`
7. Listeners and routing:
   - Add listener: **HTTP : 80** — default action: we'll fix this to redirect in Step 5, for now just point it at `msa-lab-tg-frontend` as a placeholder
8. Create load balancer

Wait for **State: Active** (a few minutes).

## Step 3 — Request the ACM certificate

Console → **Certificate Manager** (confirm you're in the **same region** as your ALB — check the top-right region selector).

1. **Request a certificate** → **Request a public certificate**
2. Fully qualified domain name: `app.yourdomain.com` (replace with your real domain/subdomain — using a subdomain like `app.` rather than the bare root domain is common and simpler for ALB aliasing)
3. Validation method: **DNS validation** (recommended — simpler and enables auto-renewal, per AWS docs)
4. Key algorithm: RSA 2048 (default, fine)
5. Request

The certificate will sit in **Pending validation**. Click into it — it shows a **CNAME name** and **CNAME value** you must add to your DNS. We'll do that in Step 4 after Route 53 is set up, since that's where this CNAME needs to live.

## Step 4 — Route 53 hosted zone + delegating from Hostinger

Since your domain is registered at Hostinger but we want Route 53 to actually resolve it:

1. Console → **Route 53** → **Hosted zones** → **Create hosted zone**
2. Domain name: `yourdomain.com` (the root domain, not the subdomain)
3. Type: **Public hosted zone**
4. Create

Route 53 will show you **4 NS (nameserver) records** automatically created in this hosted zone — these are AWS's nameservers for your domain.

**Now go to Hostinger:**
1. Log into Hostinger → **Domains** → select `yourdomain.com` → **DNS / Nameservers**
2. Change from Hostinger's default nameservers to **Custom nameservers**
3. Enter the 4 NS values exactly as shown in your Route 53 hosted zone (they look like `ns-123.awsdns-45.com`, etc.)
4. Save

**What this actually does:** domain registration (who "owns" `yourdomain.com`, renewal, WHOIS) stays with Hostinger — that's the registrar's job. But DNS *resolution* (what IP/record `yourdomain.com` and its subdomains point to) now gets delegated entirely to Route 53's nameservers. Every DNS query for anything under `yourdomain.com` will be referred to Route 53, and Route 53's hosted zone records become authoritative. This propagation can take anywhere from minutes to (rarely) up to 48 hours depending on TTLs and caching, though it's usually fast in practice.

**Now add the ACM validation CNAME**, back in Route 53:
1. Go back to your ACM certificate (Step 3) → it shows the required CNAME name/value
2. In the ACM console, there's usually a **"Create records in Route 53"** button when ACM detects you have a matching hosted zone — use it; it adds the exact CNAME automatically, avoiding any copy-paste error
3. If that button isn't available, manually go to Route 53 → your hosted zone → **Create record** → paste the CNAME name (minus your domain suffix, Route53 appends it) and value exactly as ACM shows them
4. Wait a few minutes → refresh the ACM console → status should change to **Issued**

**Do not proceed until the certificate shows "Issued."** An ALB cannot use a certificate still in "Pending validation."

## Step 5 — Attach the certificate, add HTTPS listener, and redirect HTTP→HTTPS

Back in EC2 → Load Balancers → `msa-lab-alb` → **Listeners and rules** tab:

**Add the HTTPS listener:**
1. **Add listener**
2. Protocol: HTTPS, Port: 443
3. Default action: Forward to `msa-lab-tg-frontend`
4. Security policy: `ELBSecurityPolicy-TLS13-1-2-2021-06` (current recommended default — supports TLS 1.3 while remaining compatible)
5. Default SSL/TLS certificate: select the ACM certificate you just issued
6. Add listener

**Fix the HTTP listener to redirect instead of forward:**
1. Select the existing **HTTP : 80** listener → **Edit**
2. Change the default action from "Forward" to **Redirect**
3. Redirect to: HTTPS, Port 443, Status code **301** (permanent redirect)
4. Save changes

This satisfies the lab's explicit requirement: "ssl certificate attach with redirection from http to https."

## Step 6 — Add the path-based routing rule (`/api/*` → backend)

Select the **HTTPS : 443** listener → **Manage rules** (or **View/edit rules**) → **Add rule**:

1. Rule name: `route-api-to-backend`
2. Add condition: **Path** → value: `/api/*`
3. Add action: **Forward to** → `msa-lab-tg-backend`
4. Priority: `1` (lower number = evaluated first; this must be evaluated before the default catch-all rule)
5. Save

The listener's **default action** (forward to `msa-lab-tg-frontend`) now effectively becomes the `/*` catch-all fallback for anything that doesn't match `/api/*`. This is exactly the routing design flagged back in doc 02: one public HTTPS entrypoint, the ALB internally splitting traffic to the two private backend services based on URL path.

## Step 7 — Point your domain at the ALB

Route 53 → your hosted zone → **Create record**:
1. Record name: `app` (making it `app.yourdomain.com`, matching the ACM cert)
2. Record type: **A**
3. **Alias**: toggle ON
4. Route traffic to: **Alias to Application and Classic Load Balancer** → your region → select `msa-lab-alb`
5. Create records

**Why an Alias record rather than a plain CNAME/A with a fixed IP:** an ALB's IP addresses are not fixed and can change at AWS's discretion; a Route 53 Alias record is a Route53-specific record type that always resolves to the ALB's *current* address automatically, at no extra cost, and (unlike a real CNAME) can even be used at a zone apex if you ever want the bare root domain. This is the standard, correct way to point Route 53 at an ALB.

## Step 8 — Verify

Wait a few minutes for DNS to propagate, then:

```bash
curl -I http://app.yourdomain.com          # expect: HTTP/1.1 301, Location: https://...
curl -I https://app.yourdomain.com          # expect: HTTP/2 200, served by nginx (frontend)
curl https://app.yourdomain.com/api/health   # expect: {"status":"ok"} (served by FastAPI, backend)
```

Then open `https://app.yourdomain.com` in a browser: you should see the React UI, padlock/valid HTTPS, and Insert/List should work end-to-end — browser → ALB (HTTPS) → frontend or backend target group → (for backend) → Postgres on the database instance.

## Verification checklist

- [ ] Both target groups show their registered instance as **healthy** (Target Groups → select each → Targets tab)
- [ ] ACM certificate status: **Issued**
- [ ] HTTP:80 listener redirects (301) to HTTPS:443
- [ ] HTTPS:443 listener has the ACM cert attached, default action → frontend TG, `/api/*` rule → backend TG
- [ ] Route 53 hosted zone's NS records match what's set as custom nameservers in Hostinger
- [ ] `app.yourdomain.com` resolves and serves the app over valid HTTPS
- [ ] Insert button → List button round-trip works from the actual public URL, not just curl

Next: `06-azure-devops-pipelines.md` — self-hosted agent + CI/CD pipelines so `git push` auto-deploys.
