from prometheus_api_client import PrometheusConnect
from datetime import datetime, timedelta, timezone
import warnings

# Suppress warnings for cleaner output
warnings.filterwarnings("ignore")

# --- Configuration ---
PROMETHEUS_URL = "http://192.168.126.2:9090"
LOCAL_TZ = timezone(timedelta(hours=8))

# Try to import alert function (gracefully handle if alerts module not available)
try:
    from alerts import alert_prometheus_connection_failed
    ALERTS_AVAILABLE = True
except ImportError:
    ALERTS_AVAILABLE = False

# Initialize Prometheus connection
try:
    prom = PrometheusConnect(url=PROMETHEUS_URL, disable_ssl=True)
except Exception as e:
    error_msg = str(e)
    print(f"Error: Could not connect to Prometheus at {PROMETHEUS_URL}. {error_msg}")
    # Alert for Prometheus connection failure
    if ALERTS_AVAILABLE:
        alert_prometheus_connection_failed(PROMETHEUS_URL, error_msg)
    prom = None


def get_hourly_request_count_prometheus(lookback_hours: int = 1) -> int:
    """
    Queries Prometheus for the total number of HTTP requests across all Apache 
    servers in the specified time window.
    
    This method is reliable even during reactive scaling because:
    - Prometheus stores metrics centrally (not on individual servers)
    - The increase() function handles counter resets from server restarts
    - sum() aggregates across all servers that were active during the period
    
    Args:
        lookback_hours: Number of hours to look back (default: 1 hour)
        
    Returns:
        int: Total HTTP requests in the time window, or None if query fails
    """
    if prom is None:
        print("ERROR: Prometheus connection not available.")
        return None
    
    try:
        # Query for total accesses across all Apache servers in the last hour
        # increase() calculates the increase in counter value over the time range
        # sum() aggregates across all instances
        query = f'sum(increase(apache_accesses_total{{job="apache_exporter"}}[{lookback_hours}h]))'
        
        result = prom.custom_query(query=query)
        
        if result and len(result) > 0:
            total_requests = float(result[0]['value'][1])
            return int(total_requests)
        else:
            print(f"WARNING: No data returned from Prometheus for apache_accesses_total.")
            return 0
            
    except Exception as e:
        print(f"ERROR: Failed to query Prometheus for HTTP requests: {e}")
        return None


def get_request_count_per_server(lookback_hours: int = 1) -> dict:
    """
    Gets the HTTP request count broken down by each server.
    Useful for debugging and monitoring individual server contributions.
    
    Args:
        lookback_hours: Number of hours to look back (default: 1 hour)
        
    Returns:
        dict: {server_ip: request_count} mapping
    """
    if prom is None:
        print("ERROR: Prometheus connection not available.")
        return {}
    
    try:
        # Query per-instance without aggregation
        query = f'increase(apache_accesses_total{{job="apache_exporter"}}[{lookback_hours}h])'
        
        result = prom.custom_query(query=query)
        
        server_counts = {}
        for item in result:
            instance = item['metric'].get('instance', 'unknown')
            # Extract IP from instance (format: "ip:port")
            server_ip = instance.split(':')[0]
            count = int(float(item['value'][1]))
            server_counts[server_ip] = count
        
        return server_counts
        
    except Exception as e:
        print(f"ERROR: Failed to query per-server request counts: {e}")
        return {}


def get_current_active_connections() -> int:
    """
    Gets the current number of active connections across all Apache servers.
    Useful for real-time monitoring.
    
    Returns:
        int: Total active connections, or None if query fails
    """
    if prom is None:
        return None
    
    try:
        # Apache scoreboard busy workers
        query = 'sum(apache_workers{state="busy"})'
        
        result = prom.custom_query(query=query)
        
        if result and len(result) > 0:
            return int(float(result[0]['value'][1]))
        return 0
        
    except Exception as e:
        print(f"ERROR: Failed to query active connections: {e}")
        return None


def get_requests_rate_per_second() -> float:
    """
    Gets the current request rate (requests per second) across all servers.
    
    Returns:
        float: Requests per second, or None if query fails
    """
    if prom is None:
        return None
    
    try:
        # Rate of requests over last 5 minutes
        query = 'sum(rate(apache_accesses_total{job="apache_exporter"}[5m]))'
        
        result = prom.custom_query(query=query)
        
        if result and len(result) > 0:
            return float(result[0]['value'][1])
        return 0.0
        
    except Exception as e:
        print(f"ERROR: Failed to query request rate: {e}")
        return None


def check_apache_exporter_status() -> dict:
    """
    Checks which Apache exporters are currently up and being scraped.
    
    Returns:
        dict: {server_ip: is_up} mapping
    """
    if prom is None:
        return {}
    
    try:
        query = 'up{job="apache_exporter"}'
        
        result = prom.custom_query(query=query)
        
        status = {}
        for item in result:
            instance = item['metric'].get('instance', 'unknown')
            server_ip = instance.split(':')[0]
            is_up = int(float(item['value'][1])) == 1
            status[server_ip] = is_up
        
        return status
        
    except Exception as e:
        print(f"ERROR: Failed to check apache exporter status: {e}")
        return {}