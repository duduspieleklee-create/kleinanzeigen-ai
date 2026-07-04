#!/usr/bin/env bash
# AWS infrastructure setup for kleinanzeigen-ai
# Usage: export PG_PASS="YourStr0ng#Pass" && chmod +x infra/aws-setup.sh && ./infra/aws-setup.sh
set -euo pipefail

# ── Config — edit if you need different names/region ──────────────────────────
REGION="eu-central-1"               # Frankfurt — closest AWS region to the old westeurope setup
CLUSTER="kleinanzeigen-cluster"
PG_INSTANCE="kleinanzeigen-db"
PG_USER="kaadmin"
PG_PASS="${PG_PASS:?Export PG_PASS before running: export PG_PASS='YourStr0ng#Pass'}"
PG_DB="kleinanzeigen_ai"
REDIS_ID="kleinanzeigen-redis"
EXEC_ROLE_NAME="kleinanzeigen-ecs-execution-role"
GHA_ROLE_NAME="kleinanzeigen-gha-deploy-role"
ALB_NAME="kleinanzeigen-alb"
GITHUB_REPO="duduspieleklee-create/kleinanzeigen-ai"
SECRET_PREFIX="kleinanzeigen"
# ──────────────────────────────────────────────────────────────────────────────

export AWS_DEFAULT_REGION="$REGION"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "==> Default VPC and subnets..."
VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query "Vpcs[0].VpcId" --output text)
SUBNET_IDS=$(aws ec2 describe-subnets --filters Name=vpc-id,Values="$VPC_ID" --query "Subnets[].SubnetId" --output text)
SUBNET_CSV=$(echo "$SUBNET_IDS" | tr '\t' ',')
read -r SUBNET_A SUBNET_B _ <<< "$SUBNET_IDS"

echo "==> Security groups..."
get_or_create_sg() {
  local NAME="$1" DESC="$2" ID
  ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$NAME" "Name=vpc-id,Values=$VPC_ID" \
        --query "SecurityGroups[0].GroupId" --output text 2>/dev/null || true)
  if [[ -z "$ID" || "$ID" == "None" ]]; then
    ID=$(aws ec2 create-security-group --group-name "$NAME" --description "$DESC" --vpc-id "$VPC_ID" --query GroupId --output text)
  fi
  echo "$ID"
}
SG_ALB=$(get_or_create_sg kleinanzeigen-alb-sg "kleinanzeigen ALB")
SG_ECS=$(get_or_create_sg kleinanzeigen-ecs-sg "kleinanzeigen ECS tasks")
SG_DB=$(get_or_create_sg kleinanzeigen-db-sg "kleinanzeigen RDS")
SG_REDIS=$(get_or_create_sg kleinanzeigen-redis-sg "kleinanzeigen ElastiCache")

aws ec2 authorize-security-group-ingress --group-id "$SG_ALB" --protocol tcp --port 80 --cidr 0.0.0.0/0 >/dev/null 2>&1 || true
aws ec2 authorize-security-group-ingress --group-id "$SG_ECS" --protocol tcp --port 8000 --source-group "$SG_ALB" >/dev/null 2>&1 || true
aws ec2 authorize-security-group-ingress --group-id "$SG_DB" --protocol tcp --port 5432 --source-group "$SG_ECS" >/dev/null 2>&1 || true
aws ec2 authorize-security-group-ingress --group-id "$SG_REDIS" --protocol tcp --port 6379 --source-group "$SG_ECS" >/dev/null 2>&1 || true

echo "==> ECR repositories..."
for REPO in kleinanzeigen-ai-api kleinanzeigen-ai-worker kleinanzeigen-ai-beat; do
  aws ecr describe-repositories --repository-names "$REPO" >/dev/null 2>&1 \
    || aws ecr create-repository --repository-name "$REPO" >/dev/null
done

echo "==> RDS for PostgreSQL (takes ~5-10 min)..."
aws rds create-db-subnet-group \
  --db-subnet-group-name kleinanzeigen-db-subnets \
  --db-subnet-group-description "kleinanzeigen RDS subnets" \
  --subnet-ids $SUBNET_IDS >/dev/null 2>&1 || true

PG_ENGINE_VERSION=$(aws rds describe-db-engine-versions --engine postgres \
  --query "DBEngineVersions[?starts_with(EngineVersion, '15.')].EngineVersion" --output text \
  | tr '\t' '\n' | sort -V | tail -1)
echo "    using PostgreSQL $PG_ENGINE_VERSION"

aws rds describe-db-instances --db-instance-identifier "$PG_INSTANCE" >/dev/null 2>&1 || \
  aws rds create-db-instance \
    --db-instance-identifier "$PG_INSTANCE" \
    --db-name "$PG_DB" \
    --engine postgres --engine-version "$PG_ENGINE_VERSION" \
    --db-instance-class db.t4g.micro \
    --allocated-storage 20 \
    --master-username "$PG_USER" --master-user-password "$PG_PASS" \
    --db-subnet-group-name kleinanzeigen-db-subnets \
    --vpc-security-group-ids "$SG_DB" \
    --no-publicly-accessible \
    --no-multi-az \
    --backup-retention-period 7 \
    >/dev/null
echo "    waiting for RDS to become available..."
aws rds wait db-instance-available --db-instance-identifier "$PG_INSTANCE"

echo "==> ElastiCache for Redis (takes ~5-10 min)..."
aws elasticache create-cache-subnet-group \
  --cache-subnet-group-name kleinanzeigen-redis-subnets \
  --cache-subnet-group-description "kleinanzeigen Redis subnets" \
  --subnet-ids $SUBNET_IDS >/dev/null 2>&1 || true

REDIS_ENGINE_VERSION=$(aws elasticache describe-cache-engine-versions --engine redis \
  --query "CacheEngineVersions[].EngineVersion" --output text \
  | tr '\t' '\n' | sort -V | tail -1)
echo "    using Redis $REDIS_ENGINE_VERSION"

# In-transit encryption (TLS) for Redis is only available on a replication
# group, not a plain cache cluster — even a single-node one needs this API.
aws elasticache describe-replication-groups --replication-group-id "$REDIS_ID" >/dev/null 2>&1 || \
  aws elasticache create-replication-group \
    --replication-group-id "$REDIS_ID" \
    --replication-group-description "kleinanzeigen Celery broker" \
    --num-cache-clusters 1 \
    --engine redis --engine-version "$REDIS_ENGINE_VERSION" \
    --cache-node-type cache.t4g.micro \
    --cache-subnet-group-name kleinanzeigen-redis-subnets \
    --security-group-ids "$SG_REDIS" \
    --transit-encryption-enabled \
    >/dev/null
echo "    waiting for Redis to become available..."
aws elasticache wait replication-group-available --replication-group-id "$REDIS_ID"

echo "==> Secrets Manager placeholders..."
for NAME in DATABASE_URL REDIS_URL SECRET_KEY APP_USERNAME APP_PASSWORD ALLOWED_EMAILS \
            ADMIN_EMAILS SYSTEM_USER_ID VAPID_PRIVATE_KEY VAPID_PUBLIC_KEY VAPID_EMAIL \
            GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET STRIPE_SECRET_KEY STRIPE_WEBHOOK_SECRET \
            STRIPE_PRICE_CORE STRIPE_PRICE_PRO PUBLIC_BASE_URL RESEND_API_KEY EMAIL_FROM; do
  aws secretsmanager describe-secret --secret-id "$SECRET_PREFIX/$NAME" >/dev/null 2>&1 \
    || aws secretsmanager create-secret --name "$SECRET_PREFIX/$NAME" --secret-string "CHANGE_ME" >/dev/null
done

echo "==> ECS task execution role..."
cat > /tmp/ecs-trust.json <<'EOF'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}
EOF
aws iam get-role --role-name "$EXEC_ROLE_NAME" >/dev/null 2>&1 || {
  aws iam create-role --role-name "$EXEC_ROLE_NAME" --assume-role-policy-document file:///tmp/ecs-trust.json >/dev/null
  aws iam attach-role-policy --role-name "$EXEC_ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy >/dev/null
  cat > /tmp/secrets-policy.json <<EOF
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"secretsmanager:GetSecretValue","Resource":"arn:aws:secretsmanager:$REGION:$ACCOUNT_ID:secret:$SECRET_PREFIX/*"}]}
EOF
  aws iam put-role-policy --role-name "$EXEC_ROLE_NAME" --policy-name kleinanzeigen-secrets-read \
    --policy-document file:///tmp/secrets-policy.json >/dev/null
}

echo "==> CloudWatch log groups..."
for APP in api worker beat; do
  aws logs create-log-group --log-group-name "/ecs/kleinanzeigen-$APP" 2>/dev/null || true
done

echo "==> ECS cluster..."
aws ecs create-cluster --cluster-name "$CLUSTER" >/dev/null

echo "==> Application Load Balancer (api only)..."
ALB_ARN=$(aws elbv2 describe-load-balancers --names "$ALB_NAME" --query "LoadBalancers[0].LoadBalancerArn" --output text 2>/dev/null || true)
if [[ -z "$ALB_ARN" || "$ALB_ARN" == "None" ]]; then
  ALB_ARN=$(aws elbv2 create-load-balancer --name "$ALB_NAME" --subnets $SUBNET_IDS \
    --security-groups "$SG_ALB" --scheme internet-facing --type application \
    --query "LoadBalancers[0].LoadBalancerArn" --output text)
fi

TG_ARN=$(aws elbv2 describe-target-groups --names kleinanzeigen-api-tg --query "TargetGroups[0].TargetGroupArn" --output text 2>/dev/null || true)
if [[ -z "$TG_ARN" || "$TG_ARN" == "None" ]]; then
  TG_ARN=$(aws elbv2 create-target-group --name kleinanzeigen-api-tg --protocol HTTP --port 8000 \
    --vpc-id "$VPC_ID" --target-type ip --health-check-path /healthz \
    --query "TargetGroups[0].TargetGroupArn" --output text)
fi

LISTENER_EXISTS=$(aws elbv2 describe-listeners --load-balancer-arn "$ALB_ARN" --query "length(Listeners)" --output text 2>/dev/null || true)
if [[ -z "$LISTENER_EXISTS" || "$LISTENER_EXISTS" == "0" ]]; then
  aws elbv2 create-listener --load-balancer-arn "$ALB_ARN" --protocol HTTP --port 80 \
    --default-actions Type=forward,TargetGroupArn="$TG_ARN" >/dev/null
fi

echo "==> Registering task definitions and creating services..."
for APP in api worker beat; do
  sed -e "s/__AWS_ACCOUNT_ID__/$ACCOUNT_ID/g" -e "s/__AWS_REGION__/$REGION/g" \
    "infra/ecs/task-def-$APP.json" > "/tmp/task-def-$APP.json"
  aws ecs register-task-definition --cli-input-json "file:///tmp/task-def-$APP.json" >/dev/null
done

service_exists() {
  local NAME="$1" STATUS
  STATUS=$(aws ecs describe-services --cluster "$CLUSTER" --services "$NAME" \
             --query "services[0].status" --output text 2>/dev/null || true)
  [[ "$STATUS" == "ACTIVE" ]]
}

service_exists kleinanzeigen-api || \
  aws ecs create-service --cluster "$CLUSTER" --service-name kleinanzeigen-api \
    --task-definition kleinanzeigen-api --desired-count 1 --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_A,$SUBNET_B],securityGroups=[$SG_ECS],assignPublicIp=ENABLED}" \
    --load-balancers "targetGroupArn=$TG_ARN,containerName=api,containerPort=8000" >/dev/null

service_exists kleinanzeigen-worker || \
  aws ecs create-service --cluster "$CLUSTER" --service-name kleinanzeigen-worker \
    --task-definition kleinanzeigen-worker --desired-count 1 --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_A,$SUBNET_B],securityGroups=[$SG_ECS],assignPublicIp=ENABLED}" >/dev/null

service_exists kleinanzeigen-beat || \
  aws ecs create-service --cluster "$CLUSTER" --service-name kleinanzeigen-beat \
    --task-definition kleinanzeigen-beat --desired-count 1 --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_A,$SUBNET_B],securityGroups=[$SG_ECS],assignPublicIp=ENABLED}" >/dev/null

echo "==> GitHub Actions OIDC deploy role..."
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 \
  >/dev/null 2>&1 || true

cat > /tmp/gha-trust.json <<EOF
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Federated":"arn:aws:iam::$ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"},"Action":"sts:AssumeRoleWithWebIdentity","Condition":{"StringEquals":{"token.actions.githubusercontent.com:aud":"sts.amazonaws.com"},"StringLike":{"token.actions.githubusercontent.com:sub":"repo:$GITHUB_REPO:*"}}}]}
EOF
aws iam get-role --role-name "$GHA_ROLE_NAME" >/dev/null 2>&1 || \
  aws iam create-role --role-name "$GHA_ROLE_NAME" --assume-role-policy-document file:///tmp/gha-trust.json >/dev/null

cat > /tmp/gha-policy.json <<EOF
{"Version":"2012-10-17","Statement":[
  {"Effect":"Allow","Action":["ecr:GetAuthorizationToken"],"Resource":"*"},
  {"Effect":"Allow","Action":["ecr:BatchCheckLayerAvailability","ecr:GetDownloadUrlForLayer","ecr:BatchGetImage","ecr:PutImage","ecr:InitiateLayerUpload","ecr:UploadLayerPart","ecr:CompleteLayerUpload"],"Resource":"arn:aws:ecr:$REGION:$ACCOUNT_ID:repository/kleinanzeigen-ai-*"},
  {"Effect":"Allow","Action":["ecs:RegisterTaskDefinition","ecs:DescribeTaskDefinition"],"Resource":"*"},
  {"Effect":"Allow","Action":["ecs:UpdateService","ecs:DescribeServices"],"Resource":"arn:aws:ecs:$REGION:$ACCOUNT_ID:service/$CLUSTER/*"},
  {"Effect":"Allow","Action":"iam:PassRole","Resource":"arn:aws:iam::$ACCOUNT_ID:role/$EXEC_ROLE_NAME"},
  {"Effect":"Allow","Action":["secretsmanager:PutSecretValue","secretsmanager:DescribeSecret"],"Resource":"arn:aws:secretsmanager:$REGION:$ACCOUNT_ID:secret:$SECRET_PREFIX/*"}
]}
EOF
aws iam put-role-policy --role-name "$GHA_ROLE_NAME" --policy-name kleinanzeigen-gha-deploy \
  --policy-document file:///tmp/gha-policy.json >/dev/null

# ── Collect output values ──────────────────────────────────────────────────────
PG_HOST=$(aws rds describe-db-instances --db-instance-identifier "$PG_INSTANCE" --query "DBInstances[0].Endpoint.Address" --output text)
REDIS_HOST=$(aws elasticache describe-replication-groups --replication-group-id "$REDIS_ID" --query "ReplicationGroups[0].NodeGroups[0].PrimaryEndpoint.Address" --output text)
ALB_DNS=$(aws elbv2 describe-load-balancers --load-balancer-arns "$ALB_ARN" --query "LoadBalancers[0].DNSName" --output text)
GHA_ROLE_ARN="arn:aws:iam::$ACCOUNT_ID:role/$GHA_ROLE_NAME"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  All resources created. Add these to GitHub Secrets/Variables:"
echo "  Settings → Secrets and variables → Actions"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "AWS_DEPLOY_ROLE_ARN  (secret) = $GHA_ROLE_ARN"
echo "AWS_REGION           (variable) = $REGION"
echo "AWS_ACCOUNT_ID       (variable) = $ACCOUNT_ID"
echo ""
echo "Update these Secrets Manager values (currently CHANGE_ME placeholders):"
echo "  aws secretsmanager put-secret-value --secret-id $SECRET_PREFIX/DATABASE_URL \\"
echo "    --secret-string \"postgresql://$PG_USER:$PG_PASS@$PG_HOST:5432/$PG_DB?sslmode=require\""
echo "  aws secretsmanager put-secret-value --secret-id $SECRET_PREFIX/REDIS_URL \\"
echo "    --secret-string \"rediss://$REDIS_HOST:6379/0\""
echo "  ... and SECRET_KEY, GOOGLE_CLIENT_ID/SECRET, STRIPE_*, VAPID_*, RESEND_API_KEY, etc."
echo ""
echo "Each secret update is picked up automatically on the next deploy (the CI"
echo "deploy job syncs GitHub Secrets into Secrets Manager, then forces a new"
echo "ECS deployment so tasks restart with fresh values)."
echo ""
echo "App URL (until you attach a domain/ACM cert): http://$ALB_DNS"
echo "════════════════════════════════════════════════════════════"
