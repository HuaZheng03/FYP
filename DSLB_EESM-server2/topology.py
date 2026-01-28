import requests


# ONOS Controller URL and authentication
ONOS_CONTROLLER_IP = "192.168.126.1"
ONOS_BASE_URL = f'http://{ONOS_CONTROLLER_IP}:8181/onos/v1'
AUTH = ('', '')

# Function to fetch devices (switches) from ONOS
def fetch_devices():
    devices_response = requests.get(f"{ONOS_BASE_URL}/devices", auth=AUTH)
    devices = devices_response.json().get('devices', [])
    
    processed_devices = []
    for device in devices:
        processed_device = { 
            'id': device.get('id'),
            'type': device.get('type'),
            'available': device.get('available'),
            'role': device.get('role'),
            'mfr': device.get('mfr'),
            'hw': device.get('hw'),
            'sw': device.get('sw'),
            'serial': device.get('serial'),
            'driver': device.get('driver'),
            'chassisId': device.get('chassisId'),
            'lastUpdate': device.get('lastUpdate'),
            'humanReadableLastUpdate': device.get('humanReadableLastUpdate'),
            'annotations': device.get('annotations', {})
        }
        processed_devices.append(processed_device)
    return processed_devices

# Function to fetch links (connections) from ONOS
def fetch_links():
    links_response = requests.get(f"{ONOS_BASE_URL}/links", auth=AUTH)
    links = links_response.json().get('links', [])
    
    processed_links = []
    for link in links:
        processed_link = {
            'src': link.get('src'),
            'dst': link.get('dst'),
            'type': link.get('type'),
            'state': link.get('state'),
            'annotations': link.get('annotations', {})
        }
        processed_links.append(processed_link)
    return processed_links

# Function to fetch hosts from ONOS
def fetch_hosts():
    hosts_response = requests.get(f"{ONOS_BASE_URL}/hosts", auth=AUTH)
    hosts = hosts_response.json().get('hosts', [])
    
    processed_hosts = []
    for host in hosts:
        processed_host = {
            'id': host.get('id'),
            'mac': host.get('mac'),
            'vlan': host.get('vlan'),
            'ipAddresses': host.get('ipAddresses', []),
            'locations': host.get('locations', []),  # Ensure locations are captured
        }
        processed_hosts.append(processed_host)
    return processed_hosts

# Function to gather and return all topology data (devices, links, hosts)
def get_topology_data():
    try:
        devices = fetch_devices()
        links = fetch_links()
        hosts = fetch_hosts()
        
        # Combine all data into a single dictionary
        topology_data = {
            'devices': devices,
            'hosts': hosts,
            'links': links
        }
        return topology_data
    except Exception as e:
        raise RuntimeError(f"Error fetching topology data: {str(e)}")