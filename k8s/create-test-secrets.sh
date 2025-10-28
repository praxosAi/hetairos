#!/bin/bash

# Script to create test secrets from decoded YAML file
# Takes the edited secrets file and creates a Kubernetes secret in test namespace

set -e

SECRETS_FILE="${1:-hetairoi-secrets-decoded.yaml}"
TEST_NAMESPACE="hetairoi-test"
SECRET_NAME="hetairoi-secrets"

echo "=== Creating Test Secrets ==="
echo ""

# Check if secrets file exists
if [ ! -f "$SECRETS_FILE" ]; then
    echo "❌ Secrets file not found: $SECRETS_FILE"
    echo ""
    echo "Usage: $0 <secrets-file>"
    echo ""
    echo "First run: ./export-secrets.sh to export production secrets"
    exit 1
fi

# Check if test namespace exists
if ! kubectl get namespace $TEST_NAMESPACE &> /dev/null; then
    echo "📦 Creating test namespace: $TEST_NAMESPACE"
    kubectl apply -f test-namespace.yaml
fi

echo "🔐 Creating secret in namespace: $TEST_NAMESPACE"
echo "📄 Reading from: $SECRETS_FILE"
echo ""

# Create a Python script to encode and create the secret
cat > /tmp/create_secret.py << 'PYTHON_SCRIPT'
#!/usr/bin/env python3
import sys
import yaml
import base64
import re

if len(sys.argv) < 2:
    print("Usage: create_secret.py <secrets-file>")
    sys.exit(1)

secrets_file = sys.argv[1]

# Read the decoded secrets file
with open(secrets_file, 'r') as f:
    content = f.read()

# Parse the key-value pairs (ignoring comments)
secrets = {}
current_key = None
current_value_lines = []
in_multiline = False

for line in content.split('\n'):
    # Skip comments and empty lines
    if line.strip().startswith('#') or not line.strip():
        continue

    # Check for key: value or key: |
    if ':' in line and not line.startswith(' '):
        # Save previous multiline value if any
        if current_key and in_multiline:
            secrets[current_key] = '\n'.join(current_value_lines)
            current_value_lines = []
            in_multiline = False

        # Parse new key
        key, sep, value = line.partition(':')
        key = key.strip()
        value = value.strip()

        if value == '|':
            # Start multiline value
            current_key = key
            in_multiline = True
        elif value:
            # Single line value
            secrets[key] = value
            current_key = None
        else:
            current_key = key
    elif line.startswith('  ') and in_multiline:
        # Multiline value continuation
        current_value_lines.append(line[2:])  # Remove leading spaces

# Save last multiline value if any
if current_key and in_multiline:
    secrets[current_key] = '\n'.join(current_value_lines)

# Create Kubernetes secret YAML
secret_yaml = {
    'apiVersion': 'v1',
    'kind': 'Secret',
    'metadata': {
        'name': 'hetairoi-secrets',
        'namespace': 'hetairoi-test'
    },
    'type': 'Opaque',
    'data': {}
}

# Base64 encode all values
for key, value in secrets.items():
    encoded = base64.b64encode(value.encode('utf-8')).decode('utf-8')
    secret_yaml['data'][key] = encoded

# Output the YAML
print(yaml.dump(secret_yaml, default_flow_style=False))

PYTHON_SCRIPT

# Create the secret
python3 /tmp/create_secret.py "$SECRETS_FILE" | kubectl apply -f -

# Cleanup temp file
rm /tmp/create_secret.py

echo ""
echo "✅ Test secrets created successfully"
echo ""
echo "🔍 Verify secrets:"
echo "   kubectl get secret $SECRET_NAME -n $TEST_NAMESPACE"
echo ""
echo "🧪 View secret keys (without values):"
echo "   kubectl get secret $SECRET_NAME -n $TEST_NAMESPACE -o jsonpath='{.data}' | jq 'keys'"
echo ""
echo "🚀 Deploy test environment:"
echo "   kubectl apply -f test-deployment.yaml"
echo ""
echo "⚠️  Remember to delete: $SECRETS_FILE (contains plaintext secrets)"
