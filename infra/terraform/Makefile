STAGING_DIR := infra/terraform/environments/staging

.PHONY: staging-up staging-down staging-verify

# staging-verify: confirm everything is healthy after a first apply.
# Run AFTER make staging-up so ECS and ElastiCache are present.
# Each check prints OK or FAIL. A FAIL does not abort — you see all results.
staging-verify:
	@echo "======================================================"
	@echo " Staging verification"
	@echo "======================================================"
	@echo ""

	@echo "--- Terraform outputs ---"
	@cd $(STAGING_DIR) && terraform output
	@echo ""

	@echo "--- VPC ---"
	@VPC_ID=$$(cd $(STAGING_DIR) && terraform output -json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('')" 2>/dev/null || echo ""); \
	aws ec2 describe-vpcs --filters "Name=tag:Project,Values=dental-pms" "Name=tag:Environment,Values=staging" \
	  --query 'Vpcs[0].State' --output text | grep -q available \
	  && echo "  VPC: OK" || echo "  VPC: FAIL"
	@echo ""

	@echo "--- RDS ---"
	@aws rds describe-db-instances --db-instance-identifier dental-staging \
	  --query 'DBInstances[0].DBInstanceStatus' --output text 2>/dev/null \
	  | tee /dev/stderr | grep -qE 'available|stopped' \
	  && echo "  RDS: OK (available or stopped — run staging-up to start)" \
	  || echo "  RDS: FAIL or not found"
	@echo ""

	@echo "--- NAT instance ---"
	@NAT_ID=$$(cd $(STAGING_DIR) && terraform output -raw nat_instance_id 2>/dev/null); \
	[ -n "$$NAT_ID" ] && \
	  aws ec2 describe-instances --instance-ids $$NAT_ID \
	    --query 'Reservations[0].Instances[0].State.Name' --output text 2>/dev/null \
	  | grep -qE 'running|stopped' \
	  && echo "  NAT instance: OK ($$NAT_ID)" \
	  || echo "  NAT instance: FAIL"
	@echo ""

	@echo "--- ECS cluster ---"
	@aws ecs describe-clusters --clusters dental-staging \
	  --query 'clusters[0].status' --output text 2>/dev/null \
	  | grep -q ACTIVE && echo "  ECS cluster: OK" || echo "  ECS cluster: FAIL"
	@echo ""

	@echo "--- ECS services (requires staging-up) ---"
	@aws ecs describe-services --cluster dental-staging \
	  --services dental-staging-api dental-staging-web \
	  --query 'services[*].[serviceName,status,desiredCount,runningCount]' \
	  --output table 2>/dev/null || echo "  ECS services: not found (run staging-up)"
	@echo ""

	@echo "--- ALB health ---"
	@ALB_DNS=$$(cd $(STAGING_DIR) && terraform output -raw alb_dns_name 2>/dev/null); \
	[ -n "$$ALB_DNS" ] && \
	  curl -sf --max-time 5 "http://$$ALB_DNS/health" > /dev/null \
	  && echo "  ALB /health: OK (http://$$ALB_DNS)" \
	  || echo "  ALB /health: unreachable — ECS may not be up yet (http://$$ALB_DNS)"
	@echo ""

	@echo "--- S3 buckets ---"
	@for bucket in dental-phi-documents-staging dental-era-files-staging dental-exports-staging; do \
	  aws s3api head-bucket --bucket $$bucket 2>/dev/null \
	    && echo "  $$bucket: OK" \
	    || echo "  $$bucket: FAIL"; \
	done
	@echo ""

	@echo "--- SQS queues ---"
	@for queue in dental-reminders-queue-staging dental-eligibility-queue-staging dental-era-queue-staging dental-audit-logs-queue-staging; do \
	  aws sqs get-queue-url --queue-name $$queue --query 'QueueUrl' --output text 2>/dev/null \
	    && echo "  $$queue: OK" \
	    || echo "  $$queue: FAIL"; \
	done
	@echo ""

	@echo "--- SSM parameters (checks values are no longer placeholders) ---"
	@for param in db/url redis/url cognito/user_pool_id app/secret_key; do \
	  val=$$(aws ssm get-parameter --name /dental/staging/$$param \
	    --with-decryption --query 'Parameter.Value' --output text 2>/dev/null); \
	  echo "$$val" | grep -q "^placeholder" \
	    && echo "  /dental/staging/$$param: NEEDS POPULATING" \
	    || echo "  /dental/staging/$$param: OK"; \
	done
	@echo ""

	@echo "--- Cognito user pool ---"
	@POOL_ID=$$(cd $(STAGING_DIR) && terraform output -raw cognito_user_pool_id 2>/dev/null); \
	[ -n "$$POOL_ID" ] && \
	  aws cognito-idp describe-user-pool --user-pool-id $$POOL_ID \
	    --query 'UserPool.Id' --output text 2>/dev/null \
	  | grep -q "$$POOL_ID" \
	  && echo "  Cognito: OK ($$POOL_ID)" \
	  || echo "  Cognito: FAIL"
	@echo ""

	@echo "--- ECR repos ---"
	@for repo in dental/api dental/web; do \
	  aws ecr describe-repositories --repository-names $$repo \
	    --query 'repositories[0].repositoryName' --output text 2>/dev/null \
	    && echo "  $$repo: OK" \
	    || echo "  $$repo: FAIL"; \
	done
	@echo ""

	@echo "======================================================"
	@echo " Done. Fix any FAILs or NEEDS POPULATING above."
	@echo " SSM population steps are in DEV.md under 'First apply'."
	@echo "======================================================"

# staging-up: provision VPC endpoints + ElastiCache, start RDS + NAT instance, bring ECS to desired=1
# Run from the repo root.
staging-up:
	@echo "==> [1/6] Provisioning VPC endpoints (~2 min)..."
	cd $(STAGING_DIR) && terraform apply -target=module.vpc_endpoints -auto-approve
	@echo "==> [2/6] Provisioning ElastiCache (~5 min)..."
	cd $(STAGING_DIR) && terraform apply -target=module.elasticache -auto-approve
	@echo "==> [3/6] Starting RDS..."
	-aws rds start-db-instance --db-instance-identifier dental-staging
	@echo "==> [4/6] Starting NAT instance..."
	-aws ec2 start-instances --instance-ids $$(cd $(STAGING_DIR) && terraform output -raw nat_instance_id)
	@echo "==> [5/6] Waiting for RDS to be available (~2 min)..."
	aws rds wait db-instance-available --db-instance-identifier dental-staging
	@echo "==> [6/6] Starting ECS services..."
	aws ecs update-service --cluster dental-staging --service dental-staging-api --desired-count 1
	aws ecs update-service --cluster dental-staging --service dental-staging-web --desired-count 1
	@echo ""
	@echo "==> Staging is up!"
	@cd $(STAGING_DIR) && echo "    ALB: http://$$(terraform output -raw alb_dns_name)"

# staging-down: stop ECS, stop RDS, stop NAT instance, destroy ElastiCache + VPC endpoints
# Run from the repo root.
staging-down:
	@echo "==> [1/5] Stopping ECS services..."
	-aws ecs update-service --cluster dental-staging --service dental-staging-api --desired-count 0
	-aws ecs update-service --cluster dental-staging --service dental-staging-web --desired-count 0
	@echo "==> [2/5] Stopping RDS..."
	-aws rds stop-db-instance --db-instance-identifier dental-staging
	@echo "==> [3/5] Stopping NAT instance..."
	-aws ec2 stop-instances --instance-ids $$(cd $(STAGING_DIR) && terraform output -raw nat_instance_id)
	@echo "==> [4/5] Destroying ElastiCache (~3 min)..."
	cd $(STAGING_DIR) && terraform destroy -target=module.elasticache -auto-approve
	@echo "==> [5/5] Destroying VPC endpoints (~2 min)..."
	cd $(STAGING_DIR) && terraform destroy -target=module.vpc_endpoints -auto-approve
	@echo ""
	@echo "==> Staging is down. Cost while idle: ~\$$2/mo (RDS storage only)."
