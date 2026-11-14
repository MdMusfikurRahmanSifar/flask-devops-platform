terraform {
  required_version = ">= 1.7.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
  }
}

provider "aws" {
  region = "ap-south-1"
}



# ── Networking ────────────────────────────────────────────────────────────
resource "aws_security_group" "app_sg" {
  name        = "flask-devops-app-sg"
  description = "Allow HTTP traffic"
  
  ingress {
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── ECR ───────────────────────────────────────────────────────────────────
resource "aws_ecr_repository" "app_repo" {
  name                 = "flask-devops-platform"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

# ── IAM for EC2 ───────────────────────────────────────────────────────────
resource "aws_iam_role" "ec2_role" {
  name = "flask-devops-ec2-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ec2_ecr" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_role_policy_attachment" "ec2_ssm" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name = "flask-devops-ec2-profile"
  role = aws_iam_role.ec2_role.name
}

# ── IAM for GitHub Actions (OIDC) ─────────────────────────────────────────
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

resource "aws_iam_role" "github_actions" {
  name = "flask-devops-github-actions"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = { "token.actions.githubusercontent.com:aud" : "sts.amazonaws.com" },
        StringLike = { "token.actions.githubusercontent.com:sub" : "repo:*flask-devops-platform*" }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "gh_ecr" {
  role       = aws_iam_role.github_actions.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser"
}

resource "aws_iam_role_policy_attachment" "gh_ssm" {
  role       = aws_iam_role.github_actions.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMFullAccess"
}

# ── EC2 Instance ──────────────────────────────────────────────────────────
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
}

resource "aws_instance" "app_server" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.micro"
  iam_instance_profile   = aws_iam_instance_profile.ec2_profile.name
  vpc_security_group_ids = [aws_security_group.app_sg.id]

  user_data = <<-EOF
              #!/bin/bash
              apt-get update -y
              apt-get install -y docker.io awscli
              systemctl start docker
              systemctl enable docker
              usermod -aG docker ubuntu
              EOF

  tags = {
    Name = "flask-devops-app-server"
  }
}

# ── Outputs ───────────────────────────────────────────────────────────────
output "ec2_public_ip" {
  value = aws_instance.app_server.public_ip
}

output "ec2_instance_id" {
  value = aws_instance.app_server.id
}

output "github_actions_role_arn" {
  value = aws_iam_role.github_actions.arn
}

# Allow GitHub Actions to fetch the EC2 Public IP for the smoke test
resource "aws_iam_role_policy_attachment" "gh_ec2_read" {
  role       = aws_iam_role.github_actions.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess"
}
