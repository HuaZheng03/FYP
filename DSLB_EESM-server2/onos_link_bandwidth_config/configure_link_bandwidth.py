import argparse
import json
import requests
from requests.auth import HTTPBasicAuth
import sys
import os

# ==============================================================================
# ===                           CONFIGURATION                              ===
# ==============================================================================

ONOS_HOST = "192.168.126.1"
ONOS_PORT = 8181
ONOS_USER = ""
ONOS_PASSWORD = ""

# Device ID mappings (from your topology)
DEVICE_IDS = {
    "leaf1": "of:000072ecfb3ccb4c",
    "leaf2": "of:000042b1a1405d41",
    "leaf3": "of:000032095cbf1043",
    "leaf6": "of:0000ca44716bdf4b",
    "spine1": "of:0000d6dee87ca841",
    "spine2": "of:00000ac352fff34c",
}

# Port mappings for spine-leaf connections
# Format: (device_name, port_number): (connected_device_name, connected_port)
LINK_PORTS = {
    # Leaf1 connections
    ("leaf1", 1): ("spine1", 1),
    ("leaf1", 5): ("spine2", 1),
    # Leaf2 connections
    ("leaf2", 3): ("spine1", 3),
    ("leaf2", 1): ("spine2", 2),
    # Leaf3 connections
    ("leaf3", 1): ("spine1", 4),
    ("leaf3", 2): ("spine2", 3),
    # Leaf6 connections
    ("leaf6", 1): ("spine1", 2),
    ("leaf6", 2): ("spine2", 4),
}

# ==============================================================================
# ===                      HELPER FUNCTIONS                                ===
# ==============================================================================

def get_auth():
    """Return HTTP Basic Auth object."""
    return HTTPBasicAuth(ONOS_USER, ONOS_PASSWORD)


def get_base_url():
    """Return ONOS REST API base URL."""
    return f"http://{ONOS_HOST}:{ONOS_PORT}/onos/v1"


def check_onos_connection():
    """Check if ONOS is reachable."""
    try:
        response = requests.get(
            f"{get_base_url()}/devices",
            auth=get_auth(),
            timeout=10
        )
        response.raise_for_status()
        print("✓ Successfully connected to ONOS controller")
        return True
    except requests.exceptions.RequestException as e:
        print(f"✗ Failed to connect to ONOS: {e}")
        return False


def generate_port_config(bandwidth_mbps):
    """
    Generate port configuration for all spine-leaf ports.
    
    Args:
        bandwidth_mbps: Bandwidth in Mbps (e.g., 500 for 500Mbps)
    
    Returns:
        dict: Port configuration for ONOS netcfg
    """
    bandwidth_bps = bandwidth_mbps * 1_000_000  # Convert to bps
    ports_config = {}
    
    # Generate config for each link port
    for (device_name, port), (connected_device, connected_port) in LINK_PORTS.items():
        device_id = DEVICE_IDS[device_name]
        port_key = f"{device_id}/{port}"
        
        ports_config[port_key] = {
            "interfaces": [
                {
                    "name": f"{device_name}-port{port}-to-{connected_device}"
                }
            ],
            "bandwidth": bandwidth_bps,
            "portSpeed": bandwidth_mbps,
            "type": "copper"
        }
        
        # Also configure the other end of the link
        connected_device_id = DEVICE_IDS[connected_device]
        connected_port_key = f"{connected_device_id}/{connected_port}"
        
        ports_config[connected_port_key] = {
            "interfaces": [
                {
                    "name": f"{connected_device}-port{connected_port}-to-{device_name}"
                }
            ],
            "bandwidth": bandwidth_bps,
            "portSpeed": bandwidth_mbps,
            "type": "copper"
        }
    
    return ports_config


def generate_link_config(bandwidth_mbps):
    """
    Generate link configuration for all spine-leaf links.
    
    Args:
        bandwidth_mbps: Bandwidth in Mbps (e.g., 500 for 500Mbps)
    
    Returns:
        dict: Link configuration for ONOS netcfg
    """
    bandwidth_bps = bandwidth_mbps * 1_000_000
    links_config = {}
    
    for (device_name, port), (connected_device, connected_port) in LINK_PORTS.items():
        device_id = DEVICE_IDS[device_name]
        connected_device_id = DEVICE_IDS[connected_device]
        
        # Forward direction
        link_key_fwd = f"{device_id}/{port}-{connected_device_id}/{connected_port}"
        links_config[link_key_fwd] = {
            "basic": {
                "bandwidth": bandwidth_bps,
                "type": "DIRECT",
                "metric": 1,
                "isDurable": True
            }
        }
        
        # Reverse direction
        link_key_rev = f"{connected_device_id}/{connected_port}-{device_id}/{port}"
        links_config[link_key_rev] = {
            "basic": {
                "bandwidth": bandwidth_bps,
                "type": "DIRECT",
                "metric": 1,
                "isDurable": True
            }
        }
    
    return links_config


def generate_full_config(bandwidth_mbps):
    """
    Generate full ONOS network configuration.
    
    Args:
        bandwidth_mbps: Bandwidth in Mbps
    
    Returns:
        dict: Complete network configuration
    """
    return {
        "ports": generate_port_config(bandwidth_mbps),
        "links": generate_link_config(bandwidth_mbps)
    }


def apply_config(config):
    """
    Apply network configuration to ONOS.
    
    Args:
        config: Network configuration dict
    
    Returns:
        bool: True if successful
    """
    url = f"{get_base_url()}/network/configuration"
    
    try:
        response = requests.post(
            url,
            auth=get_auth(),
            headers={"Content-Type": "application/json"},
            data=json.dumps(config),
            timeout=30
        )
        response.raise_for_status()
        print("✓ Configuration applied successfully")
        return True
    except requests.exceptions.RequestException as e:
        print(f"✗ Failed to apply configuration: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"  Response: {e.response.text}")
        return False


def verify_config():
    """
    Verify current network configuration in ONOS.
    
    Returns:
        dict: Current configuration or None
    """
    url = f"{get_base_url()}/network/configuration"
    
    try:
        response = requests.get(url, auth=get_auth(), timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"✗ Failed to get configuration: {e}")
        return None


def get_links_info():
    """
    Get current link information from ONOS.
    
    Returns:
        list: Link information
    """
    url = f"{get_base_url()}/links"
    
    try:
        response = requests.get(url, auth=get_auth(), timeout=10)
        response.raise_for_status()
        return response.json().get("links", [])
    except requests.exceptions.RequestException as e:
        print(f"✗ Failed to get links: {e}")
        return []


def clear_port_config():
    """Clear existing port configuration."""
    url = f"{get_base_url()}/network/configuration/ports"
    
    try:
        response = requests.delete(url, auth=get_auth(), timeout=10)
        print("✓ Cleared existing port configuration")
        return True
    except requests.exceptions.RequestException as e:
        print(f"⚠ Could not clear port config: {e}")
        return False


def clear_link_config():
    """Clear existing link configuration."""
    url = f"{get_base_url()}/network/configuration/links"
    
    try:
        response = requests.delete(url, auth=get_auth(), timeout=10)
        print("✓ Cleared existing link configuration")
        return True
    except requests.exceptions.RequestException as e:
        print(f"⚠ Could not clear link config: {e}")
        return False


def save_config_to_file(config, filename):
    """Save configuration to JSON file."""
    with open(filename, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"✓ Configuration saved to {filename}")


# ==============================================================================
# ===                          MAIN FUNCTIONS                              ===
# ==============================================================================

def configure_bandwidth(bandwidth_mbps, apply=False, clear_existing=False):
    """
    Main function to configure link bandwidth.
    
    Args:
        bandwidth_mbps: Target bandwidth in Mbps
        apply: Whether to apply config to ONOS
        clear_existing: Whether to clear existing config first
    """
    print(f"\n{'='*60}")
    print(f"ONOS Link Bandwidth Configuration")
    print(f"Target Bandwidth: {bandwidth_mbps} Mbps ({bandwidth_mbps * 1_000_000:,} bps)")
    print(f"{'='*60}\n")
    
    # Check ONOS connection
    if not check_onos_connection():
        sys.exit(1)
    
    # Generate configuration
    print("\nGenerating configuration...")
    config = generate_full_config(bandwidth_mbps)
    
    # Save to file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(script_dir, f"network-cfg-{bandwidth_mbps}mbps.json")
    save_config_to_file(config, config_file)
    
    if apply:
        print("\nApplying configuration to ONOS...")
        
        if clear_existing:
            print("Clearing existing configuration...")
            clear_port_config()
            clear_link_config()
        
        if apply_config(config):
            print("\n✓ Configuration applied successfully!")
            print("\nTo verify, run:")
            print(f"  python3 {sys.argv[0]} --verify")
        else:
            print("\n✗ Failed to apply configuration")
            sys.exit(1)
    else:
        print(f"\nConfiguration generated but not applied.")
        print(f"To apply, run:")
        print(f"  python3 {sys.argv[0]} --bandwidth {bandwidth_mbps} --apply")
        print(f"\nOr apply manually:")
        print(f"  curl -X POST -H 'Content-Type: application/json' \\")
        print(f"    -u {ONOS_USER}:{ONOS_PASSWORD} \\")
        print(f"    http://{ONOS_HOST}:{ONOS_PORT}/onos/v1/network/configuration \\")
        print(f"    -d @{config_file}")


def verify_bandwidth():
    """Verify current bandwidth configuration."""
    print(f"\n{'='*60}")
    print("ONOS Link Bandwidth Verification")
    print(f"{'='*60}\n")
    
    if not check_onos_connection():
        sys.exit(1)
    
    # Get current configuration
    print("\nCurrent Network Configuration:")
    print("-" * 40)
    
    config = verify_config()
    if config:
        # Check ports
        ports = config.get("ports", {})
        if ports:
            print("\nPort Bandwidth Configuration:")
            for port_key, port_config in ports.items():
                bandwidth = port_config.get("bandwidth", "Not set")
                port_speed = port_config.get("portSpeed", "Not set")
                if isinstance(bandwidth, int):
                    bandwidth_mbps = bandwidth / 1_000_000
                    print(f"  {port_key}: {bandwidth_mbps:.0f} Mbps")
        else:
            print("\n  No port configuration found")
        
        # Check links
        links = config.get("links", {})
        if links:
            print("\nLink Bandwidth Configuration:")
            for link_key, link_config in links.items():
                basic = link_config.get("basic", {})
                bandwidth = basic.get("bandwidth", "Not set")
                if isinstance(bandwidth, int):
                    bandwidth_mbps = bandwidth / 1_000_000
                    print(f"  {link_key}: {bandwidth_mbps:.0f} Mbps")
        else:
            print("\n  No link configuration found")
    
    # Get discovered links
    print("\nDiscovered Links in ONOS:")
    print("-" * 40)
    
    links = get_links_info()
    if links:
        for link in links:
            src = link.get("src", {})
            dst = link.get("dst", {})
            print(f"  {src.get('device')}:{src.get('port')} -> {dst.get('device')}:{dst.get('port')}")
    else:
        print("  No links discovered")


# ==============================================================================
# ===                          CLI INTERFACE                               ===
# ==============================================================================

def main():
    global ONOS_HOST, ONOS_PORT
    
    parser = argparse.ArgumentParser(
        description="Configure ONOS link bandwidth for spine-leaf topology",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 500Mbps configuration (don't apply)
  python3 %(prog)s --bandwidth 500
  
  # Generate and apply 500Mbps configuration
  python3 %(prog)s --bandwidth 500 --apply
  
  # Clear existing config and apply new one
  python3 %(prog)s --bandwidth 500 --apply --clear
  
  # Verify current configuration
  python3 %(prog)s --verify
        """
    )
    
    parser.add_argument(
        "--bandwidth", "-b",
        type=int,
        default=500,
        help="Target bandwidth in Mbps (default: 500)"
    )
    
    parser.add_argument(
        "--apply", "-a",
        action="store_true",
        help="Apply configuration to ONOS"
    )
    
    parser.add_argument(
        "--clear", "-c",
        action="store_true",
        help="Clear existing configuration before applying"
    )
    
    parser.add_argument(
        "--verify", "-v",
        action="store_true",
        help="Verify current bandwidth configuration"
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default=ONOS_HOST,
        help=f"ONOS host (default: {ONOS_HOST})"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=ONOS_PORT,
        help=f"ONOS port (default: {ONOS_PORT})"
    )
    
    args = parser.parse_args()
    
    # Update globals if custom host/port specified
    ONOS_HOST = args.host
    ONOS_PORT = args.port
    
    if args.verify:
        verify_bandwidth()
    else:
        configure_bandwidth(args.bandwidth, args.apply, args.clear)


if __name__ == "__main__":
    main()
