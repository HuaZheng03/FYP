import random
from collections import defaultdict

# Device ID mappings
DEVICE_IDS = {
    "leaf1": "of:000072ecfb3ccb4c",
    "leaf2": "of:000042b1a1405d41",
    "leaf3": "of:000032095cbf1043",
    "leaf6": "of:0000ca44716bdf4b",
    "spine1": "of:0000d6dee87ca841",
    "spine2": "of:00000ac352fff34c",
}

# Available paths: (src, dst) -> list of paths
# Each path is a list of (device_id, out_port) tuples
AVAILABLE_PATHS = {
    # leaf1 -> leaf6
    ("leaf1", "leaf6"): [
        [(DEVICE_IDS["leaf1"], 1), (DEVICE_IDS["spine1"], 2)],
        [(DEVICE_IDS["leaf1"], 5), (DEVICE_IDS["spine2"], 4)],
    ],
    
    # leaf6 -> leaf1
    ("leaf6", "leaf1"): [
        [(DEVICE_IDS["leaf6"], 1), (DEVICE_IDS["spine1"], 1)],
        [(DEVICE_IDS["leaf6"], 2), (DEVICE_IDS["spine2"], 1)],
    ],
    
    # leaf1 -> leaf2
    ("leaf1", "leaf2"): [
        [(DEVICE_IDS["leaf1"], 1), (DEVICE_IDS["spine1"], 3)],
        [(DEVICE_IDS["leaf1"], 5), (DEVICE_IDS["spine2"], 2)],
    ],
    
    # leaf2 -> leaf1
    ("leaf2", "leaf1"): [
        [(DEVICE_IDS["leaf2"], 3), (DEVICE_IDS["spine1"], 1)],
        [(DEVICE_IDS["leaf2"], 1), (DEVICE_IDS["spine2"], 1)],
    ],
    
    # leaf1 -> leaf3
    ("leaf1", "leaf3"): [
        [(DEVICE_IDS["leaf1"], 1), (DEVICE_IDS["spine1"], 4)],
        [(DEVICE_IDS["leaf1"], 5), (DEVICE_IDS["spine2"], 3)],
    ],
    
    # leaf3 -> leaf1
    ("leaf3", "leaf1"): [
        [(DEVICE_IDS["leaf3"], 1), (DEVICE_IDS["spine1"], 1)],
        [(DEVICE_IDS["leaf3"], 2), (DEVICE_IDS["spine2"], 1)],
    ],
    
    # leaf2 -> leaf3
    ("leaf2", "leaf3"): [
        [(DEVICE_IDS["leaf2"], 3), (DEVICE_IDS["spine1"], 4)],
        [(DEVICE_IDS["leaf2"], 1), (DEVICE_IDS["spine2"], 3)],
    ],
    
    # leaf3 -> leaf2
    ("leaf3", "leaf2"): [
        [(DEVICE_IDS["leaf3"], 1), (DEVICE_IDS["spine1"], 3)],
        [(DEVICE_IDS["leaf3"], 2), (DEVICE_IDS["spine2"], 2)],
    ],
    
    # leaf2 -> leaf6
    ("leaf2", "leaf6"): [
        [(DEVICE_IDS["leaf2"], 3), (DEVICE_IDS["spine1"], 2)],
        [(DEVICE_IDS["leaf2"], 1), (DEVICE_IDS["spine2"], 4)],
    ],
    
    # leaf6 -> leaf2
    ("leaf6", "leaf2"): [
        [(DEVICE_IDS["leaf6"], 1), (DEVICE_IDS["spine1"], 3)],
        [(DEVICE_IDS["leaf6"], 2), (DEVICE_IDS["spine2"], 2)],
    ],
    
    # leaf3 -> leaf6
    ("leaf3", "leaf6"): [
        [(DEVICE_IDS["leaf3"], 1), (DEVICE_IDS["spine1"], 2)],
        [(DEVICE_IDS["leaf3"], 2), (DEVICE_IDS["spine2"], 4)],
    ],
    
    # leaf6 -> leaf3
    ("leaf6", "leaf3"): [
        [(DEVICE_IDS["leaf6"], 1), (DEVICE_IDS["spine1"], 4)],
        [(DEVICE_IDS["leaf6"], 2), (DEVICE_IDS["spine2"], 3)],
    ],
}


class LinkLoadBalancer:
    def __init__(self):
        self.device_ids = DEVICE_IDS
        self.available_paths = AVAILABLE_PATHS
    
    def compute_path_costs_cumulative(self, usage, src, dst):
        """
        Compute path costs using cumulative bandwidth usage.
        
        Args:
            usage: Dict with structure {device_id: {port: {'total_bytes': X}}}
            src: Source device name (e.g., "leaf1")
            dst: Destination device name (e.g., "leaf6")
        
        Returns:
            Dict: {path_index: total_cost_bytes}
        """
        paths = AVAILABLE_PATHS.get((src, dst), [])
        path_costs = {}
        
        for path_index, path_hops in enumerate(paths):
            total_cost = 0
            path_valid = True
            
            for (device_id, out_port) in path_hops:
                # Convert port to string to match stats format
                port_str = str(out_port)
                
                # Check if device exists
                if device_id not in usage:
                    print(f"[DEBUG] Device {device_id} not found in usage stats")
                    path_valid = False
                    break
                
                # Check if port exists
                if port_str not in usage[device_id]:
                    print(f"[DEBUG] Port {port_str} not found on device {device_id}")
                    print(f"[DEBUG] Available ports: {list(usage[device_id].keys())}")
                    path_valid = False
                    break
                
                port_data = usage[device_id][port_str]
                
                # Get total bytes
                total_bytes = port_data.get('total_bytes', 0)
                total_cost += total_bytes
            
            if path_valid:
                path_costs[path_index] = total_cost
        
        return path_costs
    
    def compute_path_ratios_from_costs(self, path_costs):
        """
        Convert path costs to ratios using inverse weighting.
        Lower cost = higher ratio (more traffic allocated).
        
        Args:
            path_costs: Dict {path_index: cost_bytes}
        
        Returns:
            Dict: {path_index: ratio} where ratios sum to 1.0
        """
        if not path_costs:
            return {}
        
        # If all costs are zero, return equal distribution
        if all(cost == 0 for cost in path_costs.values()):
            num_paths = len(path_costs)
            return {path: 1.0 / num_paths for path in path_costs.keys()}
        
        # Inverse weighting: lower cost = higher weight
        weights = {}
        for path, cost in path_costs.items():
            weights[path] = 1.0 / (cost + 1)
        
        # Normalize to ratios (sum = 1.0)
        total_weight = sum(weights.values())
        ratios = {path: weight / total_weight for path, weight in weights.items()}
        
        return ratios


def get_device_name_from_id(device_id):
    """Convert device ID to device name"""
    for name, dev_id in DEVICE_IDS.items():
        if dev_id in device_id:
            return name
    return device_id