#!/bin/bash
# ==============================================================================
# ONOS Link Bandwidth Configuration Script
# Sets all spine-leaf link bandwidth to 500Mbps
# ==============================================================================

# Configuration
ONOS_HOST="192.168.126.1"
ONOS_PORT="8181"
ONOS_USER=""
ONOS_PASS=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/network-cfg-500mbps.json"

echo "=============================================="
echo "ONOS Link Bandwidth Configuration"
echo "Target: 500 Mbps for all spine-leaf links"
echo "=============================================="

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: Configuration file not found: $CONFIG_FILE"
    echo "Please run configure_link_bandwidth.py first to generate it."
    exit 1
fi

# Test ONOS connection
echo ""
echo "Testing ONOS connection..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -u "${ONOS_USER}:${ONOS_PASS}" \
    "http://${ONOS_HOST}:${ONOS_PORT}/onos/v1/devices")

if [ "$HTTP_CODE" != "200" ]; then
    echo "ERROR: Cannot connect to ONOS (HTTP $HTTP_CODE)"
    echo "Please check:"
    echo "  - ONOS is running"
    echo "  - Host: ${ONOS_HOST}"
    echo "  - Port: ${ONOS_PORT}"
    echo "  - Credentials: ${ONOS_USER}"
    exit 1
fi
echo "✓ ONOS connection successful"

# Optional: Clear existing configuration
echo ""
read -p "Clear existing port/link configuration first? (y/N): " CLEAR_CONFIG
if [ "$CLEAR_CONFIG" = "y" ] || [ "$CLEAR_CONFIG" = "Y" ]; then
    echo "Clearing existing port configuration..."
    curl -s -X DELETE \
        -u "${ONOS_USER}:${ONOS_PASS}" \
        "http://${ONOS_HOST}:${ONOS_PORT}/onos/v1/network/configuration/ports"
    
    echo "Clearing existing link configuration..."
    curl -s -X DELETE \
        -u "${ONOS_USER}:${ONOS_PASS}" \
        "http://${ONOS_HOST}:${ONOS_PORT}/onos/v1/network/configuration/links"
    
    echo "✓ Existing configuration cleared"
    sleep 2
fi

# Apply new configuration
echo ""
echo "Applying 500Mbps bandwidth configuration..."
HTTP_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -u "${ONOS_USER}:${ONOS_PASS}" \
    "http://${ONOS_HOST}:${ONOS_PORT}/onos/v1/network/configuration" \
    -d @"$CONFIG_FILE")

HTTP_BODY=$(echo "$HTTP_RESPONSE" | head -n -1)
HTTP_CODE=$(echo "$HTTP_RESPONSE" | tail -n 1)

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "204" ]; then
    echo "✓ Configuration applied successfully!"
else
    echo "ERROR: Failed to apply configuration (HTTP $HTTP_CODE)"
    echo "Response: $HTTP_BODY"
    exit 1
fi

# Verify configuration
echo ""
echo "=============================================="
echo "Verifying Configuration"
echo "=============================================="

echo ""
echo "Current port configuration:"
curl -s -u "${ONOS_USER}:${ONOS_PASS}" \
    "http://${ONOS_HOST}:${ONOS_PORT}/onos/v1/network/configuration/ports" | \
    python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for port, config in data.items():
        bw = config.get('bandwidth', 'N/A')
        if isinstance(bw, int):
            print(f'  {port}: {bw/1000000:.0f} Mbps')
except:
    print('  Unable to parse response')
"

echo ""
echo "Current link configuration:"
curl -s -u "${ONOS_USER}:${ONOS_PASS}" \
    "http://${ONOS_HOST}:${ONOS_PORT}/onos/v1/network/configuration/links" | \
    python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for link, config in data.items():
        basic = config.get('basic', {})
        bw = basic.get('bandwidth', 'N/A')
        if isinstance(bw, int):
            print(f'  {link}: {bw/1000000:.0f} Mbps')
except:
    print('  Unable to parse response')
"

echo ""
echo "=============================================="
echo "Configuration Complete!"
echo "=============================================="
echo ""
echo "To verify from ONOS CLI:"
echo "  ssh -p 8101 onos@${ONOS_HOST}"
echo "  onos> cfg get org.onosproject.net.config.basics.BasicLinkConfig"
echo ""
