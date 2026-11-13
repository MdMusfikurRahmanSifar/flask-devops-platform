terraform {
  backend "s3" {
    bucket         = "flask-devops-tfstate-<YOUR_AWS_ACCOUNT_ID>"
    key            = "prod/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "flask-devops-tflock"
    encrypt        = true
  }
}
