# 03 — EC2 Instances + SSM Session Manager Setup

We're launching **4 EC2 instances** total, all in `msa-lab-private-a`, all with **no public IP**:
`msa-lab-frontend`, `msa-lab-backend`, `msa-lab-database`, `msa-lab-devops-agent`.

Verified against current AWS documentation: **`AmazonSSMManagedInstanceCore`** is the correct, current managed policy for SSM (an older policy, `AmazonEC2RoleforSSM`, is explicitly marked deprecated by AWS — don't use it if you see it suggested anywhere). Ubuntu Server 20.04/22.04 and Amazon Linux 2/2023 ship with the SSM Agent **preinstalled**, so no manual agent install is needed if you use one of those AMIs.

---

## Step 1 — Create the IAM role for SSM (once, reused by all 4 instances)

1. Console → **IAM** → **Roles** → **Create role**
2. Trusted entity type: **AWS service**
3. Use case: **EC2** → Next
4. Permissions policies: search `AmazonSSMManagedInstanceCore` → check it → Next
5. Role name: `msa-lab-ssm-role`
6. Create role

This role, once attached to an instance (as an "instance profile"), lets the SSM Agent running on that instance authenticate to the Systems Manager service using **temporary, auto-rotating credentials** — nothing hardcoded, nothing to leak. This is the IAM-based trust model replacing SSH keys entirely.

## Step 2 — Choose AMI and instance type

- **AMI**: Ubuntu Server 22.04 LTS (x86_64) — has SSM Agent preinstalled, and matches the Docker install commands we'll use in doc 04.
- **Instance type**: `t3.micro` is enough for frontend/backend/agent for a lab. For the database, use `t3.small` (Postgres benefits from a bit more headroom, and this is cheap either way for a lab you'll tear down).

## Step 3 — Launch each instance

Repeat this launch flow **4 times**, changing only the **Name** and (for database) instance size.

EC2 Console → **Launch instance**:

1. **Name**: `msa-lab-frontend` (then repeat for `msa-lab-backend`, `msa-lab-database`, `msa-lab-devops-agent`)
2. **AMI**: Ubuntu Server 22.04 LTS
3. **Instance type**: `t3.micro` (`t3.small` for database)
4. **Key pair**: **Proceed without a key pair** — we don't need SSH keys at all since we're using SSM exclusively. (If the console warns you, that's expected and fine.)
5. **Network settings** → Edit:
   - VPC: `msa-lab-vpc`
   - Subnet: `msa-lab-private-a`
   - Auto-assign public IP: **Disable** ← critical, this is what makes the instance actually private
   - Firewall (security groups): **Select existing security group** →
     - frontend instance → `msa-lab-sg-frontend`
     - backend instance → `msa-lab-sg-backend`
     - database instance → `msa-lab-sg-database`
     - devops-agent instance → `msa-lab-sg-agent`
6. **Advanced details** → **IAM instance profile** → select `msa-lab-ssm-role`
7. Storage: default 8GB gp3 is fine for frontend/backend/agent. Bump the database instance to **20GB** (Postgres + Docker images need more room).
8. **Launch instance**

Do this for all 4. Takes a couple minutes each to reach "Running."

## Step 4 — Verify SSM connectivity

Wait ~2-5 minutes after each instance shows "Running" (the SSM Agent needs a moment to register with the service, and needs the NAT Gateway path to actually reach the SSM endpoints over the internet — this is exactly why doc 01's NAT Gateway setup matters here specifically, not just for `apt`/Docker pulls).

1. Console → **Systems Manager** → **Fleet Manager** (or directly: EC2 → select an instance → **Connect** button → **Session Manager** tab)
2. You should see all 4 instances listed as **managed nodes**
3. Select `msa-lab-frontend` → **Connect** → confirms a browser-based terminal session opens, no SSH, no key, no open port

If an instance doesn't show up after 5 minutes, the near-universal cause is one of:
- No route to the internet (check the NAT Gateway is "Available" and the private route table has the `0.0.0.0/0 → nat` route from doc 01)
- Wrong/missing IAM instance profile
- Security group somehow blocking outbound (shouldn't happen with our default "allow all outbound" — verify you didn't change it)

## Step 5 — Install Docker on all 4 instances

Open an SSM session (Step 4) to **each** of the 4 instances and run:

```bash
# Update package index
sudo apt-get update -y

# Install prerequisites
sudo apt-get install -y ca-certificates curl gnupg

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add the Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Let the ssm-user (and ubuntu user) run docker without sudo
sudo usermod -aG docker ubuntu
sudo usermod -aG docker ssm-user 2>/dev/null || true

# Verify
sudo docker run hello-world
```

This is the official Docker CE install method for Ubuntu — the exact same `apt` repository setup referenced throughout Docker's own docs. Notice this is happening on a **private** instance, reaching `download.docker.com` and the Ubuntu package mirrors purely through the NAT Gateway's outbound path — a direct, concrete confirmation that the NAT setup from doc 01 is working correctly.

**Why `hello-world` matters as a check**: this tiny image, per section 3.2-3.3 of what we covered, is Docker: pull an image, unpack its layers via OverlayFS, create a container (namespaces + cgroups per section 1.9), run it, print output, exit. If this works, your entire Docker Engine install is sound before we put anything real on top of it.

## Verification checklist

- [ ] 4 instances running, all in `msa-lab-private-a`, all with **no public IPv4** (check the instance details — "Public IPv4 address" should be blank)
- [ ] All 4 appear as managed nodes in Systems Manager → Fleet Manager
- [ ] SSM Session Manager connects to each without any SSH key or open port
- [ ] `docker run hello-world` succeeds on all 4

Next: `04-application-code.md` — the actual React/FastAPI/Postgres application and Dockerfiles.
