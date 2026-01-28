import sys
from prometheus_api_client import PrometheusConnect
from pprint import pprint

# --- Configuration ---
# Replace with the IP address of your Prometheus server (Server 2)
PROMETHEUS_URL = "http://192.168.126.2:9090"

# 80 seconds 
BOOT_GRACE_PERIOD_SECONDS = 80

try:
    # Connect to Prometheus
    print(f"Connecting to Prometheus at {PROMETHEUS_URL}...")
    prom = PrometheusConnect(url=PROMETHEUS_URL, disable_ssl=True)
except Exception as e:
    print(f"Error: Could not connect to Prometheus. Please check the URL. \n{e}")
    sys.exit(1)


# --- PromQL Queries ---

# 1. Memory Usage Percentage
mem_usage_query = '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100'

# 2. CPU Usage Percentage (Averaged across all cores)
cpu_usage_query = 'avg by (instance) ((1 - irate(node_cpu_seconds_total{mode="idle"}[5s])) * 100)'

# 3. Total Memory in Bytes
total_mem_query = 'node_memory_MemTotal_bytes'

# 4. Total CPU Cores
total_cpu_query = 'count(node_cpu_seconds_total{mode="idle"}) by (instance)'

# --- Fetch and Display Metrics ---
def fetch_and_print_metrics(metric_name, query):
    """Fetches and prints metrics for a given PromQL query."""
    print(f"\n--- Fetching {metric_name} ---")
    try:
        # Execute the query
        metric_data = prom.custom_query(query=query)
        if not metric_data:
            print(f"No data received for {metric_name}. Check if Node Exporter is running.")
            return

        # Print results for each server (instance)
        for result in metric_data:
            metric = result['metric']
            instance = metric['instance']
            value = float(result['value'][1])
            print(f"  - Server: {instance.split(':')[0]:<15} | Usage: {value:.2f}%")

    except Exception as e:
        print(f"Error querying Prometheus for {metric_name}: {e}")

def check_and_evaluate_load(cpu_threshold=90.0, mem_threshold=90.0):
    """
    Checks CPU and Memory usage for STABLE servers against their separate thresholds.
    Servers in their boot grace period are ignored.
    """
    print("\n--- Checking System Load for Scaling (with Grace Period) ---")

    # --- 1. Identify Stable Servers (those past the boot grace period) ---
    stable_server_ips = []
    try:
        # This query calculates the uptime for each server in seconds
        uptime_query = f'time() - node_boot_time_seconds{{job="node_exporter"}} > {BOOT_GRACE_PERIOD_SECONDS}'
        stable_servers_data = prom.custom_query(query=uptime_query)
        
        # Create a list of IPs for servers that are "stable"
        stable_server_ips = [d['metric']['instance'].split(':')[0] for d in stable_servers_data]
        
        if stable_server_ips:
            print(f"Found {len(stable_server_ips)} stable server(s) past the grace period: {stable_server_ips}")
        else:
            print("No servers are past the boot grace period. Waiting for servers to stabilize.")
            return False # Important: Don't make scaling decisions if no servers are stable

    except Exception as e:
        print(f"Could not determine server uptime: {e}")
        return False # Fail safely

    # --- 2. Explicitly Compute and Check CPU Load for STABLE servers ---
    try:
        cpu_data = prom.custom_query(query=cpu_usage_query)
        # FILTER the data to only include stable servers
        stable_cpu_data = [d for d in cpu_data if d['metric']['instance'].split(':')[0] in stable_server_ips]

        if not stable_cpu_data:
            print("No stable CPU data found. Skipping check.")
        else:
            num_servers = len(stable_cpu_data)
            usage_values = [float(result['value'][1]) for result in stable_cpu_data]
            
            # The rest of this logic is the same, but now runs only on filtered data
            if num_servers == 1:
                usage = usage_values[0]
                print(f"Stable Server CPU Usage: {usage:.2f}%")
                if usage > cpu_threshold:
                    print(f"ALERT: Stable server CPU usage exceeds threshold of {cpu_threshold}%!")
                    return True
            elif num_servers > 1:
                average_usage = sum(usage_values) / num_servers
                print(f"Average Stable CPU Usage ({num_servers} servers): {average_usage:.2f}%")
                if average_usage > cpu_threshold:
                    print(f"ALERT: Average stable CPU usage exceeds threshold of {cpu_threshold}%!")
                    return True
    except Exception as e:
        print(f"Error during CPU evaluation: {e}")

    # --- 3. Explicitly Compute and Check Memory Load for STABLE servers ---
    try:
        mem_data = prom.custom_query(query=mem_usage_query)
        # FILTER the data to only include stable servers
        stable_mem_data = [d for d in mem_data if d['metric']['instance'].split(':')[0] in stable_server_ips]

        if not stable_mem_data:
            print("No stable Memory data found. Skipping check.")
        else:
            num_servers = len(stable_mem_data)
            usage_values = [float(result['value'][1]) for result in stable_mem_data]
            
            if num_servers == 1:
                usage = usage_values[0]
                print(f"Stable Server Memory Usage: {usage:.2f}%")
                if usage > mem_threshold:
                    print(f"ALERT: Stable server Memory usage exceeds threshold of {mem_threshold}%!")
                    return True
            elif num_servers > 1:
                average_usage = sum(usage_values) / num_servers
                print(f"Average Stable Memory Usage ({num_servers} servers): {average_usage:.2f}%")
                if average_usage > mem_threshold:
                    print(f"ALERT: Average stable Memory usage exceeds threshold of {mem_threshold}%!")
                    return True
    except Exception as e:
        print(f"Error during Memory evaluation: {e}")

    # --- 4. Final Result ---
    print("OK: System load is within all thresholds.")
    return False

def get_all_server_metrics():
    """
    Fetches CPU/Memory usage percentages AND total allocated CPU/Memory
    for all active servers.

    Returns:
        dict: A dictionary where keys are server IPs and values are another
              dictionary containing their metrics.
              Example:
              { '192.168.6.2': { 'cpu': 15.5, 'mem': 30.1, 'total_cpu_cores': 4, 'total_mem_gb': 7.8 } }
    """
    print("\n--- Collecting Full Telemetry for Load Balancer ---")
    server_metrics = {}
    try:
        # Fetch all metrics
        cpu_usage_data = prom.custom_query(query=cpu_usage_query)
        mem_usage_data = prom.custom_query(query=mem_usage_query)
        total_cpu_data = prom.custom_query(query=total_cpu_query)
        total_mem_data = prom.custom_query(query=total_mem_query)

        if not cpu_usage_data:
            print("No active servers found (could not fetch CPU usage data).")
            return {}

        # Initialize dictionary with CPU usage
        for result in cpu_usage_data:
            ip = result['metric']['instance'].split(':')[0]
            server_metrics[ip] = {
                'cpu': float(result['value'][1]),
                'mem': 0.0,
                'total_cpu_cores': 0,
                'total_mem_gb': 0.0
            }
        
        # Populate memory usage
        for result in mem_usage_data:
            ip = result['metric']['instance'].split(':')[0]
            if ip in server_metrics:
                server_metrics[ip]['mem'] = float(result['value'][1])

        # Populate total CPU cores
        for result in total_cpu_data:
            ip = result['metric']['instance'].split(':')[0]
            if ip in server_metrics:
                server_metrics[ip]['total_cpu_cores'] = int(result['value'][1])
        
        # Populate total memory (and convert from Bytes to GB for readability)
        for result in total_mem_data:
            ip = result['metric']['instance'].split(':')[0]
            if ip in server_metrics:
                mem_in_bytes = float(result['value'][1])
                mem_in_gb = round(mem_in_bytes / (1024**3), 1)
                server_metrics[ip]['total_mem_gb'] = mem_in_gb
        
        print(f"Successfully collected metrics for {len(server_metrics)} active server(s).")
        return server_metrics

    except Exception as e:
        print(f"An error occurred while getting all server metrics: {e}")
        return {}