import requests
from requests.auth import HTTPBasicAuth

# ==============================================================================
# ===                           CONFIGURATION                              ===
# ==============================================================================

ONOS_HOST = "192.168.126.1"
ONOS_PORT = 8181
ONOS_USER = ""
ONOS_PASSWORD = ""

# Timeout for API requests
REQUEST_TIMEOUT = 10  # seconds

# Try to import alert function (gracefully handle if alerts module not available)
try:
    from alerts import alert_onos_connection_failed
    ALERTS_AVAILABLE = True
except ImportError:
    ALERTS_AVAILABLE = False

# ==============================================================================
# ===                      CORE TELEMETRY FUNCTIONS                        ===
# ==============================================================================

def get_onos_port_stats():
    """
    Fetch CUMULATIVE port statistics from ONOS REST API.
    
    Returns:
        dict: Port statistics organized by device_id and port number
        {
            "of:000072ecfb3ccb4c": {
                "1": {
                    "bytesSent": 123456789,
                    "bytesReceived": 987654321,
                    "packetsSent": 12345,
                    "packetsReceived": 54321
                },
                "5": {...}
            },
            ...
        }
    """
    url = f"http://{ONOS_HOST}:{ONOS_PORT}/onos/v1/statistics/ports"
    
    try:
        response = requests.get(
            url,
            auth=HTTPBasicAuth(ONOS_USER, ONOS_PASSWORD),
            timeout=REQUEST_TIMEOUT
        )
        
        if response.status_code != 200:
            error_msg = f"API returned status {response.status_code}: {response.text[:200]}"
            print(f"[ERROR] ONOS API returned status {response.status_code}")
            print(f"[ERROR] URL: {url}")
            print(f"[ERROR] Response: {response.text[:200]}")
            # Alert for non-200 response
            if ALERTS_AVAILABLE:
                alert_onos_connection_failed(f"{ONOS_HOST}:{ONOS_PORT}", error_msg)
            return {}
        
        data = response.json()
        stats_by_device = {}
        
        for device_stats in data.get('statistics', []):
            device_id = device_stats.get('device', '')
            if isinstance(device_id, dict):
                device_id = device_id.get('id', '')
            
            if not device_id:
                continue
            
            ports = device_stats.get('ports', [])
            port_stats = {}
            
            for port in ports:
                port_num = str(port.get('port', ''))
                
                port_stats[port_num] = {
                    'bytesSent': port.get('bytesSent', 0),
                    'bytesReceived': port.get('bytesReceived', 0),
                    'packetsSent': port.get('packetsSent', 0),
                    'packetsReceived': port.get('packetsReceived', 0)
                }
            
            stats_by_device[device_id] = port_stats
        
        total_devices = len(stats_by_device)
        total_ports = sum(len(ports) for ports in stats_by_device.values())
        
        if total_devices > 0:
            print(f"[Telemetry] ✓ Retrieved stats for {total_devices} devices, {total_ports} ports")
        else:
            print(f"[Telemetry] ⚠ No statistics retrieved from ONOS")
        
        return stats_by_device
        
    except requests.exceptions.Timeout:
        error_msg = f"Timeout after {REQUEST_TIMEOUT}s"
        print(f"[ERROR] Timeout connecting to ONOS at {ONOS_HOST}:{ONOS_PORT}")
        # Alert for timeout
        if ALERTS_AVAILABLE:
            alert_onos_connection_failed(f"{ONOS_HOST}:{ONOS_PORT}", error_msg)
        return {}
        
    except requests.exceptions.ConnectionError as e:
        error_msg = str(e)
        print(f"[ERROR] Cannot connect to ONOS at {ONOS_HOST}:{ONOS_PORT}")
        print(f"[ERROR] {e}")
        # Alert for connection error
        if ALERTS_AVAILABLE:
            alert_onos_connection_failed(f"{ONOS_HOST}:{ONOS_PORT}", error_msg)
        return {}
        
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Unexpected error fetching ONOS stats: {e}")
        import traceback
        traceback.print_exc()
        # Alert for unexpected error
        if ALERTS_AVAILABLE:
            alert_onos_connection_failed(f"{ONOS_HOST}:{ONOS_PORT}", error_msg)
        return {}


def get_device_name_from_id(device_id):
    """Convert device ID to friendly name"""
    device_map = {
        "of:000072ecfb3ccb4c": "leaf1",
        "of:000042b1a1405d41": "leaf2",
        "of:000032095cbf1043": "leaf3",
        "of:0000ca44716bdf4b": "leaf6",
        "of:0000d6dee87ca841": "spine1",
        "of:00000ac352fff34c": "spine2",
    }
    return device_map.get(device_id, device_id)


if __name__ == "__main__":
    print("Testing ONOS connection...")
    stats = get_onos_port_stats()
    
    if stats:
        print("\n✓ Connection successful!")
        for device_id, ports in stats.items():
            name = get_device_name_from_id(device_id)
            print(f"\n{name}: {len(ports)} ports")
            for port_num, port_data in list(ports.items())[:2]:
                tx = port_data.get('bytesSent', 0)
                rx = port_data.get('bytesReceived', 0)
                print(f"  Port {port_num}: TX={tx:,} RX={rx:,}")
    else:
        print("\n✗ Connection failed!")