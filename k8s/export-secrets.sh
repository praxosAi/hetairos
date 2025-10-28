#!/bin/bash

# Script to export Kubernetes secrets to editable YAML format
# This decodes base64 secrets so you can easily modify them

set -e

PROD_NAMESPACE="${1:-hetairoi}"
SECRET_NAME="${2:-hetairoi-secrets}"
OUTPUT_FILE="hetairoi-secrets-decoded.yaml"

echo "=== Exporting Kubernetes Secrets ==="
echo "Namespace: $PROD_NAMESPACE"
echo "Secret: $SECRET_NAME"
echo ""

# Check if secret exists
if ! kubectl get secret $SECRET_NAME -n $PROD_NAMESPACE &> /dev/null; then
    echo "❌ Secret '$SECRET_NAME' not found in namespace '$PROD_NAMESPACE'"
    echo ""
    echo "Available secrets:"
    kubectl get secrets -n $PROD_NAMESPACE
    exit 1
fi

echo "📥 Exporting secret to: $OUTPUT_FILE"

# Create a Python script to decode the secrets
cat > /tmp/decode_secrets.py << 'PYTHON_SCRIPT'
#!/usr/bin/env python3
import sys
import yaml
import base64

# Read the YAML from stdin
data = yaml.safe_load(sys.stdin)

# Get the secret data
secret_data = data.get('data', {})

# Decode all base64 values
decoded = {}
for key, value in secret_data.items():
    try:
        decoded[key] = base64.b64decode(value).decode('utf-8')
    except Exception as e:
        decoded[key] = f"<ERROR DECODING: {e}>"

# Print in readable format
print("# Decoded Kubernetes Secret")
print("# Edit this file, then use create-test-secrets.sh to apply")
print("# " + "="*70)
print("")
print("# Original Secret Info:")
print(f"# Name: {data['metadata']['name']}")
print(f"# Namespace: {data['metadata'].get('namespace', 'N/A')}")
print("")
print("# " + "="*70)
print("# DECODED VALUES (edit as needed for test environment)")
print("# " + "="*70)
print("")

# Print each key-value pair
for key in sorted(decoded.keys()):
    value = decoded[key]
    # Handle multi-line values
    if '\n' in value:
        print(f"{key}: |")
        for line in value.split('\n'):
            print(f"  {line}")
    else:
        print(f"{key}: {value}")
    print("")

PYTHON_SCRIPT

# Export secret and decode it
kubectl get secret $SECRET_NAME -n $PROD_NAMESPACE -o yaml | \
    python3 /tmp/decode_secrets.py > $OUTPUT_FILE

# Cleanup temp file
rm /tmp/decode_secrets.py

echo "✅ Secrets exported and decoded"
echo ""
echo "📝 Next steps:"
echo "   1. Edit $OUTPUT_FILE with your test environment values"
echo "   2. Update these values for test environment:"
echo "      - Redis queue names (if different)"
echo "      - WhatsApp phone number"
echo "      - Webhook URLs (if different)"
echo "      - Any other environment-specific values"
echo ""
echo "   3. Run: ./create-test-secrets.sh $OUTPUT_FILE"
echo ""
echo "⚠️  IMPORTANT: $OUTPUT_FILE contains plaintext secrets!"
echo "   - Do NOT commit to git"
echo "   - Delete after creating test secrets"
