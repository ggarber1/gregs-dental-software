#!/usr/bin/env bash
# Run a one-off Fargate task from the api task definition with a command
# override, wait for it to stop, and fail unless the container exited 0.
#
# Usage: run-ecs-task.sh <cluster> <task-def-arn> <subnet-id> <sg-id> <command> [args...]
set -euo pipefail

if [ "$#" -lt 5 ]; then
  echo "usage: $0 <cluster> <task-def-arn> <subnet-id> <sg-id> <command> [args...]" >&2
  exit 2
fi

CLUSTER=$1 TASK_DEF=$2 SUBNET=$3 SG=$4
shift 4

OVERRIDES=$(jq -cn --args '{containerOverrides: [{name: "api", command: $ARGS.positional}]}' -- "$@")

TASK_ARN=$(aws ecs run-task \
  --cluster "$CLUSTER" \
  --task-definition "$TASK_DEF" \
  --overrides "$OVERRIDES" \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG],assignPublicIp=DISABLED}" \
  --launch-type FARGATE \
  --query 'tasks[0].taskArn' \
  --output text)

echo "Task ARN: ${TASK_ARN} (command: $1)"

aws ecs wait tasks-stopped --cluster "$CLUSTER" --tasks "$TASK_ARN"

EXIT_CODE=$(aws ecs describe-tasks \
  --cluster "$CLUSTER" \
  --tasks "$TASK_ARN" \
  --query 'tasks[0].containers[0].exitCode' \
  --output text)

if [ "$EXIT_CODE" != "0" ]; then
  echo "Task failed with exit code ${EXIT_CODE}" >&2
  exit 1
fi

echo "Task succeeded"
