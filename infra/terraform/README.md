# RKE2 foundation — Terraform

This is the first slice of the RKE2/K8s target architecture named in
CLAUDE.md's tech-stack table. It provisions exactly one thing: a VPC and
a two-node RKE2 cluster (one control-plane, one worker) reachable via
`kubectl` over AWS SSM. It does **not** provision APISIX, SigNoz, RDS
Postgres, or move any of the existing systemd-based services
(`infra/deploy/`) onto the cluster — those are explicit follow-up phases.

This is real infrastructure with real ongoing AWS spend (2× `t3.medium`
+ 1 NAT gateway ≈ a few USD/day in `ap-south-1`), not a sandboxed
simulation. Read the whole file before running `terraform apply`.

## Bootstrap (one-time, already done for this account)

Terraform's own state needs somewhere to live before Terraform can do
anything — a chicken-and-egg problem, so this step is plain AWS CLI, not
part of the `.tf` files:

```bash
aws s3api create-bucket --bucket ocen-platform-tfstate-572914130294 \
  --region ap-south-1 --create-bucket-configuration LocationConstraint=ap-south-1
aws s3api put-bucket-versioning --bucket ocen-platform-tfstate-572914130294 \
  --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket ocen-platform-tfstate-572914130294 \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-public-access-block --bucket ocen-platform-tfstate-572914130294 \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws dynamodb create-table \
  --table-name ocen-platform-tfstate-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region ap-south-1
```

Already run for account `572914130294` — bucket and table both exist.
Only re-run this if standing up a fresh AWS account.

## Apply

```bash
cd infra/terraform
terraform init
terraform validate
terraform plan       # review every resource before proceeding
terraform apply      # real spend starts here — confirm the resource count matches the plan
```

Expect ~12-15 resources: VPC, IGW, 2 public + 2 private subnets, 1 NAT
gateway + EIP, 2 route tables + associations, 1 security group + 3
rules, 1 IAM role + 2 inline policies + 1 managed policy attachment + 1
instance profile, 1 CloudWatch log group, 2 EC2 instances.

Boot + join takes a few minutes — the worker's `user_data` polls SSM for
the control-plane's join token for up to 10 minutes before failing, so
don't expect `kubectl get nodes` to show both nodes `Ready` immediately
after `terraform apply` returns.

## Verify

No SSH, no bastion — everything goes through SSM Session Manager
(`AmazonSSMManagedInstanceCore` on the instance role). Confirm the
`tally-sync-admin` IAM identity (or whichever identity you're using) has
`ssm:StartSession` — it already has `AdministratorAccess`, so this is
covered for the account this was built against.

**One-liner, no interactive session:**

```bash
terraform output -raw kubectl_via_ssm_command | bash
```

**Interactive session** (for troubleshooting, checking `/var/log/rke2-bootstrap.log`, etc.):

```bash
aws ssm start-session --target "$(terraform output -raw control_plane_instance_id)" --region ap-south-1
# once connected:
sudo tail -f /var/log/rke2-bootstrap.log
sudo KUBECONFIG=/etc/rancher/rke2/rke2.yaml kubectl get nodes -o wide
```

Both nodes should show `Ready` once the worker has joined.

**Full kubeconfig, for a local machine:**

```bash
# 1. Start an SSM port-forward from your machine to the control-plane's :6443
aws ssm start-session \
  --target "$(terraform output -raw control_plane_instance_id)" \
  --region ap-south-1 \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["6443"],"localPortNumber":["6443"]}'

# 2. In a second terminal, fetch the kubeconfig content via SSM (not scp — no SSH)
aws ssm start-session \
  --target "$(terraform output -raw control_plane_instance_id)" \
  --region ap-south-1 \
  --document-name AWS-StartInteractiveCommand \
  --parameters command="sudo cat /etc/rancher/rke2/rke2.yaml" > /tmp/rke2-raw.yaml

# 3. Rewrite the server URL from https://127.0.0.1:6443 to match the local
#    port-forward (same value here, since RKE2's default kubeconfig already
#    points at localhost) and use it:
export KUBECONFIG=/tmp/rke2-raw.yaml
kubectl get nodes
```

The SSM command output includes a couple of header/footer lines from the
session wrapper — strip those from `/tmp/rke2-raw.yaml` before pointing
`kubectl` at it (a one-time manual step; scripting this cleanly is a
follow-up if this becomes a routine flow rather than a one-off check).

## Teardown

This foundation was built to be genuinely real (per the explicit
decision to build the RKE2/K8s target architecture rather than a
throwaway), but nothing depends on it yet — safe to tear down and
recreate at any point before something is actually deployed onto it.

```bash
cd infra/terraform
terraform plan -destroy   # dry-run first, confirm exactly what will be removed
terraform destroy
```

This does **not** remove the bootstrap S3 bucket or DynamoDB table
(state storage — kept across teardown/recreate cycles) or the
`/ocen-platform/rke2/join-token` SSM parameter (harmless to leave; the
next `apply` overwrites it with a fresh token).

## What's next (not in this phase)

- APISIX ingress controller
- SigNoz observability stack
- RDS Postgres (or in-cluster Postgres — undecided) for services that
  move onto the cluster
- Migrating `ocen-gateway`/`ocen-worker`/Keycloak from the existing
  systemd-on-EC2 pattern (`infra/deploy/`) onto this cluster
- TLS / cert-manager, DNS
- Deploying the Platform Console (`project-k-admin-console`) onto the
  cluster — it runs locally against a local backend for now
