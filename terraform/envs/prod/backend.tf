terraform {
  backend "s3" {
    bucket       = "flask-devops-tfstate-050752609622"
    key          = "prod/terraform.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }
}
