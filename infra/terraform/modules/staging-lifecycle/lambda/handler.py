"""
Midnight staging lifecycle Lambda.

Runs at midnight (5 AM UTC) and stops any staging resources left running.
Sends an SNS email alert if anything had to be stopped — so you know next
morning that it ran and what it found.

Idempotent: stopping an already-stopped resource is a no-op (handled via
status checks before issuing stop calls).
"""

import json
import os

import boto3

ecs = boto3.client("ecs")
rds = boto3.client("rds")
ec2 = boto3.client("ec2")
sns = boto3.client("sns")

ECS_CLUSTER_ARN = os.environ["ECS_CLUSTER_ARN"]
ECS_SERVICE_NAMES = [s.strip() for s in os.environ["ECS_SERVICE_NAMES"].split(",") if s.strip()]
RDS_INSTANCE_ID = os.environ["RDS_INSTANCE_ID"]
NAT_INSTANCE_ID = os.environ["NAT_INSTANCE_ID"]
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
ENV = os.environ["ENV"]


def handler(event, context):
    stopped = []

    # Stop ECS services with running tasks
    if ECS_SERVICE_NAMES:
        services = ecs.describe_services(
            cluster=ECS_CLUSTER_ARN,
            services=ECS_SERVICE_NAMES,
        )["services"]

        for svc in services:
            if svc.get("desiredCount", 0) > 0:
                ecs.update_service(
                    cluster=ECS_CLUSTER_ARN,
                    service=svc["serviceName"],
                    desiredCount=0,
                )
                stopped.append(f"ECS service: {svc['serviceName']} (was desiredCount={svc['desiredCount']})")

    # Stop RDS if available
    try:
        db = rds.describe_db_instances(DBInstanceIdentifier=RDS_INSTANCE_ID)["DBInstances"][0]
        if db["DBInstanceStatus"] == "available":
            rds.stop_db_instance(DBInstanceIdentifier=RDS_INSTANCE_ID)
            stopped.append(f"RDS: {RDS_INSTANCE_ID}")
    except rds.exceptions.DBInstanceNotFoundFault:
        pass  # already destroyed as part of staging-down

    # Stop NAT instance if running
    try:
        reservations = ec2.describe_instances(InstanceIds=[NAT_INSTANCE_ID])["Reservations"]
        if reservations:
            instance = reservations[0]["Instances"][0]
            state = instance["State"]["Name"]
            if state == "running":
                ec2.stop_instances(InstanceIds=[NAT_INSTANCE_ID])
                stopped.append(f"NAT instance: {NAT_INSTANCE_ID}")
    except ec2.exceptions.ClientError:
        pass  # instance may not exist

    if stopped:
        lines = "\n".join(f"  - {s}" for s in stopped)
        message = (
            f"[dental-pms {ENV}] Midnight lifecycle stopped resources that were left running:\n"
            f"{lines}\n\n"
            f"Run 'make staging-up' when you're ready to work again."
        )
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f"[dental-pms {ENV}] Staging auto-stopped at midnight",
            Message=message,
        )
        print(message)
    else:
        print(f"[{ENV}] Midnight lifecycle: nothing was running, no action taken.")

    return {"stopped": stopped}
