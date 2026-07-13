# One IAM role shared by both nodes — same trust policy and baseline
# permissions either way; the control-plane's extra "write the join
# token" permission and the worker's "read the join token" permission
# are the only asymmetry, both scoped to the single SSM parameter below.

data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "rke2_node" {
  name               = "ocen-platform-rke2-node"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
}

# AWS-managed policy for Session Manager connectivity — this is what
# lets us skip SSH/bastion entirely.
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.rke2_node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Least-privilege access to exactly one SSM parameter — the RKE2 join
# token — not broad ssm:* on all parameters.
data "aws_iam_policy_document" "rke2_token_parameter" {
  statement {
    sid = "ReadWriteJoinTokenParameter"
    actions = [
      "ssm:PutParameter",
      "ssm:GetParameter",
    ]
    resources = [
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter${local.rke2_token_parameter_name}",
    ]
  }
}

resource "aws_iam_role_policy" "rke2_token_parameter" {
  name   = "rke2-join-token-parameter-access"
  role   = aws_iam_role.rke2_node.id
  policy = data.aws_iam_policy_document.rke2_token_parameter.json
}

# Scoped CloudWatch Logs write for RKE2 unit logs — a dedicated log
# group, not the broad CloudWatchAgentServerPolicy managed policy.
data "aws_iam_policy_document" "rke2_logs" {
  statement {
    sid = "WriteRke2LogGroup"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams",
    ]
    resources = ["${aws_cloudwatch_log_group.rke2.arn}:*"]
  }
}

resource "aws_iam_role_policy" "rke2_logs" {
  name   = "rke2-cloudwatch-logs-write"
  role   = aws_iam_role.rke2_node.id
  policy = data.aws_iam_policy_document.rke2_logs.json
}

resource "aws_cloudwatch_log_group" "rke2" {
  name              = "/ocen-platform/rke2"
  retention_in_days = 14

  tags = {
    Name = "ocen-platform-rke2-logs"
  }
}

resource "aws_iam_instance_profile" "rke2_node" {
  name = "ocen-platform-rke2-node"
  role = aws_iam_role.rke2_node.name
}

data "aws_caller_identity" "current" {}
