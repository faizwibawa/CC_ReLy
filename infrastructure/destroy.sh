#!/usr/bin/env bash
# Delete every ReLy resource created by deploy.sh. Run in AWS CloudShell:
#     bash infrastructure/destroy.sh
# (The AWS Academy sandbox also wipes resources when the session ends.)
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
STACK="${RELY_STACK:-rely-stack}"
export AWS_DEFAULT_REGION="$REGION"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="rely-artifacts-${ACCOUNT}-${REGION}"

echo "==> Deleting stack $STACK (table, Lambda, Function URL, log group)"
aws cloudformation delete-stack --stack-name "$STACK"
aws cloudformation wait stack-delete-complete --stack-name "$STACK"

echo "==> Emptying and deleting artifact bucket"
if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  aws s3 rm "s3://$BUCKET" --recursive --quiet
  aws s3api delete-bucket --bucket "$BUCKET"
fi

echo "==> Verifying"
aws dynamodb list-tables --query "TableNames[?starts_with(@, 'ReLy')]" --output text
aws lambda list-functions --query "Functions[?starts_with(FunctionName, 'ReLy')].FunctionName" --output text
echo "Done. Empty output above means everything was removed."
