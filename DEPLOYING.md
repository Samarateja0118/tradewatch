# Deploying

Two hosts, because the frontend is static and the API is a container. Neither
needs a database, a volume, or a secret — the briefings travel inside the image
(see `data/snapshot.db` and the note in `.gitignore`).

## 1. API

Render reads `render.yaml`, so the only manual step is the one value that
differs per environment:

1. New → Blueprint → pick this repo.
2. Set `TRADEWATCH_ALLOWED_ORIGINS` to the frontend's origin once step 2 gives
   you one (e.g. `https://tradewatch.vercel.app`). Comma-separate to allow more.
3. Note the service URL — `https://tradewatch-api.onrender.com` or similar.

Fly or Railway work identically; both take the Dockerfile as-is.

The free tier sleeps when idle, so the first request after a quiet spell takes a
few seconds. That is a cold start, not a fault.

### Verifying the image before you push it anywhere

```bash
docker build -t tradewatch-api .
docker run --rm -p 8080:8000 tradewatch-api
curl localhost:8080/api/documents?min_significance=4
```

It should return briefings with no further configuration. If it does, the
deployment will too — there is nothing else for the platform to supply.

## 2. Frontend

1. Vercel → Add New Project → this repo.
2. **Root directory: `frontend`.** Vercel detects Vite from there.
3. Environment variable `VITE_API_URL` = the API URL from step 1, no trailing
   slash.
4. Redeploy after setting it — Vite inlines env vars at build time, so a
   variable added after a build does not reach the bundle.

Then go back and set `TRADEWATCH_ALLOWED_ORIGINS` on the API to the Vercel URL.
Until you do, the API answers and the browser discards the response — the
failure looks like a broken API and is really a CORS policy doing its job.

## 3. AWS, with Terraform

`terraform/` provisions the API on Lambda. Render (above) still works and the
uvicorn `Dockerfile` is unchanged — this is a second host, not a replacement,
and keeping both is what stops the project being locked to one vendor.

Six resources, chosen to be small enough to defend line by line:

| Resource | Why it is here |
|---|---|
| S3 bucket, versioned, public access blocked | holds the SQLite snapshot |
| ECR repository, with a lifecycle policy | holds the API image |
| Lambda function (container) + function URL | runs it |
| IAM role + inline policy | `s3:GetObject` on **one object**, logs to **one group** |
| CloudWatch log group | retention set to 14 days, not "never expire" |
| S3 remote state + DynamoDB lock | so two applies cannot corrupt state |

### What changed, and why

The snapshot used to ship inside the image. That was correct for a single
container host — nothing writes to the database at runtime, so an ephemeral
filesystem cost nothing — but it meant a rebuild and a redeploy every time the
pipeline produced fresher briefings. "Keeping the data fresh" below flagged
that and deferred it. S3 decouples them: the pipeline uploads, the API picks it
up on its next cold start, and no image is rebuilt.

The least-privilege IAM policy is a consequence of that decision. It is not the
reason for it.

### Two ordering problems worth understanding

**State before Terraform.** The root config keeps state in S3 with a DynamoDB
lock, and Terraform cannot initialise a backend pointing at a bucket it has not
yet created. `terraform/bootstrap/` creates those two resources with *local*
state, once. The header comment there lays out the three ways to resolve this
and why local state is the least bad for two resources that change never.

**Image before function.** `aws_lambda_function` with `package_type = "Image"`
validates that the image exists at apply time, so a single `terraform apply` on
an empty account fails: the repository and the function are created in the same
run, and nothing has pushed to the repository yet. Hence the two-phase apply
below. This is a real limit of declarative infrastructure over an imperative
registry, not a bug — and it is a better answer to "what does Terraform not do
well" than anything invented on the spot.

### Runbook

```bash
# 0. once per account — creates the state bucket and lock table
cd terraform/bootstrap
terraform init
terraform apply -var 'state_bucket_name=tradewatch-tfstate-<suffix>'
terraform output backend_hcl      # paste into ../backend.hcl

# 1. configure
cd ..
cp backend.hcl.example backend.hcl              # fill in from the output above
cp terraform.tfvars.example terraform.tfvars    # snapshot bucket, frontend origin
terraform init -backend-config=backend.hcl

# 2. phase one — the repository must exist before an image can be pushed
terraform apply -target=aws_ecr_repository.api

# 3. build and push
REPO=$(terraform output -raw ecr_repository_url)
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin "${REPO%%/*}"
docker build --platform linux/amd64 -f Dockerfile.lambda -t "$REPO:latest" .
docker push "$REPO:latest"

# 4. phase two — everything else
terraform apply

# 5. seed the snapshot the API reads
aws s3 cp data/snapshot.db "s3://$(terraform output -raw snapshot_bucket)/snapshot.db"

# 6. check it
curl "$(terraform output -raw function_url)api/health"
```

`--platform linux/amd64` is not optional on an Apple Silicon machine. Lambda
runs x86_64 unless the function is explicitly configured for arm64, and an
arm64 image fails at invocation with an error that does not mention
architecture.

### Verifying the image before you push it

The Lambda runtime interface is testable locally. Mounting the snapshot at
`/tmp/tradewatch.db` makes the handler's S3 fetch short-circuit, so no AWS
credentials are involved:

```bash
docker build -f Dockerfile.lambda -t tradewatch-lambda .
docker run --rm -p 9000:8080 \
  -v "$(pwd)/data/snapshot.db:/tmp/tradewatch.db:ro" \
  -e TRADEWATCH_SNAPSHOT_BUCKET=stub tradewatch-lambda

curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{
  "version":"2.0","rawPath":"/api/health","rawQueryString":"","headers":{"host":"x"},
  "requestContext":{"http":{"method":"GET","path":"/api/health"}},"isBase64Encoded":false}'
```

Expect `{"statusCode":200,"body":"{\"status\":\"ok\"}"}`.

### Demonstrating drift

The reason declarative infrastructure is worth the ceremony:

```bash
# change the log retention in the console to 30 days, then
terraform plan
```

Plan reports `~ retention_in_days: 30 -> 14` and nothing else. It reached that
by comparing three things — the configuration, the recorded state, and the real
resource as the API reports it now. That third comparison is why drift is
detectable at all, and it is why `plan` is not simply a dry run of `apply`.

`terraform apply` puts it back.

### Refreshing the data

Replaces the deferred GitHub Action described below:

```bash
python -m tradewatch.main            # writes tradewatch.db
aws s3 cp tradewatch.db "s3://$(terraform output -raw snapshot_bucket)/snapshot.db"
```

No rebuild, no redeploy. Cold starts pick it up immediately; already-warm
execution environments keep serving the previous snapshot until AWS recycles
them, which for daily-published documents is an acceptable trade and is
commented as such in `api/lambda_handler.py`.

### What this configuration is not

Honest limits, because they are the interesting half:

- **No modules.** Six resources used once do not need the indirection. Modules
  earn their place at the second environment, not the first.
- **One environment.** No workspaces, no `dev`/`prod` split. Adding them means
  a `terraform.workspace` suffix on every name, which is worth doing when there
  is a second environment to protect.
- **No secrets management.** There are none to manage: the API is read-only over
  public documents. The pipeline needs `ANTHROPIC_API_KEY`, and if it moved into
  this configuration that key belongs in Parameter Store or Secrets Manager
  read at runtime, never in a `variable` — variables land in state in plaintext.
- **`image_tag` defaults to `latest`,** which makes an apply non-reproducible:
  the same config yields a different running image depending on when it ran.
  Pinning to a digest is the fix, and is a one-line change to `terraform.tfvars`.
- **DynamoDB locking** rather than the newer S3-native `use_lockfile`. The table
  is the mechanism worth being able to explain; the migration off it is easy
  once it is not the interesting part.

## Keeping the data fresh

On Render, the snapshot is a point-in-time export baked into the image, so
refreshing it means committing a regenerated `data/snapshot.db` and letting the
push trigger a redeploy. A scheduled GitHub Action running the pipeline with
`ANTHROPIC_API_KEY` from repository secrets would automate that. Deliberately
not built: it adds a scheduled job and a key to a system that needs neither, and
a stale week of briefings costs a demo nothing.

On AWS this is already solved differently — the snapshot lives in S3, so a
refresh is one `aws s3 cp` with no rebuild. See "Refreshing the data" above.
That difference is the substantive reason the AWS path exists; the rest of it is
the same application.
