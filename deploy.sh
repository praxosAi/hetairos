#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

REGISTRY="praxosagentcontainers.azurecr.io"
IMAGE_NAME="hetairoi-worker"
FULL_IMAGE="$REGISTRY/$IMAGE_NAME"

# Parse arguments
ENV=${1:-production}

if [[ "$ENV" != "production" && "$ENV" != "test" ]]; then
    echo -e "${RED}Error: Environment must be 'production' or 'test'${NC}"
    echo "Usage: ./deploy.sh [production|test]"
    exit 1
fi

OVERLAY_PATH="k8s/overlays/$ENV"
NAMESPACE="hetairoi"
if [[ "$ENV" == "test" ]]; then
    NAMESPACE="hetairoi-test"
    IMAGE_NAME="hetairoi-worker-test"
    FULL_IMAGE="$REGISTRY/$IMAGE_NAME"
fi

echo -e "${BLUE}===========================================${NC}"
echo -e "${BLUE}Deploying to: ${GREEN}$ENV${NC}"
echo -e "${BLUE}Namespace: ${GREEN}$NAMESPACE${NC}"
echo -e "${BLUE}===========================================${NC}"
echo ""

# Step 1: Login to ACR
echo -e "${YELLOW}→ Logging in to Azure Container Registry...${NC}"
az acr login --name praxosagentcontainers

# Step 2: Build and push
echo -e "${YELLOW}→ Building and pushing Docker image...${NC}"
docker buildx create --use --name hetairoi-builder 2>/dev/null || docker buildx use hetairoi-builder
docker buildx build --platform linux/amd64 -t $FULL_IMAGE:latest --push .

# Step 3: Get the digest
echo -e "${YELLOW}→ Getting image digest...${NC}"
IMAGE_DIGEST=$(docker buildx imagetools inspect $FULL_IMAGE:latest --format '{{json .Manifest}}' | jq -r '.digest')
echo -e "${GREEN}✓ Image digest: $IMAGE_DIGEST${NC}"

# Step 4: Update kustomization
echo -e "${YELLOW}→ Updating kustomization with new digest...${NC}"
cd $OVERLAY_PATH
kustomize edit set image $REGISTRY/hetairoi-worker@$IMAGE_DIGEST
cd - > /dev/null

# Step 5: Preview changes
echo -e "${YELLOW}→ Previewing changes...${NC}"
kubectl diff -k $OVERLAY_PATH || true

# Step 6: Apply
echo ""
read -p "Deploy to $ENV? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}→ Deploying via Kustomize...${NC}"
    kubectl apply -k $OVERLAY_PATH

    # Step 7: Watch rollout
    echo -e "${YELLOW}→ Watching rollout status...${NC}"
    kubectl rollout status deployment/hetairoi-worker-deployment -n $NAMESPACE --timeout=5m
    kubectl rollout status deployment/hetairoi-web-deployment -n $NAMESPACE --timeout=5m

    echo ""
    echo -e "${GREEN}✓ Deployment complete!${NC}"
    echo ""
    echo -e "${BLUE}Pods in $NAMESPACE:${NC}"
    kubectl get pods -n $NAMESPACE
else
    echo -e "${RED}Deployment cancelled${NC}"
    exit 0
fi
