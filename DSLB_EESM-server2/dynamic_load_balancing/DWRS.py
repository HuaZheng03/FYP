import random
import math
from pprint import pprint

# Import the new function from your telemetry script
# Make sure server_telemetry.py is in the same directory
try:
    from data_reception.server_telemetry import get_all_server_metrics
except ImportError:
    print("Error: Could not import 'get_all_server_metrics' from 'server_telemetry.py'.")
    print("Please ensure the file exists and is in the same directory.")
    exit(1)

# --- DWRS Algorithm Configuration ---
# Weights now only account for CPU and Memory, so they must sum to 1.0.
# The original 5:4 ratio between CPU and Memory is maintained.
ALPHA = 0.55  # Weight for CPU
BETA = 0.45   # Weight for Memory

def calculate_comprehensive_load(metrics, alpha, beta):
    """
    Calculates a single comprehensive load score from multiple metrics.
    This formula is based on the one described in the research papers.
    """
    cpu_load = metrics['cpu']
    mem_load = metrics['mem']
    
    # The comprehensive load is a weighted average of the individual metrics.
    comprehensive_load = (cpu_load * alpha) + (mem_load * beta)
    return comprehensive_load

def convert_load_to_weight(load):

    if load >= 100:
        return 1
    weight = 100 - math.floor(load)
    return int(weight)

def update_server_weights():
    """
    Fetches the latest server metrics and calculates a dynamic weight for each active server.
    
    Returns:
        list: A list of dictionaries, where each dictionary represents an active
              server and contains its IP, metrics, load, and DWRS weight.
    """
    # 1. Get real-time metrics for all active servers
    all_metrics = get_all_server_metrics()
    
    if not all_metrics:
        print("No active servers found. Cannot calculate weights.")
        return []

    servers_with_weights = []
    print("\n--- Calculating DWRS Weights for Active Servers ---")
    for ip, metrics in all_metrics.items():
        # 2. Calculate comprehensive load for each server
        load = calculate_comprehensive_load(metrics, ALPHA, BETA)
        
        # 3. Convert load to dynamic weight
        weight = convert_load_to_weight(load)
        
        servers_with_weights.append({
            "ip": ip,
            "metrics": metrics,
            "comprehensive_load": round(load, 2),
            "dynamic_weight": weight
        })
        
    return servers_with_weights

def select_target_server(servers):

    if not servers:
        print("Cannot select a server: The list of active servers is empty.")
        return None
    
    if len(servers) == 1:
        the_only_server = servers[0]
        print("\n--- Selecting Target Server ---")
        print(f"Only one server is active ({the_only_server['ip']}). Selecting it by default.")
        print(f"*** Target Server Selected: {the_only_server['ip']} ***")
        return the_only_server
    
    # 1. Calculate the sum of all weights
    total_weight = sum(server['dynamic_weight'] for server in servers)
    
    if total_weight == 0:
        print("Cannot select a server: Total weight of all servers is 0.")
        # Fallback: return a random server to avoid complete failure
        return random.choice(servers)

    # 2. Generate a random number between 1 and the total weight
    random_pick = random.randint(1, total_weight)
    
    # 3. Iterate through servers until the cumulative weight exceeds the random number
    print(f"\n--- Selecting Target Server (Total Weight: {total_weight}, Pick: {random_pick}) ---")
    cumulative_weight = 0
    for server in servers:
        cumulative_weight += server['dynamic_weight']
        print(f"  - Checking Server {server['ip']} (Weight: {server['dynamic_weight']}). Cumulative: {cumulative_weight}")
        if cumulative_weight >= random_pick:
            print(f"*** Target Server Selected: {server['ip']} ***")
            return server
            
    # This part should ideally not be reached if total_weight > 0
    return None