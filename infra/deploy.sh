#!/usr/bin/env bash
set -euo pipefail

REPO_NAME=${REPO_NAME:=rail-debug}
IMAGE_TAG=${IMAGE_TAG:=latest}

# Ensure repo exists
aws ecr describe-repositories --repository-names "$REPO_NAME" >/dev/null 2>&1 || \
  aws ecr create-repository --repository-name "$REPO_NAME" >/dev/null

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=$(aws configure get region || echo "us-east-1")
REPO_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO_NAME"

# ECR login
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

# Build and push
docker build -t $REPO_NAME:build ../app
docker tag $REPO_NAME:build $REPO_URI:$IMAGE_TAG
docker push $REPO_URI:$IMAGE_TAG

# Deploy CDK stack
cdk deploy RailDebugStack --require-approval never

# Optional: Test endpoint (replace DNS)
# curl -sS -X POST "http://your-alb-dns/debug-rail-code" -H "Content-Type: application/json" \
#   -d '{"query": "Why does this rail code fail?", "few_shot_examples": [], "docs": []}'
