output "vpc_id" {
  value = aws_vpc.main.id
}

output "control_plane_instance_id" {
  description = "SSM into this: aws ssm start-session --target <this-id> --region ap-south-1"
  value       = aws_instance.control_plane.id
}

output "control_plane_private_ip" {
  value = aws_instance.control_plane.private_ip
}

output "worker_instance_id" {
  description = "SSM into this: aws ssm start-session --target <this-id> --region ap-south-1"
  value       = aws_instance.worker.id
}

output "kubectl_via_ssm_command" {
  description = "One-liner to fetch nodes without an interactive session — see README.md for the full kubeconfig retrieval flow."
  value       = "aws ssm start-session --target ${aws_instance.control_plane.id} --region ${var.aws_region} --document-name AWS-StartInteractiveCommand --parameters command=\"sudo KUBECONFIG=/etc/rancher/rke2/rke2.yaml kubectl get nodes\""
}
