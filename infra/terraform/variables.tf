variable "aws_region" {
  description = "AWS region — must match CLAUDE.md's stated target (ap-south-1)."
  type        = string
  default     = "ap-south-1"
}

variable "environment" {
  description = "Deployment environment tag. This foundation is explicitly framed as temporary/minimal until proven out — see README.md's teardown section."
  type        = string
  default     = "dev"
}

variable "vpc_cidr" {
  description = "VPC CIDR block. 10.60.0.0/16 chosen to avoid collision with existing account VPCs (10.0.0.0/16 x2 for the unrelated tally-sync-agent project, 172.31.0.0/16 default VPC) — verified via `aws ec2 describe-vpcs` before picking this range."
  type        = string
  default     = "10.60.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones to spread subnets across."
  type        = number
  default     = 2
}

variable "control_plane_instance_type" {
  description = "EC2 instance type for the RKE2 control-plane node."
  type        = string
  default     = "t3.medium"
}

variable "worker_instance_type" {
  description = "EC2 instance type for the RKE2 worker node."
  type        = string
  default     = "t3.medium"
}

variable "rke2_version" {
  description = "RKE2 channel/version to install. \"stable\" tracks the latest stable release at apply time — pin to an exact version (e.g. v1.30.4+rke2r1) once this cluster is more than a throwaway foundation."
  type        = string
  default     = "stable"
}
