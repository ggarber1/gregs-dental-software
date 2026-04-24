#!/usr/bin/env bash
# LocalStack init script — runs once on first startup after service is ready.
# Creates all S3 buckets and SQS queues needed for local development.
# Idempotent: awslocal ignores "already exists" errors for queues/buckets.

set -euo pipefail

AWS_FLAGS="--endpoint-url http://localhost:4566 --region us-east-1"

echo "==> Creating S3 buckets..."
for bucket in \
  dental-phi-documents-local \
  dental-era-files-local \
  dental-exports-local; do
  awslocal s3 mb "s3://${bucket}" ${AWS_FLAGS} 2>/dev/null || echo "  ${bucket} already exists"
  # Block all public access (mirrors prod KMS-encrypted buckets)
  awslocal s3api put-public-access-block \
    --bucket "${bucket}" \
    --public-access-block-configuration \
      "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" \
    ${AWS_FLAGS}
  echo "  created: ${bucket}"
done

echo "==> Creating SQS queues..."
for queue in \
  dental-reminders-queue \
  dental-eligibility-queue \
  dental-era-queue \
  dental-audit-logs-queue; do
  awslocal sqs create-queue --queue-name "${queue}" ${AWS_FLAGS} 2>/dev/null || echo "  ${queue} already exists"
  echo "  created: ${queue}"
done

echo "==> Creating SQS dead-letter queues..."
for queue in \
  dental-reminders-dlq \
  dental-eligibility-dlq \
  dental-era-dlq; do
  awslocal sqs create-queue --queue-name "${queue}" ${AWS_FLAGS} 2>/dev/null || echo "  ${queue} already exists"
  echo "  created: ${queue}"
done

echo "==> Wiring DLQ redrive policies..."
# dental-reminders-dlq: max 3 receive attempts before messages land in DLQ.
REMINDERS_DLQ_ARN=$(awslocal sqs get-queue-attributes \
  --queue-url "http://localhost:4566/000000000000/dental-reminders-dlq" \
  --attribute-names QueueArn \
  ${AWS_FLAGS} \
  --query 'Attributes.QueueArn' --output text)

awslocal sqs set-queue-attributes \
  --queue-url "http://localhost:4566/000000000000/dental-reminders-queue" \
  --attributes "{\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${REMINDERS_DLQ_ARN}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}" \
  ${AWS_FLAGS} 2>/dev/null || echo "  redrive policy already set or skipped"
echo "  dental-reminders-queue -> dental-reminders-dlq (maxReceiveCount=3)"

echo "==> LocalStack resources ready."
