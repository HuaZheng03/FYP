#!/bin/bash
# ==============================================================================
# Configure OVS Interface Speed on All Switches
# Sets interface link_speed to 500Mbps (500000000 bits/sec)
# ==============================================================================

# Run this script on each server/host running Open vSwitch

TARGET_SPEED=500000000  # 500 Mbps in bits per second

echo "=============================================="
echo "Open vSwitch Interface Speed Configuration"
echo "Target Speed: 500 Mbps"
echo "=============================================="

# Get all OVS bridges
BRIDGES=$(ovs-vsctl list-br 2>/dev/null)

if [ -z "$BRIDGES" ]; then
    echo "No OVS bridges found on this host."
    exit 0
fi

echo ""
echo "Found bridges: $BRIDGES"
echo ""

for BRIDGE in $BRIDGES; do
    echo "Processing bridge: $BRIDGE"
    echo "-------------------------------------------"
    
    # Get all ports on the bridge
    PORTS=$(ovs-vsctl list-ports "$BRIDGE" 2>/dev/null)
    
    for PORT in $PORTS; do
        # Skip internal ports (like br0, etc)
        TYPE=$(ovs-vsctl get interface "$PORT" type 2>/dev/null | tr -d '"')
        
        if [ "$TYPE" = "internal" ]; then
            echo "  Skipping internal port: $PORT"
            continue
        fi
        
        echo "  Configuring port: $PORT"
        
        # Set the link speed
        if ovs-vsctl set interface "$PORT" link_speed=$TARGET_SPEED 2>/dev/null; then
            echo "    ✓ Set link_speed to $TARGET_SPEED"
        else
            echo "    ⚠ Could not set link_speed (may not be supported)"
        fi
        
        # Verify the setting
        CURRENT_SPEED=$(ovs-vsctl get interface "$PORT" link_speed 2>/dev/null)
        echo "    Current link_speed: $CURRENT_SPEED"
    done
    echo ""
done

echo "=============================================="
echo "Configuration Complete"
echo "=============================================="
echo ""
echo "Note: Interface link_speed affects how OVS reports"
echo "port speed but may not enforce actual bandwidth limits."
echo "Use Linux tc (traffic control) for actual bandwidth limiting."
