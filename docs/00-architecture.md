# Microservices on AWS + Docker — Architecture Overview

## What we're building

```
                                   Internet
                                      │
                                      │  (HTTPS :443, HTTP :80→redirect)
                                      ▼
                         ┌─────────────────────────┐
                         │   Route 53 (public zone)  │
                         │   yourdomain.com  A-alias  │
                         └────────────┬────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │  Application Load Balancer │  (internet-facing)
                         │  ACM cert (yourdomain.com)  │
                         │  lives in 2 PUBLIC subnets  │
                         └────────────┬────────────┘
                                      │  forwards :443→:3000
                                      ▼
        ┌───────────────────────── VPC 10.0.0.0/16 ─────────────────────────┐
        │                                                                     │
        │   PUBLIC SUBNET A (10.0.1.0/24, AZ-a)   PUBLIC SUBNET B (10.0.2.0/24, AZ-b) │
        │   - ALB ENI                                - ALB ENI (2nd AZ, required)     │
        │   - NAT Gateway                                                              │
        │                                                                     │
        │   ─────────────────────────────────────────────────────────────   │
        │                                                                     │
        │   PRIVATE SUBNET A (10.0.11.0/24, AZ-a)                            │
        │   ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐ │
        │   │  EC2: frontend    │  │  EC2: backend     │  │  EC2: database     │ │
        │   │  (React+nginx,    │  │  (FastAPI,        │  │  (Postgres,        │ │
        │   │   Docker)         │  │   Docker)          │  │   Docker)          │ │
        │   │  registered in     │  │  :8000             │  │  :5432             │ │
        │   │  ALB target group  │  │                    │  │                    │ │
        │   └─────────────────┘  └─────────────────┘  └──────────────────┘ │
        │                                                                     │
        │   (a 4th "instance": the Azure DevOps self-hosted agent EC2 —      │
        │    also in a private subnet, see doc 06)                          │
        └─────────────────────────────────────────────────────────────────┘
```

## Key decision (per your note): no separate public subnet for the frontend EC2

You're right, and here's precisely why: with ACM+ALB, the thing the internet talks to is the **ALB**, not the EC2 instance. The ALB's *nodes* live in public subnets (that's an AWS requirement for internet-facing ALBs), but the **target** (your frontend EC2) only needs to be reachable *from the ALB*, which is an internal, VPC-level hop. So:

- **Public subnets (2, one per AZ)**: contain only the ALB's network interfaces + the NAT Gateway. No EC2 instances live here.
- **Private subnets (2, one per AZ for the DB/backend/frontend group — using 1 AZ is fine for a lab, 2 is production-correct)**: contain frontend, backend, database EC2 instances, all with **no public IP at all**.

This is more secure than the original "public subnet for frontend" idea and is exactly how production AWS architectures are built. Good catch on your end.

## Why an ALB needs 2 subnets in 2 different AZs

AWS requires an internet-facing ALB to be associated with at least **2 Availability Zones** for high availability — this isn't optional, the console will refuse to create it with only one subnet. So even though this is a lab, we need 2 public subnets (in 2 AZs) purely to satisfy this ALB requirement, even though nothing else lives in the second one.

## Resource naming convention used throughout this guide

To keep every step unambiguous, we'll use this naming scheme consistently:

| Resource | Name |
|---|---|
| VPC | `msa-lab-vpc` |
| Public subnet AZ-a | `msa-lab-public-a` |
| Public subnet AZ-b | `msa-lab-public-b` |
| Private subnet AZ-a | `msa-lab-private-a` |
| Internet Gateway | `msa-lab-igw` |
| NAT Gateway | `msa-lab-nat` |
| Route table (public) | `msa-lab-rt-public` |
| Route table (private) | `msa-lab-rt-private` |
| Security group - ALB | `msa-lab-sg-alb` |
| Security group - frontend | `msa-lab-sg-frontend` |
| Security group - backend | `msa-lab-sg-backend` |
| Security group - database | `msa-lab-sg-database` |
| Security group - devops agent | `msa-lab-sg-agent` |
| EC2 - frontend | `msa-lab-frontend` |
| EC2 - backend | `msa-lab-backend` |
| EC2 - database | `msa-lab-database` |
| EC2 - Azure DevOps agent | `msa-lab-devops-agent` |
| Target group | `msa-lab-tg-frontend` |
| ALB | `msa-lab-alb` |
| ACM cert | for `app.yourdomain.com` (adjust to your real domain) |

## CIDR plan

| Block | CIDR | Purpose |
|---|---|---|
| VPC | `10.0.0.0/16` | 65,536 addresses total |
| Public subnet A | `10.0.1.0/24` | ALB + NAT Gateway (AZ a) |
| Public subnet B | `10.0.2.0/24` | ALB only (AZ b, HA requirement) |
| Private subnet A | `10.0.11.0/24` | frontend, backend, database, devops-agent EC2s |

## The 6 documents that follow

1. `01-vpc-networking.md` — VPC, subnets, IGW, NAT, route tables
2. `02-security-groups.md` — the 5 security groups and exact rules
3. `03-ec2-instances.md` — launching the 4 EC2 instances + SSM setup
4. `04-application-code.md` — React frontend, FastAPI backend, Postgres, Dockerfiles
5. `05-alb-acm-route53-hostinger.md` — ALB, target group, ACM cert, DNS (Route53 + Hostinger delegation)
6. `06-azure-devops-pipelines.md` — self-hosted agent + 2 pipelines (frontend, backend)

Work through them **in this order** — each depends on resources created in the previous one. Every step below is a manual AWS Console action, written precisely (exact field names/values) so nothing is ambiguous. Where a step matters for security or correctness, I explain *why*, tying back to the OS/Docker fundamentals we covered earlier.
