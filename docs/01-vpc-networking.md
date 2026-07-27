# 01 — VPC & Networking Setup (AWS Console, manual)

Do these in order. Pick **one AWS Region** for everything (e.g., `us-east-1`) and stay in it for the entire lab — ACM certs for an ALB must be in the same region as the ALB (verified against AWS docs), so switching regions mid-lab will break things later.

---

## Step 1 — Create the VPC

1. Console → **VPC** → **Your VPCs** → **Create VPC**
2. Choose **VPC only** (not the "VPC and more" wizard — we want to build subnets ourselves so you see every piece)
3. Name tag: `msa-lab-vpc`
4. IPv4 CIDR: `10.0.0.0/16`
5. IPv6: No IPv6 CIDR block
6. Tenancy: Default
7. Create VPC

## Step 2 — Create the subnets

Repeat **Create subnet** 3 times inside `msa-lab-vpc`:

| Name | AZ | CIDR |
|---|---|---|
| `msa-lab-public-a` | e.g. `us-east-1a` | `10.0.1.0/24` |
| `msa-lab-public-b` | a **different** AZ, e.g. `us-east-1b` | `10.0.2.0/24` |
| `msa-lab-private-a` | same AZ as public-a, e.g. `us-east-1a` | `10.0.11.0/24` |

**Why public-a and public-b must be different AZs:** this is the ALB's 2-AZ requirement mentioned in the architecture doc — an AZ is an isolated physical datacenter; AWS forces this spread so the ALB survives a single datacenter failure.

**Why private-a is in the same AZ as public-a:** the NAT Gateway lives in public-a; keeping private-a in the same AZ avoids cross-AZ data transfer charges for the private instances' outbound traffic. (In a real production setup you'd add a `private-b` + a 2nd NAT Gateway for full HA — skipped here to keep the lab's cost down; note this as a known simplification.)

## Step 3 — Create and attach an Internet Gateway

1. VPC → **Internet Gateways** → **Create internet gateway**
2. Name: `msa-lab-igw`
3. Create, then select it → **Actions → Attach to VPC** → choose `msa-lab-vpc`

The IGW is what gives the VPC a path to/from the actual internet — without it, nothing in any subnet, public or private, can reach outside the VPC at all, regardless of route tables.

## Step 4 — Allocate an Elastic IP (for the NAT Gateway)

1. VPC → **Elastic IPs** → **Allocate Elastic IP address** → Allocate
   (Leave default settings — Amazon's pool)

A NAT Gateway needs a fixed public IP to present to the internet on behalf of everything behind it — that's what this Elastic IP is for.

## Step 5 — Create the NAT Gateway

1. VPC → **NAT Gateways** → **Create NAT gateway**
2. Name: `msa-lab-nat`
3. Subnet: `msa-lab-public-a` (**must** be a public subnet — a NAT Gateway itself needs internet access via the IGW to do its job)
4. Connectivity type: **Public**
5. Elastic IP allocation ID: pick the one you just allocated
6. Create

This will take a few minutes to become "Available." This is the mechanism you approved earlier: private-subnet EC2s route their outbound internet traffic through this NAT Gateway, which has a real public IP, while the private EC2s themselves never get one — inbound connections from the internet to them are impossible, only outbound-initiated traffic works (this asymmetry is the whole point of NAT).

## Step 6 — Create route tables

**Public route table:**
1. VPC → **Route Tables** → **Create route table**
2. Name: `msa-lab-rt-public`, VPC: `msa-lab-vpc`
3. After creation, select it → **Routes** tab → **Edit routes** → **Add route**
   - Destination: `0.0.0.0/0`
   - Target: **Internet Gateway** → `msa-lab-igw`
   - Save
4. **Subnet associations** tab → **Edit subnet associations** → check both `msa-lab-public-a` and `msa-lab-public-b` → Save

**Private route table:**
1. Create route table → Name: `msa-lab-rt-private`, VPC: `msa-lab-vpc`
2. **Edit routes** → **Add route**
   - Destination: `0.0.0.0/0`
   - Target: **NAT Gateway** → `msa-lab-nat`
   - Save
3. **Subnet associations** → check `msa-lab-private-a` → Save

**Why two separate route tables is the actual definition of "public" vs "private" here:** nothing about a subnet is *inherently* public or private in AWS — a subnet is "public" purely because its route table sends `0.0.0.0/0` traffic to an Internet Gateway (direct, two-way path to the internet), and "private" because its route table sends `0.0.0.0/0` to a NAT Gateway instead (outbound-only, one-way path). This is the mechanism, not a label you tick somewhere.

## Step 7 — Enable auto-assign public IP on public subnets (needed later for the ALB's own ENIs — not for your EC2 instances, which stay private)

1. Select `msa-lab-public-a` → **Actions → Edit subnet settings** → check **Enable auto-assign public IPv4 address** → Save
2. Repeat for `msa-lab-public-b`

## Verification checklist before moving on

- [ ] VPC `msa-lab-vpc` exists, CIDR `10.0.0.0/16`
- [ ] 3 subnets exist with correct CIDRs and AZs
- [ ] IGW attached to the VPC
- [ ] NAT Gateway status = **Available**, sitting in `msa-lab-public-a`
- [ ] `msa-lab-rt-public` has a `0.0.0.0/0 → igw` route, associated with both public subnets
- [ ] `msa-lab-rt-private` has a `0.0.0.0/0 → nat` route, associated with `msa-lab-private-a`

Next: `02-security-groups.md`
