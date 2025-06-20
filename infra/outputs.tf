output "backend_repo_url" {
  description = "ECR repo URI for the backend image"
  value       = aws_ecr_repository.backend.repository_url
}

output "ui_repo_url" {
  description = "ECR repo URI for the Chainlit UI image"
  value       = aws_ecr_repository.ui.repository_url
}
