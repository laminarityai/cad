# Deploying the hosted server on AWS

Status: proposed on 2026-11-11. Nothing is deployed, and this plan creates no AWS resource. It was written against commit 70fce6b. Terms follow GLOSSARY.md. §10 lists the questions still open for the operator.

SPEC says the first version is hosted only. Today the hosted endpoint is a temporary tunnel to a laptop. This document says how the server would run on AWS, what in the code shapes that answer, and which problems the plan found before anyone pays for an instance.

Each claim about the code says how it was checked. "Measured" means a command was run for this document. "Read" means the source was read. "From memory" marks AWS and Clerk facts that were not looked up, such as prices.

## 1. Decisions the operator made

1. **AWS.** No other cloud is considered.
2. **Terraform** describes the infrastructure.
3. **Untrusted code may share a host with account data for the first private release.** Variant code runs in a locked-down container on the same instance as every account's files and the signing keys. §8 says what moves it off that host later.
4. **Region.** The operator asked for US Central. AWS has no region with that name. This plan uses `us-east-2` (Ohio), the most central US region. `us-east-1` and `us-west-2` are the other candidates, and the choice changes one Terraform variable.

## 2. What the code requires

These four facts decide the shape. Each one rules out a managed container service.

- **A Docker daemon on the same host as the server.** `sandbox/container.py` starts each build and each check with `docker run`, with read-only bind mounts from host paths under the data root. Fargate, App Runner, and Lambda give a task no Docker daemon and no host paths. (Read.)
- **One replica.** `accounts/lease.py` takes an exclusive `flock` on `<root>/accounts/lease`, and a second server on the same root refuses to start. The check lanes in `checks/lanes.py` are a queue in the process's memory. (Read.)
- **State is files on a local disk.** Each account is a directory under `<root>/accounts/`. The store keys `briefs.key` and `variants.key` sit beside the records they sign. There is no database. (Measured: a fresh root holds only `accounts/lease` after a start.)
- **The server runs from a git checkout.** `tables/`, `knowledge/`, `sandbox/`, and `web/dist` resolve from the repository root, and `server_info` runs `git rev-parse` there. A wheel or a tarball without `.git` reports the SHA as `unknown`. (Read.)

Two smaller facts set the instance size and the image flow.

- **Two containers run at once, and the number is a constant.** `SLOTS` is a semaphore of `DOCKER_MEMORY_BUDGET_MB // MEMORY_MB`, which is 4096 // 2048. Each container gets 2 GB and 2 CPUs. A larger instance does not raise throughput until that constant changes. (Read.)
- **The server never pulls an image.** `docker run` passes `--pull never`. The host must already hold `cad-sandbox:<hash>`, `cad-analysis:<hash>` and `cad-reader:<hash>`, where the hash covers the Dockerfile and `requirements.txt`. The first two images are about 1.7 GB and 2.5 GB (read). The reader is 225 MB (measured 2026-11-11).

The server process is light. Its runtime dependencies are `anthropic`, `mcp`, `packaging`, `pint`, `pyjwt`, and `pyyaml`. A `uv sync --no-dev` virtual environment is 65 MB. (Measured.) The CAD kernel lives only in the images.

## 3. The shape

```
person or MCP client
        |  HTTPS 443
   Route 53  ->  ALB (ACM certificate, idle timeout 3600 s)
        |  HTTP 8765, from the ALB security group only
   EC2 instance, x86_64, Ubuntu 24.04
     systemd: cad-http --host 0.0.0.0 --root /var/lib/cad
     Docker Engine: cad-sandbox, cad-analysis and cad-reader containers, no network
     /var/lib/cad on its own encrypted EBS volume
        |  outbound 443
   Anthropic API, Clerk, ECR, S3, Secrets Manager, pages the research step fetches
```

| Piece | Choice | Why |
|---|---|---|
| Compute | One `m7i.xlarge`, 4 vCPU and 16 GB | Two containers use 4 CPUs and 4 GB at peak. The rest is the server, Docker, and file cache for 4 GB of images |
| Architecture | x86_64 | CI builds the images on `ubuntu-latest`, and `requirements.txt` pins binary wheels by hash |
| Operating system | Ubuntu 24.04 LTS | The same family CI runs the Docker tests on |
| Data | 100 GB gp3 EBS volume, encrypted, mounted at `/var/lib/cad` | Survives the instance. Grows online |
| Entry | ALB on 443 with an ACM certificate. Port 80 redirects | TLS without a key on the instance, and a place to attach WAF |
| Network | One VPC, two public subnets. The instance has a public address and accepts traffic only from the ALB | An ALB needs two zones. No NAT gateway, which saves about $33 a month |
| Images | ECR, two repositories, tags equal to the local tags | The deploy pulls and re-tags. Nothing is built on the host |
| Releases | An S3 bucket holding a git bundle and the built web app for each SHA | The host needs no GitHub credential and no Node |
| Secrets | Secrets Manager for the Anthropic key | Read with the instance role at service start |
| Shell | Systems Manager Session Manager | No SSH port and no key pair |
| Watching | CloudWatch agent for the journal, ALB access logs to S3, alarms | The server writes no access log of its own |
| Backup | Data Lifecycle Manager snapshots of the data volume | The store keys are on that volume, so one snapshot restores everything |

## 4. Each piece

### Network and entry

- The ALB security group accepts 443 and 80 from anywhere. The instance security group accepts 8765 from the ALB security group and nothing else.
- The instance may open outbound 443 to anywhere, because the research step fetches public pages the agent names.
- The ALB health check is `GET /app/` and expects 200. The route answers 200 when the web app is built and 503 when it is not, and it answers whatever `Host` header the request carries. (Measured: 503 on a checkout with no `web/dist`, with `Host: 10.0.1.5:8799`.)
- The listener is on 443 so that the `Host` header has no port. The MCP SDK accepts only the host of `CAD_PUBLIC_URL`. The ALB passes the client's `Host` header through unchanged. (Read in `mcp/server/transport_security.py`. A request with no token gets 401 before that check runs, measured.)
- The ALB idle timeout is 3600 s. See kink 6.

### The instance

- A `cad` user owns `/opt/cad` and `/var/lib/cad` and belongs to the `docker` group. Membership in that group is root on the host. Decision 3 accepts that.
- The instance profile allows five things: read one secret, pull from two ECR repositories, read the release bucket, write logs, and register with Systems Manager.
- The metadata service requires IMDSv2 with a hop limit of 1. The sandbox containers have no network at all, and `research/fetch.py` refuses any address that is not global and connects to the address it resolved. The hop limit is a third layer, not the first.
- The service unit:

```
[Service]
User=cad
WorkingDirectory=/opt/cad/current
ExecStartPre=+/opt/cad/bin/fetch-secrets
EnvironmentFile=/run/cad/env
Environment=CLERK_PUBLISHABLE_KEY=pk_live_...
Environment=CAD_PUBLIC_URL=https://<domain>
ExecStart=/opt/cad/current/.venv/bin/cad-http --host 0.0.0.0 --port 8765 --root /var/lib/cad
Restart=on-failure
UMask=0022
TimeoutStopSec=15
```

`fetch-secrets` writes `ANTHROPIC_API_KEY=<key>` to `/run/cad/env`, which is memory, with mode 0600. The Clerk publishable key and the public URL are not secrets.

### Sign-in

- The server holds no Clerk secret. `accounts/clerk.py` derives the Clerk Frontend API host from `CLERK_PUBLISHABLE_KEY` and fetches its JWKS on first use. (Measured: the server starts with a placeholder key and makes no call to Clerk at start.)
- `CAD_PUBLIC_URL` must start with `https://`. `<url>/mcp` is the audience an agent token must carry, and the origin is the `azp` a session token must name. Every MCP client is configured with that URL, and its tokens carry it, so choose the domain once.
- A production Clerk instance needs DNS records on the domain, its own Google OAuth client, and whatever setting lets MCP clients register. (From memory. Confirm in the Clerk dashboard before the first deploy.)
- Sign-up is restricted to an allowlist in Clerk for the private release. See kink 4.

### A release

A release is one commit on `main` that passed CI. The server's layout on the host:

```
/opt/cad/releases/<sha>/     a git checkout, its .venv, and web/dist
/opt/cad/current             a symlink to one release
/var/lib/cad/                the data root
```

A `deploy` workflow in GitHub Actions, started by hand with a SHA, does this:

1. It assumes an AWS role through GitHub's OIDC provider. No long-lived AWS key is stored in GitHub.
2. It builds the three images with `uv run cad-sandbox build-image` and `uv run cad-reader build-image` and pushes them to ECR under the same tags.
3. It builds the web app, writes `git bundle create release.bundle HEAD`, and uploads the bundle and `web/dist` to `s3://<bucket>/releases/<sha>/`.
4. It runs `/opt/cad/bin/deploy <sha>` on the instance through Systems Manager and fails if the script fails.

The `deploy` script on the instance:

1. Pulls the three images from ECR and tags them with the bare names the server looks up.
2. Fetches the bundle into `/opt/cad/releases/<sha>` and checks out the SHA.
3. Runs `uv sync --locked --no-dev` and unpacks `web/dist`. Git ignores both, so the tree stays clean.
4. Proves the release before any person sees it. With a temporary `HOME`, it runs `cad-call server_info` and `cad-call build_variant` over stdio. The first must report the SHA and `dirty: false`. The second must return `built`, which proves Docker and both image tags.
5. Points `current` at the release and restarts the service.
6. Waits for `GET http://127.0.0.1:8765/app/` to answer 200.

Rollback is step 5 with the previous SHA. Images and releases for the last five SHAs stay on the host and in ECR.

### Backup and restore

- Data Lifecycle Manager snapshots the data volume every hour and keeps 24 hourly and 14 daily snapshots.
- A snapshot of a running volume is safe here. Every record is written to a temporary file and renamed into place by `records/files.py`, so a snapshot holds either the old file or the new one.
- Recovery from a lost instance or a lost zone is `terraform apply` with the newest snapshot as the volume source, then one deploy. The data lost is at most one hour. The time to recover is about 30 minutes and has not been rehearsed.
- Run one restore drill before the first outside user. A backup that was never restored is not known to work.

### Watching

- The CloudWatch agent ships the service's journal. The server logs at `warning`, so normal traffic produces almost nothing.
- ALB access logs go to S3. They are the only record of requests.
- Alarms: target unhealthy, ALB 5xx rate, data volume above 70% full, instance status check failed, memory above 85%.
- An AWS Budgets alert on the account, and a monthly spend limit on the Anthropic workspace.

### Terraform

The code lives in `infra/aws/` in this repository, with remote state in an S3 bucket created once by hand. Suggested modules: `network`, `entry` (ALB, certificate, DNS), `instance`, `data` (volume and snapshots), `registry`, `release_bucket`, `iam`, and `watching`. CI runs `terraform fmt -check` and `terraform validate`. `terraform apply` is run by a person.

## 5. Kinks found, and what the plan does about each

1. **AWS has no US Central region.** The plan uses `us-east-2`. Confirm.
2. **The server cannot run from a package.** It needs the checkout and `.git`. The plan ships a git bundle through S3, so the host holds a real checkout and no GitHub credential. The bundle flow is untested.
3. **Nothing checks at start that the images exist.** The server started with no Docker check. (Measured.) A missing tag would surface as an error on a person's first build. The deploy script's stdio build catches it before the switch.
4. **The daily cap covers container seconds only.** `sandbox/meter.py` meters `build` and `check`. Nothing limits what one account spends on the Anthropic key, apart from 100 steps a turn. (Read.) For the private release the plan restricts who can sign up, gives the server its own Anthropic workspace with a spend limit, and adds a budget alert. A per-account chat limit is a code change. See §6.
5. **No health route.** `server_info` over HTTP needs a Clerk token, so the load balancer cannot ask for the SHA. `GET /app/` is the health check, and the SHA is proven over stdio during the deploy.
6. **A quiet stream can outlast the default idle timeout.** The ALB closes a connection after 60 s with no bytes. I found no keep-alive in the chat stream, and a turn can wait on a 60 s build. (Read, by search.) The plan sets the idle timeout to 3600 s. A keep-alive comment every 15 s would be the sturdier fix.
7. **A restart drops work in progress.** The server exits 0.2 s after SIGTERM when idle and waits at most 3 s for open requests. (Measured and read.) A chat turn in progress is cut. A check job in progress is lost and starts again on the next `score_variant`. After `ATTEMPT_CAP = 2` interruptions the job is refused until an operator deletes its `.attempt` file, so two deploys during one long analysis strand it. Deploy at a quiet hour. What an Auto run does across a restart was not checked.
8. **Some deploys make every stored variant outdated.** A variant id hashes the source under `variants/` and `sandbox/`. After a deploy that touches either, each variant is rebuilt when it is next opened. I infer that the rebuild counts against the account's daily cap. Say so in the release note, and raise `--cap-seconds` for that day if needed.
9. **The data root only grows.** No code deletes variants, meshes, job results, or old stage directories. (Read, by search for deletes.) The plan starts at 100 GB, alarms at 70%, and grows the volume online. The deploy prunes image tags older than five releases, since each analysis image is 2.5 GB.
10. **The sandbox user must read the bind mounts.** Containers run as uid 65534. The stage directory is made world-readable by code, and variant files depend on the service's umask. The unit sets `UMask=0022`. A stricter umask would break every check. CI covers the default case on Ubuntu.
11. **One instance in one zone.** A failed instance or zone is downtime until a person restores. That is acceptable for a private release and is the first thing §8 changes.
12. **Rollback is not always clean.** No record format has a migration. A rollback after a release that changed a format may meet records it cannot read. Keep format changes in their own release, and snapshot before deploying one.
13. **Request bodies have no size limit outside the confirmation page.** (Read, by search.) A WAF rule on the ALB can cap body size and rate per address. It is optional for the private release.

## 6. Code changes that would help

None blocks a first deploy. They are listed in the order I would do them.

1. A `/healthz` route with no sign-in that returns the SHA. It replaces the `/app/` health check and lets the deploy workflow prove the running server's SHA from outside.
2. A keep-alive on the chat stream.
3. A per-account limit on chat spend, beside the container-seconds cap.
4. `DOCKER_MEMORY_BUDGET_MB` read from the host or from a flag, so a larger instance runs more containers.
5. A check at start that both image tags exist, failing the start with the tag name.
6. A way to delete an account's old variants and job results.

## 7. Cost

On-demand in `us-east-2`, from memory. Check the numbers in the AWS pricing calculator before relying on them.

| Item | A month |
|---|---|
| `m7i.xlarge` | about $147 |
| ALB | about $22 |
| EBS, 100 GB data and 30 GB root | about $11 |
| Three public IPv4 addresses | about $11 |
| Snapshots, ECR, logs, secrets, DNS | about $10 |
| **Total before Anthropic usage** | **about $200** |

Anthropic usage is likely the larger bill once people use the chat. A one-year savings plan cuts the instance cost by roughly a third, once the size is settled.

## 8. When one instance is not enough

In this order.

1. **A larger instance**, after code change 4. It is the cheapest step.
2. **Sandbox workers on their own hosts.** The server queues a job, a worker with Docker and no account data runs it, and the result comes back signed. This step also ends decision 3, because untrusted code no longer shares a host with the keys. It changes `checks/lanes.py` and the stage mounts, and the protocol models cover that code.
3. **More than one server.** The lease, the in-memory queue, and the file store all assume one process. Replacing them is a redesign and needs an ADR.

## 9. Order of work

When the operator decides to deploy:

1. Accounts: an AWS account, the domain, a production Clerk instance, and an Anthropic workspace with a spend limit.
2. Terraform for the network, entry, instance, data volume, registry, and release bucket.
3. The `deploy` workflow and the two host scripts, `fetch-secrets` and `deploy`.
4. A first deploy, then a live walk in the web app and from one MCP client.
5. A restore drill from a snapshot.
6. The allowlist opens to the first outside people.

## 10. Open questions for the operator

1. Is `us-east-2` the region you meant by US Central?
2. Which domain will the server use? Every MCP client is configured with it.
3. Should the topology be recorded as an ADR when the deploy starts? It is hard to reverse, so I think so.
4. Do you want a second, smaller environment for staging against a Clerk test instance, or is a local run enough before each deploy?
5. Who is on the first allowlist?

## How this was checked

- The server was started from commit 70fce6b with a placeholder `CLERK_PUBLISHABLE_KEY`, `CAD_PUBLIC_URL=https://cad.example.com`, and a fresh `--root`. `GET /app/` answered 503 on a checkout with no web build. The protected-resource metadata answered 200 with `Host: 10.0.1.5:8799`. `POST /mcp` with no token answered 401 and named the metadata URL under the public origin. SIGTERM ended the idle process in 0.2 s. The root held only `accounts/lease`.
- Everything else about the code was read from source at that commit.
- Nothing was run on AWS. Nothing was run on Linux for this document.
