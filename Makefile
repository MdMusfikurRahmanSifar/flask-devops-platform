.PHONY: help up down test lint monitoring k8s-deploy k8s-delete tf-apply tf-destroy

help:
	@echo "Available commands:"
	@echo "  make up            - Build and start the app locally"
	@echo "  make down          - Stop the app"
	@echo "  make test          - Run pytest with coverage"
	@echo "  make lint          - Run ruff, hadolint, shellcheck"
	@echo "  make monitoring    - Start the observability stack"
	@echo "  make k8s-deploy    - Deploy to local kind cluster"
	@echo "  make tf-apply      - Provision AWS infrastructure"
	@echo "  make tf-destroy    - Destroy AWS infrastructure"

up:
	docker compose up -d --build

down:
	docker compose down

test:
	cd app && pytest tests/ --cov=app --cov-fail-under=80

lint:
	ruff check app/
	hadolint Dockerfile
	shellcheck scripts/system_health.sh

monitoring:
	docker compose -f docker-compose.monitoring.yml up -d

k8s-deploy:
	kind create cluster --name devops || true
	docker tag flask-devops-platform-app:latest flask-devops-platform:local
	kind load docker-image flask-devops-platform:local --name devops
	kubectl apply -k k8s/base

k8s-delete:
	kind delete cluster --name devops

tf-apply:
	cd terraform/envs/prod && terraform apply -auto-approve

tf-destroy:
	cd terraform/envs/prod && terraform destroy -auto-approve
