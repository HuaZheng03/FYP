#!/bin/bash
# ==============================================================================
# Apply ONOS Network Configuration (500Mbps Link Bandwidth)
# Run this script after ONOS container restarts to re-apply the configuration
# ==============================================================================

ONOS_HOST="192.168.126.1"
ONOS_PORT="8181"
ONOS_USER=""
ONOS_PASS=""
CONFIG_FILE="/home/huazheng/DSLB_EESM/onos_link_bandwidth_config/network-cfg-500mbps.json"

echo "Applying ONOS network configuration..."

# Wait for ONOS to be ready
MAX_RETRIES=30
RETRY_INTERVAL=5

for i in $(seq 1 $MAX_RETRIES); do
    if curl -s -f -u "${ONOS_USER}:${ONOS_PASS}" \
        "http://${ONOS_HOST}:${ONOS_PORT}/onos/v1/devices" > /dev/null 2>&1; then
        echo "✓ ONOS is ready"
        break
    fi
    echo "Waiting for ONOS to be ready... (attempt $i/$MAX_RETRIES)"
    sleep $RETRY_INTERVAL
done

# Apply configuration
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -u "${ONOS_USER}:${ONOS_PASS}" \
    "http://${ONOS_HOST}:${ONOS_PORT}/onos/v1/network/configuration" \
    -d @"$CONFIG_FILE")

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "204" ]; then
    echo "✓ Configuration applied successfully (500Mbps link bandwidth)"
else
    echo "✗ Failed to apply configuration (HTTP $HTTP_CODE)"
    exit 1
fi

# Verify
echo ""
echo "Verifying link bandwidth configuration..."
curl -s -u "${ONOS_USER}:${ONOS_PASS}" \
    "http://${ONOS_HOST}:${ONOS_PORT}/onos/v1/network/configuration/links" | \
    python3 -c "
import sys, json
data = json.load(sys.stdin)
count = 0
for link, config in data.items():
    bw = config.get('basic', {}).get('bandwidth', 'N/A')
    if bw == 500:
        count += 1
print(f'✓ {count} links configured with 500 Mbps bandwidth')
"
