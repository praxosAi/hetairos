#!/bin/bash

# Script to deploy FileManager changes to test namespace
# Requires test secrets to be created first (see TEST_SETUP.md)

set -e  # Exit on error

TEST_NAMESPACE="hetairoi-test"
SECRET_NAME="hetairoi-secrets"

echo "=== Deploying FileManager Test Environment ==="
echo ""

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found. Please install kubectl first."
    exit 1
fi

# Step 1: Create test namespace
echo "📦 Creating test namespace: $TEST_NAMESPACE"
kubectl apply -f test-namespace.yaml

# Step 2: Check if test secrets exist
if ! kubectl get secret $SECRET_NAME -n $TEST_NAMESPACE &> /dev/null; then
    echo "❌ Test secrets not found in namespace '$TEST_NAMESPACE'"
    echo ""
    echo "⚠️  You need to create test secrets first!"
    echo ""
    echo "Run these commands:"
    echo "   1. ./export-secrets.sh                    # Export production secrets"
    echo "   2. Edit hetairoi-secrets-decoded.yaml     # Modify for test environment"
    echo "   3. ./create-test-secrets.sh               # Create test secrets"
    echo ""
    exit 1
fi

echo "✅ Test secrets found"

# Step 3: Deploy test pods
echo "🚀 Deploying test pods to $TEST_NAMESPACE"
kubectl apply -f test-deployment.yaml

# Step 4: Ask about ingress
echo ""
echo "🌐 Ingress Configuration"
echo ""
echo "Do you want to deploy test ingress? (allows external webhook access)"
echo ""
echo "Options:"
echo "  1) Path-based (/test prefix) - Quick, no DNS needed"
echo "  2) Subdomain (test-hooks.praxos.ai) - Clean, requires DNS"
echo "  3) Skip (use kubectl port-forward for testing)"
echo ""
read -p "Choose [1/2/3]: " ingress_choice

case $ingress_choice in
    1)
        echo "📡 Deploying path-based ingress..."
        kubectl apply -f test-ingress-path-based.yaml
        echo "✅ Test webhooks available at: https://hooks.praxos.ai/test/webhooks/*"
        echo "   Update webhook URLs in Telegram/WhatsApp to include /test prefix"
        ;;
    2)
        echo "📡 Deploying subdomain ingress..."
        kubectl apply -f test-ingress-subdomain.yaml
        echo "✅ Test webhooks available at: https://test-hooks.praxos.ai/webhooks/*"
        echo "⚠️  Make sure DNS is configured: test-hooks.praxos.ai → ingress IP"
        echo "⚠️  Make sure TLS certificate exists for test-hooks.praxos.ai"
        ;;
    3)
        echo "⏭️  Skipping ingress deployment"
        echo "   Use: kubectl port-forward -n $TEST_NAMESPACE svc/hetairoi-web-service-test 8080:80"
        ;;
    *)
        echo "⏭️  Invalid choice, skipping ingress"
        ;;
esac

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "📊 Check deployment status:"
echo "   kubectl get pods -n $TEST_NAMESPACE"
echo ""
echo "📝 View logs:"
echo "   kubectl logs -n $TEST_NAMESPACE -l app=hetairoi-web-test --tail=100 -f"
echo "   kubectl logs -n $TEST_NAMESPACE -l app=hetairoi-worker-test --tail=100 -f"
echo ""
echo "🧪 To test file uploads:"
echo "   1. Port-forward to test web service:"
echo "      kubectl port-forward -n $TEST_NAMESPACE svc/hetairoi-web-service-test 8080:80"
echo "   2. Send test file via Telegram/WhatsApp/iMessage"
echo "   3. Check logs for 'Processing file:' from FileManager"
echo ""
echo "🗑️  To cleanup test environment:"
echo "   kubectl delete namespace $TEST_NAMESPACE"
