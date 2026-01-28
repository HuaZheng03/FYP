#!/bin/bash
# ==============================================================================
# Verify ONOS Link Bandwidth Configuration
# ==============================================================================

ONOS_HOST="192.168.126.1"
ONOS_PORT="8181"
ONOS_USER=""
ONOS_PASS=""

echo "=============================================="
echo "ONOS Link Bandwidth Verification"
echo "=============================================="

# Test connection
echo ""
echo "Checking ONOS connection..."
if ! curl -s -f -u "${ONOS_USER}:${ONOS_PASS}" \
    "http://${ONOS_HOST}:${ONOS_PORT}/onos/v1/devices" > /dev/null 2>&1; then
    echo "ERROR: Cannot connect to ONOS"
    exit 1
fi
echo "✓ Connected to ONOS"

# Show devices
echo ""
echo "=============================================="
echo "Devices"
echo "=============================================="
curl -s -u "${ONOS_USER}:${ONOS_PASS}" \
    "http://${ONOS_HOST}:${ONOS_PORT}/onos/v1/devices" | \
    python3 -c "
import sys, json
data = json.load(sys.stdin)
for device in data.get('devices', []):
    print(f\"  {device.get('id')}: {device.get('type', 'SWITCH')} - {device.get('available', False)}\")
"

# Show links
echo ""
echo "=============================================="
echo "Links"
echo "=============================================="
curl -s -u "${ONOS_USER}:${ONOS_PASS}" \
    "http://${ONOS_HOST}:${ONOS_PORT}/onos/v1/links" | \
    python3 -c "
import sys, json
data = json.load(sys.stdin)
for link in data.get('links', []):
    src = link.get('src', {})
    dst = link.get('dst', {})
    state = link.get('state', 'UNKNOWN')
    print(f\"  {src.get('device')}:{src.get('port')} -> {dst.get('device')}:{dst.get('port')} [{state}]\")
"

# Show port configuration
echo ""
echo "=============================================="
echo "Port Bandwidth Configuration"
echo "=============================================="
curl -s -u "${ONOS_USER}:${ONOS_PASS}" \
    "http://${ONOS_HOST}:${ONOS_PORT}/onos/v1/network/configuration/ports" | \
    python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if not data:
        print('  No port configuration found')
    else:
        for port, config in sorted(data.items()):
            bw = config.get('bandwidth', 'Not configured')
            ps = config.get('portSpeed', 'Not configured')
            if isinstance(bw, int):
                print(f'  {port}:')
                print(f'    bandwidth: {bw:,} bps ({bw/1000000:.0f} Mbps)')
                print(f'    portSpeed: {ps} Mbps')
except Exception as e:
    print(f'  Error: {e}')
"

# Show link configuration
echo ""
echo "=============================================="
echo "Link Bandwidth Configuration"
echo "=============================================="
curl -s -u "${ONOS_USER}:${ONOS_PASS}" \
    "http://${ONOS_HOST}:${ONOS_PORT}/onos/v1/network/configuration/links" | \
    python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if not data:
        print('  No link configuration found')
    else:
        for link, config in sorted(data.items()):
            basic = config.get('basic', {})
            bw = basic.get('bandwidth', 'Not configured')
            if isinstance(bw, int):
                print(f'  {link}:')
                print(f'    bandwidth: {bw:,} bps ({bw/1000000:.0f} Mbps)')
except Exception as e:
    print(f'  Error: {e}')
"

# Full network configuration dump
echo ""
echo "=============================================="
echo "Full Network Configuration (JSON)"
echo "=============================================="
curl -s -u "${ONOS_USER}:${ONOS_PASS}" \
    "http://${ONOS_HOST}:${ONOS_PORT}/onos/v1/network/configuration" | \
    python3 -m json.tool 2>/dev/null || echo "  No configuration or parse error"

echo ""
echo "=============================================="
echo "Verification Complete"
echo "=============================================="
