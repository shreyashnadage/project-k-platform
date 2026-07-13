locals {
  rke2_token_parameter_name = "/ocen-platform/rke2/join-token"
}

# Canonical's official Ubuntu 22.04 LTS AMI — SSM agent pre-installed,
# which is what makes the no-SSH/no-bastion access model work.
data "aws_ami" "ubuntu_2204" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_instance" "control_plane" {
  ami                    = data.aws_ami.ubuntu_2204.id
  instance_type          = var.control_plane_instance_type
  subnet_id              = aws_subnet.private[0].id
  vpc_security_group_ids = [aws_security_group.cluster.id]
  iam_instance_profile   = aws_iam_instance_profile.rke2_node.name

  root_block_device {
    volume_size = 40
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = templatefile("${path.module}/user_data/rke2-server.sh.tftpl", {
    aws_region           = var.aws_region
    rke2_version         = var.rke2_version
    token_parameter_name = local.rke2_token_parameter_name
  })

  tags = {
    Name = "ocen-platform-rke2-control-plane"
    Role = "rke2-server"
  }
}

resource "aws_instance" "worker" {
  ami                    = data.aws_ami.ubuntu_2204.id
  instance_type          = var.worker_instance_type
  subnet_id              = aws_subnet.private[0].id
  vpc_security_group_ids = [aws_security_group.cluster.id]
  iam_instance_profile   = aws_iam_instance_profile.rke2_node.name

  root_block_device {
    volume_size = 40
    volume_type = "gp3"
    encrypted   = true
  }

  # Depends on control_plane implicitly via the private_ip reference below
  # — Terraform won't create the worker until the control-plane instance
  # (and thus its private IP) exists. The worker's own user_data then
  # polls SSM at boot for the join token, which may take a few minutes
  # for the control-plane to publish — see rke2-agent.sh.tftpl.
  user_data = templatefile("${path.module}/user_data/rke2-agent.sh.tftpl", {
    aws_region           = var.aws_region
    rke2_version         = var.rke2_version
    token_parameter_name = local.rke2_token_parameter_name
    server_private_ip    = aws_instance.control_plane.private_ip
  })

  tags = {
    Name = "ocen-platform-rke2-worker"
    Role = "rke2-agent"
  }
}
