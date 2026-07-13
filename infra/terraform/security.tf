# No SSH ingress anywhere in this cluster — shell access is via AWS SSM
# Session Manager (outbound-only, no open inbound port needed), which is
# why there's no bastion/key-pair resource here. The control-plane and
# worker security groups only need to talk to each other and to the
# internet (via NAT) for package installs / SSM / RKE2 binary downloads.

resource "aws_security_group" "cluster" {
  name        = "ocen-platform-rke2-cluster"
  description = "RKE2 control-plane + worker nodes — intra-cluster traffic only, no internet ingress"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "ocen-platform-rke2-cluster-sg"
  }
}

# All traffic between members of this same security group — covers the
# Kubernetes API server (6443), RKE2 supervisor (9345), kubelet (10250),
# and the Canal/Calico CNI's VXLAN (8472/udp) + BGP (179/tcp) ports
# without hand-enumerating each one; simpler to reason about and audit
# than a long port list, and still fully closed to anything outside the
# security group.
resource "aws_security_group_rule" "cluster_self_ingress" {
  type                     = "ingress"
  security_group_id        = aws_security_group.cluster.id
  source_security_group_id = aws_security_group.cluster.id
  from_port                = 0
  to_port                  = 0
  protocol                 = "-1"
  description              = "All traffic between RKE2 cluster nodes"
}

resource "aws_security_group_rule" "cluster_egress_all" {
  type              = "egress"
  security_group_id = aws_security_group.cluster.id
  cidr_blocks       = ["0.0.0.0/0"]
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  description       = "Outbound for package installs, RKE2 binaries, SSM, ECR/registry pulls"
}

# Kubernetes API server reachable from within the VPC only (e.g. a future
# bastion, VPN, or another in-VPC service) — not the public internet.
# kubectl access from a local machine goes through SSM port-forwarding
# instead (see README.md), so this rule is a defense-in-depth allowance
# for in-VPC callers, not the primary access path.
resource "aws_security_group_rule" "cluster_api_from_vpc" {
  type              = "ingress"
  security_group_id = aws_security_group.cluster.id
  cidr_blocks       = [var.vpc_cidr]
  from_port         = 6443
  to_port           = 6443
  protocol          = "tcp"
  description       = "Kubernetes API server, from within the VPC"
}
