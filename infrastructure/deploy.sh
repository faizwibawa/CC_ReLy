#!/usr/bin/env bash
# Deploy (or update) the ReLy backend. Run from the repository root in AWS CloudShell:
#     bash infrastructure/deploy.sh
#
# What it does:
#   1. Finds the AWS Academy "LabRole".
#   2. Creates a private S3 bucket for the Lambda code package (if missing).
#   3. Zips backend/src and uploads it.
#   4. Deploys infrastructure/template.yaml with CloudFormation, acting as LabRole.
#   5. Prints the API URL and runs a health check.
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
STACK="${RELY_STACK:-rely-stack}"
ALLOWED_ORIGIN="${RELY_ALLOWED_ORIGIN:-*}"
export AWS_DEFAULT_REGION="$REGION"

cd "$(dirname "$0")/.."

echo "==> Identity"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
LAB_ROLE_ARN=$(aws iam get-role --role-name LabRole --query Role.Arn --output text)
echo "    region=$REGION stack=$STACK (LabRole found)"

BUCKET="rely-artifacts-${ACCOUNT}-${REGION}"
echo "==> Artifact bucket"
if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  aws s3api create-bucket --bucket "$BUCKET" >/dev/null
  aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  echo "    created private bucket"
else
  echo "    bucket exists"
fi

echo "==> Packaging Lambda"
mkdir -p build
rm -f build/handler.zip
(cd backend/src && zip -q -r ../../build/handler.zip . -x '__pycache__/*' '*.pyc')
KEY="lambda/handler-$(date +%Y%m%d%H%M%S).zip"   # unique key forces a code update
aws s3 cp --quiet build/handler.zip "s3://$BUCKET/$KEY"
echo "    uploaded s3://<artifact-bucket>/$KEY"

echo "==> Deploying CloudFormation stack (this takes ~1-2 minutes)"
aws cloudformation deploy \
  --stack-name "$STACK" \
  --template-file infrastructure/template.yaml \
  --role-arn "$LAB_ROLE_ARN" \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
      LabRoleArn="$LAB_ROLE_ARN" \
      CodeBucket="$BUCKET" \
      CodeKey="$KEY" \
      AllowedOrigin="$ALLOWED_ORIGIN"

API_URL=$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)
API_URL="${API_URL%/}"

echo "==> Health check"
curl -s -w '\n    HTTP %{http_code}\n' "$API_URL/"

cat <<EOF

ReLy backend deployed.
  RELY_API_URL=$API_URL

Put that line in your local .env (gitignored). Do NOT commit it.
Next: python backend/tests/api_smoke_test.py   (uses RELY_API_URL)
EOF
