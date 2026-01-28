import requests
import json
from requests.auth import HTTPBasicAuth

# ==============================================================================
# ===                           CONFIGURATION                            ===
# ==============================================================================
ONOS_HOST = "http://192.168.126.1:8181"
ONOS_USER = ""
ONOS_PASS = "" 
AUTH = HTTPBasicAuth(ONOS_USER, ONOS_PASS)
HEADERS = {'Content-Type': 'application/json', 'Accept': 'application/json'}
TIMEOUT = 5

# ==============================================================================
# ===                      FLOW CONTROL FUNCTIONS                          ===
# ==============================================================================

def build_flow_rule(device_id, priority, match_criteria, action_port):
    """
    Constructs a JSON payload for a flow rule that forwards traffic to a
    single specified port.
    """
    flow = {
        "priority": priority,
        "timeout": 0,  # 0 means the rule is permanent until removed
        "isPermanent": True,
        "deviceId": device_id,
        "treatment": {
            "instructions": [{"type": "OUTPUT", "port": action_port}]
        },
        "selector": {
            "criteria": match_criteria
        }
    }
    return flow

def install_flow_rule(flow_rule):
    """
    Installs a single flow rule using the ONOS REST API.
    Returns the location header (containing flowId) on success, otherwise None.
    """
    device_id = flow_rule["deviceId"]
    url = f"{ONOS_HOST}/onos/v1/flows/{device_id}"
    try:
        response = requests.post(url, data=json.dumps(flow_rule), auth=AUTH, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        print(f"  > Successfully installed flow on {device_id}.")
        # The response location header contains the URL to the new flow, including its ID
        return response.headers.get('Location')
    except requests.exceptions.RequestException as e:
        print(f"  > ERROR: Failed to install flow on {device_id}: {e}")
        return None

def remove_flow_rule(device_id, flow_id):
    """
    Removes a single flow rule from a device using its flow ID.
    """
    # The flow ID is part of the URL, e.g., /onos/v1/flows/of:0000.../12345
    url = f"{ONOS_HOST}/onos/v1/flows/{device_id}/{flow_id}"
    try:
        response = requests.delete(url, auth=AUTH, timeout=TIMEOUT)
        response.raise_for_status()
        print(f"  > Successfully removed flow {flow_id} from {device_id}.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"  > WARN: Failed to remove flow {flow_id} from {device_id}: {e}")
        return False
