# 06 — Self-Hosted Azure DevOps Agent + 2 Pipelines (Frontend, Backend)

Confirmed as current, correct practice via Microsoft's own docs and AWS's own guidance (searched and verified earlier in this conversation): the self-hosted agent should live **inside the VPC** for a private-subnet deployment target, registered using a **PAT with "Agent Pools (read, manage)" scope**.

Two pipelines, as you scoped: one for `frontend/`, one for `backend/`. The database isn't in a pipeline — per doc 04, it's a plain `postgres:16` official image, not custom-built code, so there's nothing to build/CI for it. (If you later add DB migrations, that would become a 3rd pipeline — out of scope here.)

---

## Part A — Set up the self-hosted agent

### Step 1 — Create a PAT

1. Azure DevOps → your organization → top-right user icon → **Personal access tokens** → **New Token**
2. Name: `msa-lab-agent-pat`
3. Expiration: your choice (e.g., 90 days — note this means you'll need to regenerate and reconfigure the agent when it expires)
4. Scopes: **Custom defined** → search "Agent Pools" → check **Read & manage**
5. Create → **copy the token immediately**, it's shown only once

### Step 2 — Create an agent pool

1. Azure DevOps → Organization settings (bottom left) → **Agent pools** → **Add pool**
2. Pool type: **Self-hosted**
3. Name: `msa-lab-agent-pool`
4. Create

### Step 3 — Install the agent on `msa-lab-devops-agent` (via SSM session)

```bash
# Prerequisites
sudo apt-get update -y
sudo apt-get install -y git curl jq

# Docker too -- the agent needs to run `docker build` during the pipeline
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker ubuntu

# Download the agent (check learn.microsoft.com/azure/devops/pipelines/agents/agents
# for the current version/link if this specific version has moved on)
mkdir -p ~/myagent && cd ~/myagent
curl -O https://vstsagentpackage.azureedge.net/agent/3.243.1/vsts-agent-linux-x64-3.243.1.tar.gz
tar zxvf vsts-agent-linux-x64-3.243.1.tar.gz

# Configure — interactive prompts:
./config.sh
#   Server URL   > https://dev.azure.com/<your-organization>
#   Auth type    > PAT   (press Enter, PAT is default)
#   Personal access token > <paste the PAT from Step 1>
#   Agent pool   > msa-lab-agent-pool
#   Agent name   > msa-lab-agent  (or press Enter for default)
#   Work folder  > press Enter for default
#   Run as service? > Y  (recommended -- covered next)

# Install and start as a systemd service (survives reboot, auto-restarts on crash)
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status
```

### Step 4 — Verify

Azure DevOps → Organization settings → Agent pools → `msa-lab-agent-pool` → **Agents** tab → you should see `msa-lab-agent` listed with a green **Online** status.

**Note on the exact agent version above**: I've given a real, recently-current version number, but Azure DevOps agent versions update periodically. If that specific `curl` URL 404s, get the current one from Azure DevOps directly: Organization settings → Agent pools → your pool → **New agent** → it shows the current download command for Linux, pre-filled and always correct for that moment. Use that if the hardcoded version above is stale by the time you do this.

## Part B — Grant the agent's IAM role deploy permissions (for SSM-based deploy, optional refinement) or SSH-less local deploy

Since the agent itself lives **inside the VPC**, on the same private subnet as frontend/backend, it can reach them directly over the network using the security-group rules already in place (`sg-backend` allows `sg-agent` on 8000, and we'll add an equivalent for frontend if needed). For this lab, the simplest correct approach: **the pipeline SSHes... actually, no** — we're SSH-key-free per your earlier decision. Instead, the pipeline will use **SSM `send-command`** to remotely trigger `docker build`/`docker run` on the target instance, keeping the "no SSH keys anywhere" principle consistent end-to-end.

For that, the agent's EC2 instance needs an IAM role with `ssm:SendCommand` permission (in addition to whatever it already has), and the target instances need the SSM agent (already true, per doc 03).

**Attach an inline policy to a new role for the agent** (separate from `msa-lab-ssm-role`, since this one needs different, broader permissions — the agent is a *sender* of SSM commands, not just a *managed node*):

1. IAM → Roles → **Create role** → AWS service → EC2
2. Skip attaching a managed policy for now → name it `msa-lab-agent-role` → Create
3. Open the role → **Add permissions → Create inline policy** → JSON tab:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ssm:SendCommand",
        "ssm:GetCommandInvocation",
        "ssm:ListCommandInvocations"
      ],
      "Resource": "*"
    }
  ]
}
```

4. Name: `msa-lab-agent-ssm-send`, Create policy
5. **Also attach** `AmazonSSMManagedInstanceCore` to this same role (the agent instance still needs to itself be a managed node, reachable for the SSM Session Manager access we set up in doc 03)
6. Go to EC2 → select `msa-lab-devops-agent` → **Actions → Security → Modify IAM role** → switch from `msa-lab-ssm-role` to `msa-lab-agent-role`

This follows the principle of least privilege discussed earlier in the lab: the agent instance gets exactly the extra permission it needs (send commands to other instances) and nothing more — it still can't, say, read S3 buckets or modify IAM itself.

## Part C — The two pipeline YAML files

Both pipelines follow the same shape: build the Docker image on the agent, then use `aws ssm send-command` to tell the *target* EC2 instance to pull the latest code and rebuild/restart its own container. (The agent builds nothing that gets shipped anywhere directly — it triggers the target instance to build its own image locally. This avoids needing a container registry for this lab; a more advanced version would push to Amazon ECR and have the target `docker pull` instead of rebuilding from source — worth doing later, out of scope for this pass.)

### `azure-pipelines-backend.yml` (place at repo root or `backend/`)

```yaml
trigger:
  branches:
    include:
      - main
  paths:
    include:
      - backend/*

pool:
  name: msa-lab-agent-pool

variables:
  BACKEND_PRIVATE_IP: '<msa-lab-backend private IP>'   # fill in from EC2 console

steps:
  - script: |
      echo "Triggering deploy on backend instance via SSM..."
      aws ssm send-command \
        --instance-ids "$(BACKEND_INSTANCE_ID)" \
        --document-name "AWS-RunShellScript" \
        --parameters commands='[
          "cd /home/ubuntu/<your-repo> || git clone https://github.com/<your-username>/<your-repo>.git /home/ubuntu/<your-repo>",
          "cd /home/ubuntu/<your-repo> && git pull origin main",
          "cd /home/ubuntu/<your-repo>/backend && sudo docker build -t msa-backend .",
          "sudo docker rm -f backend || true",
          "sudo docker run -d --name backend --restart unless-stopped -e DB_HOST=$(DATABASE_PRIVATE_IP) -e DB_PORT=5432 -e DB_NAME=labdb -e DB_USER=labuser -e DB_PASSWORD=$(DB_PASSWORD) -e ALLOWED_ORIGINS=* -p 8000:8000 msa-backend"
        ]' \
        --region us-east-1
    displayName: 'Deploy backend via SSM'
```

### `azure-pipelines-frontend.yml`

```yaml
trigger:
  branches:
    include:
      - main
  paths:
    include:
      - frontend/*

pool:
  name: msa-lab-agent-pool

steps:
  - script: |
      echo "Triggering deploy on frontend instance via SSM..."
      aws ssm send-command \
        --instance-ids "$(FRONTEND_INSTANCE_ID)" \
        --document-name "AWS-RunShellScript" \
        --parameters commands='[
          "cd /home/ubuntu/<your-repo> || git clone https://github.com/<your-username>/<your-repo>.git /home/ubuntu/<your-repo>",
          "cd /home/ubuntu/<your-repo> && git pull origin main",
          "cd /home/ubuntu/<your-repo>/frontend && sudo docker build -t msa-frontend .",
          "sudo docker rm -f frontend || true",
          "sudo docker run -d --name frontend --restart unless-stopped -p 3000:3000 msa-frontend"
        ]' \
        --region us-east-1
    displayName: 'Deploy frontend via SSM'
```

### Variables to set (Azure DevOps → Pipelines → Edit → Variables, mark `DB_PASSWORD` as **secret**)

- `BACKEND_INSTANCE_ID`, `FRONTEND_INSTANCE_ID`, `DATABASE_PRIVATE_IP` — from the EC2 console
- `DB_PASSWORD` — mark as **secret** (locked padlock icon) so it's masked in logs and not visible in plain YAML

### Prerequisite: AWS CLI + credentials on the agent

The agent instance needs the AWS CLI installed and credentials to call `ssm:SendCommand` — it gets these automatically and securely via its **IAM instance profile** (`msa-lab-agent-role` from Part B), the same mechanism used throughout this lab — no access keys hardcoded anywhere:

```bash
# On msa-lab-devops-agent, via SSM session:
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
sudo apt-get install -y unzip
unzip awscliv2.zip
sudo ./aws/install
aws sts get-caller-identity   # should succeed with no explicit credentials --
                                #  confirms the instance profile is working
```

## Step — Create both pipelines in Azure DevOps

1. Azure DevOps → your project → **Pipelines** → **New pipeline**
2. Where's your code: **GitHub** → authorize/select your repo
3. Configure: **Existing Azure Pipelines YAML file** → path: `/azure-pipelines-backend.yml`
4. Save (don't run yet if variables aren't set) → set the pipeline variables from above → run
5. Repeat: **New pipeline** again → same repo → path: `/azure-pipelines-frontend.yml`

With the `paths: include:` trigger filters shown above, pushing a change under `backend/` only triggers the backend pipeline, and a change under `frontend/` only triggers the frontend one — exactly the "2 pipelines are enough" scoping from your original plan, without one pipeline redundantly redeploying both services on every push.

## Verification checklist

- [ ] Agent shows **Online** in `msa-lab-agent-pool`
- [ ] `aws sts get-caller-identity` succeeds on the agent with no hardcoded keys
- [ ] Both pipelines created, pointed at the correct YAML paths
- [ ] Pushing a change to `backend/` (e.g., editing `main.py`) triggers only the backend pipeline, and the change is live at `https://app.yourdomain.com/api/health` afterward
- [ ] Pushing a change to `frontend/` triggers only the frontend pipeline, and the change is visible at `https://app.yourdomain.com` afterward

---

## What you've now built, end to end

A request from a browser hits Route 53 (delegated from Hostinger) → resolves to the ALB → TLS terminated using an ACM cert → HTTP redirected to HTTPS → path-routed to either the frontend or backend target group → lands on an EC2 instance with no public IP at all, reachable only because it's a *target* of the ALB → runs inside a Docker container, which is itself (per Part 1 of this whole lesson) just a namespaced, cgroup-limited Linux process → the backend talks to Postgres on a third private instance, itself only reachable from the backend's security group → and the whole thing redeploys itself automatically via a self-hosted CI/CD agent living inside the same private network, authenticating to AWS via IAM instance roles rather than static credentials, and to Azure DevOps via a scoped PAT.

Every piece of this ties back to something from the OS/virtualization/Docker fundamentals we covered before starting the lab — nothing here should feel like unexplained magic at this point.
