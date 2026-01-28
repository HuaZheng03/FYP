import sys
from prometheus_api_client import PrometheusConnect
from pprint import pprint

# --- Configuration ---
PROMETHEUS_URL = "http://192.168.126.2:9090"
BOOT_GRACE_PERIOD_SECONDS = 80
# NOTE: SCALING_LOOKBACK_PERIOD is implicitly 5m in run.py, kept here for context.
SCALING_LOOKBACK_PERIOD = '5m' 

# Try to import alert function (gracefully handle if alerts module not available)
try:
    from alerts import alert_prometheus_connection_failed
    ALERTS_AVAILABLE = True
except ImportError:
    ALERTS_AVAILABLE = False

try:
    print(f"Connecting to Prometheus at {PROMETHEUS_URL}...")
    prom = PrometheusConnect(url=PROMETHEUS_URL, disable_ssl=True)
except Exception as e:
    error_msg = str(e)
    print(f"Error: Could not connect to Prometheus. Please check the URL. \n{error_msg}")
    # Alert for Prometheus connection failure
    if ALERTS_AVAILABLE:
        alert_prometheus_connection_failed(PROMETHEUS_URL, error_msg)
    sys.exit(1)


# --- PromQL Queries (SIMPLE INSTANTANEOUS CHECK) ---

# 1. Memory Usage Percentage (Instantaneous)
mem_usage_query = '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100'

# 2. CPU Usage Percentage (Instantaneous 5s rate for 2s scrape)
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
        metric_data = prom.custom_query(query=query)
        if not metric_data:
            print(f"No data received for {metric_name}. Check if Node Exporter is running.")
            return

        for result in metric_data:
            metric = result['metric']
            instance = metric['instance']
            value = float(result['value'][1])
            print(f"  - Server: {instance.split(':')[0]:<15} | Usage: {value:.2f}%")

    except Exception as e:
        print(f"Error querying Prometheus for {metric_name}: {e}")

def check_and_evaluate_load(cpu_threshold=90.0, mem_threshold=90.0):
    """
    This function is kept simple but remains mandatory for the run.py control flow structure.
    The actual 5-minute sustained logic is in run.py.
    """
    print("\n--- Checking System Load for Scaling (Instantaneous 15s Load) ---")

    # This function is primarily used to pull data, so we simplify the internal checks.
    # The actual return value here doesn't control the final scaling decision in run.py.
    
    stable_server_ips = []
    try:
        uptime_query = f'time() - node_boot_time_seconds{{job="node_exporter"}} > {BOOT_GRACE_PERIOD_SECONDS}'
        stable_servers_data = prom.custom_query(query=uptime_query)
        stable_server_ips = [d['metric']['instance'].split(':')[0] for d in stable_servers_data]
        if not stable_server_ips:
            print("No servers are past the boot grace period. Waiting for servers to stabilize.")
            return False 

    except Exception as e:
        print(f"Could not determine server uptime: {e}")
        return False 
        
    # The true scaling decision is deferred to run.py, so we return False here 
    # and let run.py handle the history check.
    return False

def get_all_server_metrics():
    """
    Fetches detailed metrics for DWRS (load balancing on Server 1) and run.py's history.
    """
    print("\n--- Collecting Telemetry From All Active Server(s) ---")
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
        
        # Populate other metrics
        for result in mem_usage_data:
            ip = result['metric']['instance'].split(':')[0]
            if ip in server_metrics:
                server_metrics[ip]['mem'] = float(result['value'][1])

        for result in total_cpu_data:
            ip = result['metric']['instance'].split(':')[0]
            if ip in server_metrics:
                server_metrics[ip]['total_cpu_cores'] = int(result['value'][1])
        
        for result in total_mem_data:
            ip = result['metric']['instance'].split(':')[0]
            if ip in server_metrics:
                mem_in_bytes = float(result['value'][1])
                mem_in_gb = round(mem_in_bytes / (1024**3), 1)
                server_metrics[ip]['total_mem_gb'] = mem_in_gb
        
        print(f"Successfully collected metrics for {len(server_metrics)} active server(s).")
        return server_metrics

    except Exception as e:
        # This is where the HTTP 400 error was occurring; it should now be fixed with the simpler queries.
        print(f"An error occurred while getting all server metrics: {e}")
        return {}