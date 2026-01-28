import time
import os
import sys
from pprint import pprint
from datetime import datetime, timedelta, timezone
import traceback
import json
import collections 
import subprocess
import requests # Necessary for synthetic health checks

# --- Import Core Logic ---
try:
    from web_traffic_time_series_forecasting.forecast_web_traffic import get_hourly_forecast
    from data_reception import server_telemetry
    from server_power_status_management import server_power_status_management
    from web_traffic_time_series_forecasting.number_of_http_requests_per_hour import (
        get_hourly_request_count_prometheus,
        get_request_count_per_server,
        check_apache_exporter_status
    )
    from database.traffic_database_manager import insert_hourly_traffic
    from web_traffic_time_series_forecasting.daily_predictions import (
        add_prediction,
        update_actual,
        clear_old_data as clear_daily_predictions
    )
    # --- Import Alert System ---
    from alerts import (
        # Server Power State Changes
        alert_proactive_scale_up,
        alert_proactive_scale_down,
        alert_reactive_scale_up,
        alert_reactive_scale_down,
        # Server Health & Failover Events
        alert_health_check_failed,
        alert_failover_initiated,
        alert_failover_complete,
        alert_no_replacement_available,
        alert_server_blacklisted,
        alert_server_recovered,
        # ML Model & Prediction Alerts
        alert_forecast_failed,
        alert_model_retraining_started,
        alert_model_retraining_complete,
        # Connection Draining Events
        alert_draining_started,
        alert_draining_complete,
        alert_graceful_shutdown,
        # Resource Threshold Alerts
        alert_high_cpu,
        alert_high_memory,
        alert_low_utilization,
        # System Status & Telemetry Alerts
        alert_prometheus_connection_failed,
        alert_onos_connection_failed,
        alert_apache_exporter_down,
        alert_status_sync_success,
        alert_status_sync_failed,
        # Network Path Alerts
        alert_high_path_congestion,
    )
except ImportError as e:
    print(f"FATAL: Could not import a required module. Error: {e}")
    sys.exit(1)

# --- CONFIGURATION ---
CHECK_INTERVAL_SECONDS = 5
SCALING_STABILIZATION_SECONDS = 80
CONNECTION_DRAINING_SECONDS = 30 
REBOOT_WAIT_SECONDS = 15

SERVER1_IP = '192.168.126.1'
SERVER1_USER = 'huazheng'

LOCAL_TZ = timezone(timedelta(hours=8))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FORECAST_CACHE_FILE = os.path.join(BASE_DIR, 'forecast_cache.json')

# SCALING CONSTANTS
# SERVER_TIERS = { 1: range(0, 26681), 2: range(26681, 53341), 3: range(53341, 80001) }
SERVER_TIERS = { 1: range(0, 140000), 2: range(140001, 420000), 3: range(420001, 1000000) }
SCALING_MAP = { 1: "ubuntu-guest", 2: "apache-vm-1", 3: "apache-vm-2" }

# Thresholds
HIGH_CPU_THRESHOLD = 90.0 
HIGH_MEM_THRESHOLD = 90.0
LOW_CPU_THRESHOLD = 3.0 
LOW_MEM_THRESHOLD = 20.0
LOW_LOAD_DURATION_SECONDS = 30 * 60 
HIGH_LOAD_DURATION_SECONDS = 5 * 60 

# USAGE_HISTORY must now accommodate 30 minutes of data
USAGE_HISTORY = [] 
MAX_HISTORY_SIZE = int(LOW_LOAD_DURATION_SECONDS / CHECK_INTERVAL_SECONDS) + 12


ALL_SERVER_NAMES = ["ubuntu-guest", "apache-vm-1", "apache-vm-2"]
SERVER_IP_MAP = { "ubuntu-guest": "192.168.6.2", "apache-vm-1": "192.168.6.3", "apache-vm-2": "192.168.6.4" }
SERVER_CAPACITY_MAP = {
    "ubuntu-guest": {"cores": 1, "memory_gb": 1},
    "apache-vm-1": {"cores": 2, "memory_gb": 2},
    "apache-vm-2": {"cores": 4, "memory_gb": 4},
}


draining_server_ips = set()
GLOBAL_ACTIVE_IP_STATE = [] # List of IPs believed to be ON
FAILED_SERVER_IPS = set()

# Paths for synchronization playbook and JSON status file
SERVER_POWER_STATUS_DIR = os.path.join(BASE_DIR, 'server_power_status_management')
DYNAMIC_LOAD_BALANCING_DIR = os.path.join(BASE_DIR, 'dynamic_load_balancing')

STATUS_SYNC_PLAYBOOK = os.path.join(SERVER_POWER_STATUS_DIR, 'sync_server_status.yaml') 
STATUS_CACHE_FILE = os.path.join(BASE_DIR, 'local_active_servers_status.json') 
REMOTE_STATUS_FILE = os.path.join(DYNAMIC_LOAD_BALANCING_DIR, 'active_servers_status.json')


# --- HELPER FUNCTIONS ---
def determine_required_servers(predicted_traffic: int) -> int:
    for count, traffic_range in SERVER_TIERS.items():
        if predicted_traffic in traffic_range: return count
    return 3 if predicted_traffic >= SERVER_TIERS[3].start else 1

def get_active_server_ips(all_server_metrics) -> list:
    return list(all_server_metrics.keys())

def find_next_server_to_power_on(current_active_ips: list) -> str or None:
    active_names = [name for name, ip in SERVER_IP_MAP.items() if ip in current_active_ips]
    for tier in sorted(SCALING_MAP.keys()):
        server_name = SCALING_MAP[tier]
        server_ip = SERVER_IP_MAP[server_name]
        if server_name not in active_names and server_ip not in FAILED_SERVER_IPS:
            return server_name
    return None

def find_next_server_to_power_off(current_active_ips: list) -> str or None:
    eligible_to_stop_ips = [ip for ip in current_active_ips if ip not in draining_server_ips]
    if len(eligible_to_stop_ips) <= 1: return None
    eligible_names = [name for name, ip in SERVER_IP_MAP.items() if ip in eligible_to_stop_ips]
    for tier in sorted(SCALING_MAP.keys(), reverse=True):
        server_name = SCALING_MAP[tier]
        if server_name in eligible_names:
            return server_name
    return None

def get_current_average_load(all_server_metrics):
    """Calculates the average CPU/Memory usage across all stable, non-draining servers."""
    eligible_servers = [
        metrics 
        for ip, metrics in all_server_metrics.items() 
        if ip not in draining_server_ips
    ]
    
    if not eligible_servers:
        return None, None
        
    cpu_sum = sum(s['cpu'] for s in eligible_servers)
    mem_sum = sum(s['mem'] for s in eligible_servers)
    count = len(eligible_servers)
    
    return cpu_sum / count, mem_sum / count

def sync_server_status(current_active_ips: list, current_draining_ips: set, current_failed_ips: set):
    """Saves the current active/draining server list and syncs it to Server 1."""
    
    # 1. Prepare data structure: List all servers and their current status
    status_data = {}
    for name, ip in SERVER_IP_MAP.items():
        status_data[ip] = {
            "name": name,
            "ip": ip,
            "active": ip in current_active_ips,
            "draining": ip in current_draining_ips,
            "healthy": ip not in current_failed_ips
        }

    # 2. Save the data locally
    try:
        with open(STATUS_CACHE_FILE, 'w') as f:
            json.dump(status_data, f, indent=4)
    except Exception as e:
        print(f"ERROR: Could not save local status file: {e}")
        return False

    # 3. Trigger Ansible to copy the file to Server 1
    INVENTORY_PATH = os.path.join(SERVER_POWER_STATUS_DIR, 'inventory.ini')
    
    command = [
        "ansible-playbook", 
        "-i", INVENTORY_PATH, 
        STATUS_SYNC_PLAYBOOK,
        "--extra-vars", f"local_file={STATUS_CACHE_FILE} remote_file={REMOTE_STATUS_FILE}"
    ]
    
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        print("✅ Status file synced successfully to Server 1.")
        # Note: Disabled to reduce alert noise - sync happens frequently
        # alert_status_sync_success()
        return True
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else "Ansible playbook execution failed"
        print(f"[!] ERROR during Ansible sync: {error_msg}")
        alert_status_sync_failed(error_msg)
        return False
    except FileNotFoundError:
        error_msg = "Ansible command not found. Ensure Ansible is installed and in PATH."
        print(f"[!] ERROR: {error_msg}")
        alert_status_sync_failed(error_msg)
        return False

def evaluate_load_history(current_active_ips, all_server_metrics):
    """
    Evaluates historical data for both Scale-Up (5m high load) and Scale-Down (30m low load).
    
    IMPORTANT: This function uses the length of USAGE_HISTORY directly rather than
    filtering by time window, because filtering by time creates a bug where the 
    5-minute window can never accumulate more than ~60 points (old records age out
    at the same rate new ones are added).
    """
    global USAGE_HISTORY
    current_time = datetime.now(LOCAL_TZ)
    
    # 1. CONSTANTS - Points needed for each check
    required_5m_points = int(HIGH_LOAD_DURATION_SECONDS / CHECK_INTERVAL_SECONDS)   # 60 points for 5 min
    required_30m_points = int(LOW_LOAD_DURATION_SECONDS / CHECK_INTERVAL_SECONDS)   # 360 points for 30 min

    # --- Trim History (Keeps 1 hour of data) ---
    LIST_TRIM_DURATION_SECONDS = 60 * 60
    USAGE_HISTORY = [
        record for record in USAGE_HISTORY 
        if current_time - record['time'] < timedelta(seconds=LIST_TRIM_DURATION_SECONDS)
    ]
    
    # Current total history length (used for both checks)
    total_history_length = len(USAGE_HISTORY)

    # --- Check for SCALE UP (5-Minute High Load) ---
    # We need at least 60 points to evaluate 5-minute average
    if total_history_length >= required_5m_points:
        # Take the most recent 60 points
        recent_5m_records = USAGE_HISTORY[-required_5m_points:]

        cpu_5m_avgs = [record['cpu_avg'] for record in recent_5m_records if record['cpu_avg'] is not None]
        mem_5m_avgs = [record['mem_avg'] for record in recent_5m_records if record['mem_avg'] is not None]
        
        avg_cpu_over_5m = sum(cpu_5m_avgs) / len(cpu_5m_avgs) if cpu_5m_avgs else 0
        avg_mem_over_5m = sum(mem_5m_avgs) / len(mem_5m_avgs) if mem_5m_avgs else 0
        
        print("\n--- Reactive Scale Up Check (5 Min Average) ---")
        print(f"DEBUG: 5-Min Avg CPU: {avg_cpu_over_5m:.2f}% (Thresh: {HIGH_CPU_THRESHOLD}%) | "
              f"5-Min Avg MEM: {avg_mem_over_5m:.2f}% (Thresh: {HIGH_MEM_THRESHOLD}%)")
        
        if avg_cpu_over_5m > HIGH_CPU_THRESHOLD or avg_mem_over_5m > HIGH_MEM_THRESHOLD:
            print("STATUS: Scale Up Required.")
            threshold_type = "cpu" if avg_cpu_over_5m > HIGH_CPU_THRESHOLD else "memory"
            
            # Get eligible servers (not draining)
            eligible_servers = [(ip, m) for ip, m in all_server_metrics.items() if ip not in draining_server_ips]
            num_servers = len(eligible_servers)
            
            # ALERT: High resource usage detected
            if avg_cpu_over_5m > HIGH_CPU_THRESHOLD:
                if num_servers == 1:
                    ip, metrics = eligible_servers[0]
                    server_name = next((name for name, s_ip in SERVER_IP_MAP.items() if s_ip == ip), ip)
                    alert_high_cpu(metrics['cpu'], HIGH_CPU_THRESHOLD, num_servers, server_name, ip)
                else:
                    alert_high_cpu(avg_cpu_over_5m, HIGH_CPU_THRESHOLD, num_servers)
            
            if avg_mem_over_5m > HIGH_MEM_THRESHOLD:
                if num_servers == 1:
                    ip, metrics = eligible_servers[0]
                    server_name = next((name for name, s_ip in SERVER_IP_MAP.items() if s_ip == ip), ip)
                    alert_high_memory(metrics['mem'], HIGH_MEM_THRESHOLD, num_servers, server_name, ip)
                else:
                    alert_high_memory(avg_mem_over_5m, HIGH_MEM_THRESHOLD, num_servers)
            
            return ('SCALE_UP', avg_cpu_over_5m, avg_mem_over_5m, threshold_type, num_servers)
        else:
            print("STATUS: Load within acceptable range. No scale up needed.")
    else:
        print(f"INFO: Gathering load history ({total_history_length}/{required_5m_points} points needed). Skipping reactive scale up check.")

    # --- Check for SCALE DOWN (30-Minute Low Load) ---
    if len(current_active_ips) > 1:
        # We need at least 360 points to evaluate 30-minute average
        if total_history_length >= required_30m_points:
            # Take the most recent 360 points
            recent_30m_records = USAGE_HISTORY[-required_30m_points:]

            cpu_30m_avgs = [record['cpu_avg'] for record in recent_30m_records if record['cpu_avg'] is not None]
            mem_30m_avgs = [record['mem_avg'] for record in recent_30m_records if record['mem_avg'] is not None]

            avg_cpu_over_30m = sum(cpu_30m_avgs) / len(cpu_30m_avgs) if cpu_30m_avgs else 0
            avg_mem_over_30m = sum(mem_30m_avgs) / len(mem_30m_avgs) if mem_30m_avgs else 0

            print("\n--- Reactive Scale Down Check (30 Min Average) ---")
            print(f"DEBUG: 30-Min Avg CPU: {avg_cpu_over_30m:.2f}% (Low Thresh: {LOW_CPU_THRESHOLD}%) | "
                  f"30-Min Avg MEM: {avg_mem_over_30m:.2f}% (Low Thresh: {LOW_MEM_THRESHOLD}%)")

            if avg_cpu_over_30m < LOW_CPU_THRESHOLD and avg_mem_over_30m < LOW_MEM_THRESHOLD:
                print("STATUS: Scale Down Opportunity.")
                
                # Get number of active servers for alert context
                num_servers = len(current_active_ips)
                
                # ALERT: Low resource utilization detected
                alert_low_utilization(avg_cpu_over_30m, avg_mem_over_30m)
                
                return ('SCALE_DOWN', avg_cpu_over_30m, avg_mem_over_30m, None, num_servers)
            else:
                print("STATUS: Load not low enough for scale down.")
        else:
            print(f"INFO: Gathering load history ({total_history_length}/{required_30m_points} points needed). Skipping reactive scale down check.")

    return ('NO_ACTION', None, None, None, None)

def perform_synthetic_check(server_ip: str, timeout=3) -> bool:
    """Tests if a server is functional by requesting a basic endpoint (Hello Request)."""
    url = f"http://{server_ip}:80/index.html" 
    
    try:
        response = requests.get(url, timeout=timeout)
        
        if 200 <= response.status_code < 300:
            return True
        elif 500 <= response.status_code < 600:
            print(f"HEALTH CHECK FAILED for {server_ip}: Status {response.status_code}")
            return False
        else:
            return True
            
    except requests.exceptions.RequestException as e:
        print(f"HEALTH CHECK FAILED for {server_ip}: Connection Error ({e})")
        return False

def find_replacement_server(failed_ip: str, current_active_ips: list, failed_ips_blacklist: set) -> str or None:
    """
    Finds a replacement server.
    CRITICAL: Strictly filters out any server in the failed_ips_blacklist.
    """
    failed_name_list = [name for name, ip in SERVER_IP_MAP.items() if ip == failed_ip]
    if not failed_name_list: return None
    failed_name = failed_name_list[0]
        
    required_capacity = SERVER_CAPACITY_MAP[failed_name]
    required_cores = required_capacity['cores']
    required_memory = required_capacity['memory_gb']
    
    active_names = []
    for name, ip in SERVER_IP_MAP.items():
        if ip in current_active_ips: active_names.append(name)
            
    # Filter: Must not be currently active AND must not be in the FAILED set
    available_names = []
    for name in ALL_SERVER_NAMES:
        ip = SERVER_IP_MAP[name]
        
        # STRICT HEALTH CHECK: If IP is in blacklist, DO NOT consider it.
        if name not in active_names and ip not in failed_ips_blacklist:
            available_names.append(name)
    
    if not available_names:
        print("REPLACEMENT STATUS: No healthy, available servers found.")
        return None
    
    available_servers = [(name, SERVER_IP_MAP[name], SERVER_CAPACITY_MAP[name]) for name in available_names]
    available_servers.sort(key=lambda x: (x[2]['cores'], x[2]['memory_gb']))
    
    best_replacement = None
    for name, ip, capacity in available_servers:
        if capacity['cores'] == required_cores and capacity['memory_gb'] == required_memory:
            print(f"REPLACEMENT STATUS: Found exact match for {failed_name}: {name}.")
            return name
        if capacity['cores'] >= required_cores and capacity['memory_gb'] >= required_memory:
            if best_replacement is None: best_replacement = name
                
    if best_replacement:
        print(f"REPLACEMENT STATUS: Found suitable replacement: {best_replacement}.")
        return best_replacement
    print("REPLACEMENT STATUS: No available server meets the required capacity.")
    return None

# --- MAIN ORCHESTRATOR ---
def main_orchestrator():
    global draining_server_ips, USAGE_HISTORY, GLOBAL_ACTIVE_IP_STATE, FAILED_SERVER_IPS
    print("--- Initializing Single-Loop Orchestrator (Server 2: Scaling Only) ---")
    
    # --- NEW: Using Prometheus + Apache Exporter for traffic counting ---
    # No SSH initialization needed - Prometheus stores metrics centrally
    print("\n[INIT] Checking Apache Exporter status via Prometheus...")
    exporter_status = check_apache_exporter_status()
    if exporter_status:
        for ip, is_up in exporter_status.items():
            status_str = "✅ UP" if is_up else "❌ DOWN"
            print(f"    Apache Exporter on {ip}: {status_str}")
            # Alert if Apache exporter is down
            if not is_up:
                alert_apache_exporter_down(ip)
    else:
        print("⚠️ WARNING: No Apache exporters found. Traffic counting may be unavailable.")
        
    try:
        if os.path.exists(STATUS_CACHE_FILE):
            with open(STATUS_CACHE_FILE, 'r') as f:
                status_data = json.load(f)
                for ip, info in status_data.items():
                    # If "healthy" is explicitly False, assume it is failed and persist it
                    if info.get("healthy") is False:
                        print(f"[PERSISTENCE] Loaded UNHEALTHY status for {info['name']} ({ip}). Adding to blacklist.")
                        FAILED_SERVER_IPS.add(ip)
    except Exception as e:
        print(f"[Initializer] WARNING: Could not load server status file. {e}")

    forecast_data = {'value': None, 'valid_until': datetime.now(LOCAL_TZ)}

    # --- Initial load from cache ---
    try:
        if os.path.exists(FORECAST_CACHE_FILE):
            with open(FORECAST_CACHE_FILE, 'r') as f:
                cache = json.load(f)
                valid_until = datetime.fromisoformat(cache['valid_until'])
                if valid_until.tzinfo is None:
                    valid_until = valid_until.replace(tzinfo=LOCAL_TZ)
                if valid_until > datetime.now(LOCAL_TZ):
                    forecast_data['value'] = cache['value']
                    forecast_data['valid_until'] = valid_until
                    print(f"[Initializer] Loaded valid forecast from cache: {forecast_data['value']}")
    except Exception as e:
        print(f"[Initializer] WARNING: Could not read cache file. {e}")


    try:
        while True:
            current_time = datetime.now(LOCAL_TZ)
            scaling_action_taken = False
            
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"--- Running New Check @ {current_time.strftime('%Y-%m-%d %H:%M:%S')} ---")
            
            wait_time = CHECK_INTERVAL_SECONDS
            
            # 1. FORECASTING AND PROACTIVE SCALING
            if forecast_data['value'] is None or current_time >= forecast_data['valid_until']:
                
                # --- TELEMETRY FETCH FOR PROACTIVE DECISION (START) ---
                print("\n[1][MONITOR] Fetching current server status via Telemetry...")
                proactive_metrics = server_telemetry.get_all_server_metrics()
                
                if not proactive_metrics:
                    print("WARNING: Telemetry collection failed during proactive check. Skipping forecast-based scaling this cycle.")
                    time.sleep(wait_time)
                    continue
                
                # CRITICAL STEP 1: SET GLOBAL STATE BASED ON REALITY
                current_active_ips = get_active_server_ips(proactive_metrics)
                GLOBAL_ACTIVE_IP_STATE = list(current_active_ips)
                # CRITICAL STEP 2: INITIAL SYNC OF THE ACTIVE STATE TO SERVER 1
                sync_server_status(GLOBAL_ACTIVE_IP_STATE, draining_server_ips, FAILED_SERVER_IPS) 
                # --- TELEMETRY FETCH FOR PROACTIVE DECISION (END) ---
                
                # --- NEW: Query Prometheus for actual traffic from the previous hour ---
                print("[TRAFFIC] Querying Prometheus for previous hour's HTTP traffic...")
                try:
                    # Get total requests from all servers in the last hour
                    actual_traffic_last_hour = get_hourly_request_count_prometheus(lookback_hours=1)
                    
                    if actual_traffic_last_hour is not None:
                        print(f"📊 ACTUAL TRAFFIC (Previous Hour): {actual_traffic_last_hour:,} Requests.")
                        
                        # Show per-server breakdown for visibility
                        per_server_counts = get_request_count_per_server(lookback_hours=1)
                        if per_server_counts:
                            print("    Per-Server Breakdown:")
                            for ip, count in per_server_counts.items():
                                print(f"        {ip}: {count:,} requests")
                        
                        # Save hourly traffic to database for model retraining
                        # Use the start of the previous hour as timestamp
                        traffic_timestamp = (current_time - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                        try:
                            insert_hourly_traffic(traffic_timestamp, actual_traffic_last_hour)
                            print(f"    💾 Saved to database: {traffic_timestamp.strftime('%Y-%m-%d %H:%M:%S')} -> {actual_traffic_last_hour:,}")
                        except Exception as db_err:
                            print(f"    ⚠️ Failed to save traffic to database: {db_err}")
                        
                        # Update daily predictions JSON with actual traffic for previous hour
                        prev_hour_str = traffic_timestamp.strftime('%H:00')
                        try:
                            if update_actual(prev_hour_str, int(actual_traffic_last_hour)):
                                print(f"    📈 Updated daily predictions with actual for {prev_hour_str}")
                        except Exception as pred_err:
                            print(f"    ⚠️ Failed to update daily predictions: {pred_err}")
                    else:
                        print("⚠️ Failed to query traffic count from Prometheus.")
                except Exception as e:
                    print(f"⚠️ Error during traffic counting: {e}")

                print("\n" + "="*60 + "\n===> Forecast is missing or expired. Generating new forecast... <===\n" + "="*60)
                
                # Clear daily predictions if it's a new day
                try:
                    clear_daily_predictions()
                except Exception as e:
                    print(f"⚠️ Error clearing old daily predictions: {e}")
                
                time.sleep(2)
                
                try:
                    predicted_traffic = get_hourly_forecast()
                    if predicted_traffic is not None and predicted_traffic >= 0:
                        valid_until_ts = (current_time + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                        forecast_data['value'] = predicted_traffic
                        forecast_data['valid_until'] = valid_until_ts
                        with open(FORECAST_CACHE_FILE, 'w') as f: json.dump({'value': predicted_traffic, 'valid_until': valid_until_ts.isoformat()}, f)
                        
                        # Save prediction to daily predictions JSON
                        current_hour_str = current_time.replace(minute=0, second=0, microsecond=0).strftime('%H:00')
                        try:
                            add_prediction(current_hour_str, int(predicted_traffic))
                            print(f"📊 Saved prediction to daily tracker: {current_hour_str} -> {predicted_traffic:,}")
                        except Exception as pred_err:
                            print(f"⚠️ Failed to save prediction to daily tracker: {pred_err}")
                        
                        print(f"--- New forecast generated: {predicted_traffic}. Now performing proactive scaling. ---")
                        required_capacity_tier = determine_required_servers(predicted_traffic)
                        
                        # Use GLOBAL_ACTIVE_IP_STATE for scaling decision
                        required_servers_names = [SCALING_MAP[t] for t in SCALING_MAP if t <= required_capacity_tier]
                        current_active_names = [name for name, ip in SERVER_IP_MAP.items() if ip in GLOBAL_ACTIVE_IP_STATE]
                        
                        servers_to_power_on = set(required_servers_names) - set(current_active_names)
                        servers_to_power_off_initial = set(current_active_names) - set(required_servers_names)
                        servers_to_power_off = servers_to_power_off_initial - draining_server_ips
                        
                        
                        if servers_to_power_on or servers_to_power_off:
                            
                            # Proactive Scale UP
                            if servers_to_power_on:
                                print(f"--- Proactively Scaling Up (Required Tier {required_capacity_tier}) ---")
                                servers_to_power_on_sorted = sorted(list(servers_to_power_on), key=lambda s: list(SCALING_MAP.values()).index(s))

                                for server in servers_to_power_on_sorted:
                                    server_ip = SERVER_IP_MAP[server]
                                    if server_ip in FAILED_SERVER_IPS: continue
                                    if server_power_status_management.power_on_server(server):
                                        # Update GLOBAL_ACTIVE_IP_STATE immediately after ON command
                                        GLOBAL_ACTIVE_IP_STATE.append(server_ip) 
                                        scaling_action_taken = True
                                        # === ALERT: Proactive Scale-Up ===
                                        alert_proactive_scale_up(server, server_ip, predicted_traffic)
                            
                            # Proactive Scale DOWN
                            if servers_to_power_off:
                                if scaling_action_taken: time.sleep(15)
                                current_active_names = [name for name, ip in SERVER_IP_MAP.items() if ip in GLOBAL_ACTIVE_IP_STATE]
                                print(f"--- Gracefully Scaling Down {len(servers_to_power_off)} server(s) (30-second draining) ---")
                                
                                servers_to_power_off_sorted = sorted(list(servers_to_power_off), key=lambda s: list(SCALING_MAP.values()).index(s), reverse=True)
                                
                                for server_to_stop in servers_to_power_off_sorted:
                                    server_ip = SERVER_IP_MAP[server_to_stop]
                                    
                                    if len(current_active_names) - len(draining_server_ips) <= 1:
                                        print(f"WARNING: Skipping power off of {server_to_stop} as it's the last active server.")
                                        continue

                                    # CRITICAL STEP 4A: Add to Draining and Sync BEFORE wait
                                    print(f"Step 1/3: Draining connections from {server_to_stop} ({server_ip})")
                                    draining_server_ips.add(server_ip)
                                    sync_server_status(GLOBAL_ACTIVE_IP_STATE, draining_server_ips, FAILED_SERVER_IPS)
                                    
                                    # ALERT: Connection draining started
                                    alert_draining_started(server_to_stop, server_ip)
                                    
                                    print(f"Step 2/3: Waiting {CONNECTION_DRAINING_SECONDS}s...")
                                    time.sleep(CONNECTION_DRAINING_SECONDS)
                                    
                                    # ALERT: Connection draining complete
                                    alert_draining_complete(server_to_stop, server_ip)
                                    
                                    # CRITICAL STEP 4B: Power off, update GLOBAL_ACTIVE_IP_STATE, and Sync
                                    print(f"Step 3/3: Powering off {server_to_stop} and removing from draining list.")
                                    server_power_status_management.power_off_server(server_to_stop)
                                    
                                    GLOBAL_ACTIVE_IP_STATE.remove(server_ip)
                                    draining_server_ips.discard(server_ip)
                                    sync_server_status(GLOBAL_ACTIVE_IP_STATE, draining_server_ips, FAILED_SERVER_IPS)
                                    
                                    # ALERT: Graceful shutdown complete
                                    alert_graceful_shutdown(server_to_stop, server_ip)
                                    
                                    scaling_action_taken = True
                                    # === ALERT: Proactive Scale-Down ===
                                    alert_proactive_scale_down(server_to_stop, server_ip, predicted_traffic)

                            if scaling_action_taken:
                                USAGE_HISTORY = []
                                
                                # --- JUMP TO WAIT PERIOD ---
                                if servers_to_power_on:
                                    # Scale Up Wait (80s) + Final Sync
                                    print("\n--- Proactive Scaling Up Complete. Entering Stabilization Period ---")
                                    wait_time = SCALING_STABILIZATION_SECONDS 
                                    
                                    print(f"\n--- Waiting for {wait_time}s ... ---")
                                    time.sleep(wait_time)
                                    
                                    # Final synchronization after 80s stabilization
                                    sync_server_status(GLOBAL_ACTIVE_IP_STATE, draining_server_ips, FAILED_SERVER_IPS)
                                    
                                    print("\n--- Cycle complete. Resuming 5s checks. ---")
                                    continue # Jump to the next iteration

                                else:
                                    # Scale Down Wait (5s)
                                    print("\n--- Proactive Scaling Down Complete. Resuming 5s checks. ---")
                                    wait_time = CHECK_INTERVAL_SECONDS
                                    
                                    print(f"\n--- Cycle complete. Waiting for {wait_time}s ... ---")
                                    time.sleep(wait_time)
                                    
                                    continue # Jump to the next iteration
                        
                        elif not servers_to_power_on and not servers_to_power_off:
                            print(f"--- Current servers match required capacity. No proactive scaling needed. ---")
                            
                    else:
                        print("--- Forecast generation failed. Will retry on the next hour. ---")
                except Exception as e:
                    print(f"--- CRITICAL ERROR during forecast generation: {e} ---")
                    traceback.print_exc()

            # Display status
            forecast_value_str = "Not yet available"
            if forecast_data['value'] is not None:
                valid_until_str = forecast_data['valid_until'].strftime('%H:%M')
                forecast_value_str = f"{forecast_data['value']} (valid until {valid_until_str})"
            print("\n" + "="*60 + f"\nHourly Web Traffic Forecast: {forecast_value_str}\n" + "="*60)
            
            if draining_server_ips:
                print(f"\n[DRAINING STATUS]: Servers currently draining connections: {list(draining_server_ips)}")
            
            
            # 2. MONITORING AND HISTORY LOGGING (Reactive Phase)
            # --- CONSOLIDATED TELEMETRY FETCH ---
            print("\n[1][MONITOR] Fetching server telemetry...")
            all_server_metrics = server_telemetry.get_all_server_metrics()
            
            if not all_server_metrics:
                print("WARNING: Telemetry collection failed. Skipping reactive check this cycle.")
                time.sleep(wait_time)
                continue
                
            current_active_ips = get_active_server_ips(all_server_metrics)
            current_avg_cpu, current_avg_mem = get_current_average_load(all_server_metrics)
            
            # Update GLOBAL_ACTIVE_IP_STATE using live metrics (Crucial for reactive decision accuracy)
            GLOBAL_ACTIVE_IP_STATE = list(current_active_ips)
            
            # --- NEW: SYNTHETIC HEALTH CHECK & HEALING EXECUTION ---
            print("[MONITOR] Running Synthetic Health Checks...")
            servers_to_replace = [] 
            
            for ip in current_active_ips:
                if ip in draining_server_ips: continue
                if not perform_synthetic_check(ip):
                    # 1. ATTEMPT HEAL (VM REBOOT)
                    failed_name_list = [name for name, ip_map in SERVER_IP_MAP.items() if ip_map == ip]
                    if not failed_name_list:
                        print(f"CRITICAL ERROR: Could not find name for IP {ip}")
                        continue
                    failed_name = failed_name_list[0]
                    print(f"!!! CRITICAL FAILURE: Server {ip} ({failed_name}) failed synthetic check. Isolating...")
                    
                    # ALERT: Health check failed
                    alert_health_check_failed(failed_name, ip, "Synthetic HTTP check")
                    
                    # 1. ISOLATE IMMEDIATELY
                    draining_server_ips.add(ip)
                    FAILED_SERVER_IPS.add(ip) # Mark as unhealthy so it won't be re-selected
                    sync_server_status(GLOBAL_ACTIVE_IP_STATE, draining_server_ips, FAILED_SERVER_IPS)
                    
                    # ALERT: Server blacklisted
                    alert_server_blacklisted(failed_name, ip)
                    
                    print(f"[HEAL] Attempting VM Hard Reboot on {failed_name}...")

                    if server_power_status_management.restart_server(failed_name):
                         print(f"[*] VM Reboot command sent to {failed_name}. Waiting {REBOOT_WAIT_SECONDS}s for boot...")
                         time.sleep(REBOOT_WAIT_SECONDS) 
                         
                         if perform_synthetic_check(ip):
                            print(f"STATUS: Server {failed_name} HEALED successfully. Stabilizing...")
                            
                            draining_server_ips.discard(ip) # Remove from isolation
                            FAILED_SERVER_IPS.discard(ip)
                            sync_server_status(GLOBAL_ACTIVE_IP_STATE, draining_server_ips, FAILED_SERVER_IPS)
                            
                            # ALERT: Server recovered after reboot
                            alert_server_recovered(failed_name, ip)
                            
                            # 4. STABILIZE (Healed)
                            time.sleep(SCALING_STABILIZATION_SECONDS)
                            continue
                         else: print(f"STATUS: Server {failed_name} FAILED check after VM Reboot. Escalating to REPLACE.")
                    
                    # 3. TERMINATE AND REPLACE
                    servers_to_replace.append(ip)
            
            # --- EXECUTE REPLACEMENT ACTIONS ---
            if servers_to_replace:
                for failed_ip in servers_to_replace:
                    
                    # 1. POWER OFF FAILED SERVER (Reordered: Stop OLD first)
                    failed_name = [name for name, ip_map in SERVER_IP_MAP.items() if ip_map == failed_ip][0]
                    print(f"Step 1/3: Powering off failed server {failed_name} ({failed_ip})...")
                    server_power_status_management.power_off_server(failed_name)
                    
                    if failed_ip in GLOBAL_ACTIVE_IP_STATE: GLOBAL_ACTIVE_IP_STATE.remove(failed_ip)
                    draining_server_ips.discard(failed_ip)
                    sync_server_status(GLOBAL_ACTIVE_IP_STATE, draining_server_ips, FAILED_SERVER_IPS)
                    
                    # 2. FIND & POWER ON REPLACEMENT
                    # NOTE: Pass GLOBAL_ACTIVE_IP_STATE (which now excludes the failed server) 
                    # so we can find a spare from the remaining pool.
                    replacement_name = find_replacement_server(failed_ip, GLOBAL_ACTIVE_IP_STATE, FAILED_SERVER_IPS)
                    
                    if replacement_name:
                        server_ip = SERVER_IP_MAP[replacement_name]
                        print(f"Step 2/3: Powering on replacement server {replacement_name} ({server_ip})...")
                        
                        # ALERT: Failover initiated
                        alert_failover_initiated(failed_name, failed_ip, replacement_name)
                        
                        if server_power_status_management.power_on_server(replacement_name):
                            GLOBAL_ACTIVE_IP_STATE.append(server_ip)
                            if server_ip in FAILED_SERVER_IPS: FAILED_SERVER_IPS.discard(server_ip)
                            sync_server_status(GLOBAL_ACTIVE_IP_STATE, draining_server_ips, FAILED_SERVER_IPS)
                            print(f"STATUS: Replacement {replacement_name} activated successfully.")
                            
                            # ALERT: Failover complete
                            alert_failover_complete(failed_name, replacement_name, server_ip)
                    else: 
                        print(f"STATUS: No spare capacity available to replace {failed_ip}.")
                        
                        # ALERT: No replacement available
                        alert_no_replacement_available(failed_name, failed_ip)
                    
                    # 3. STABILIZATION
                    USAGE_HISTORY = []
                    wait_time = SCALING_STABILIZATION_SECONDS
                    print(f"\n--- Failure Handling Complete. Waiting for {wait_time}s stabilization. ---")
                    time.sleep(wait_time)
                    continue


            if current_avg_cpu is not None:
                 USAGE_HISTORY.append({
                     'time': current_time, 
                     'cpu_avg': current_avg_cpu, 
                     'mem_avg': current_avg_mem
                 })
                 
            if len(USAGE_HISTORY) > MAX_HISTORY_SIZE:
                 USAGE_HISTORY.pop(0)

            eligible_server_ips = [ip for ip in all_server_metrics.keys() if ip not in draining_server_ips]
            
            if eligible_server_ips:
                print(f"Active servers for external load balancer: {eligible_server_ips}")
                print("\n[2][DECIDE-LB] Load balancing is handled externally by Server 1 (DWRS). Skipping load balancing decision.")

            # 3. REACTIVE SCALING (Python History Check)
            print("\n[3][CHECK-SCALE] Evaluating system load for reactive scaling (Python history check)...")
            
            scale_result = evaluate_load_history(current_active_ips, all_server_metrics)
            scale_action, scale_avg_cpu, scale_avg_mem, threshold_type, num_servers = scale_result
            
            if scale_action == 'SCALE_UP':
                print("\n[4][ACT-SCALE] ALERT: System load exceeds 5-minute sustained threshold! Triggering reactive scale up.")
                
                server_to_power_on = find_next_server_to_power_on(current_active_ips) # Use fresh IP list
                
                if server_to_power_on:
                    server_ip = SERVER_IP_MAP[server_to_power_on]
                    if server_power_status_management.power_on_server(server_to_power_on):
                        # Update global state immediately
                        GLOBAL_ACTIVE_IP_STATE.append(server_ip)
                        
                        # === ALERT: Reactive Scale-Up ===
                        alert_reactive_scale_up(server_to_power_on, server_ip, scale_avg_cpu, scale_avg_mem, threshold_type, HIGH_CPU_THRESHOLD, HIGH_MEM_THRESHOLD, num_servers)
                        
                        USAGE_HISTORY = []
                        # JUMP TO WAIT PERIOD
                        print("\n--- Reactive Scaling Up Complete. Entering Stabilization Period ---")
                        wait_time = SCALING_STABILIZATION_SECONDS 
                        
                        print(f"\n--- Waiting for {wait_time}s ... ---")
                        time.sleep(wait_time)
                        
                        # Final synchronization AFTER 80s stabilization
                        sync_server_status(GLOBAL_ACTIVE_IP_STATE, draining_server_ips, FAILED_SERVER_IPS)
                        
                        print("\n--- Cycle complete. Resuming 5s checks. ---")
                        continue
                else:
                    print("WARNING: Cannot scale up - all available servers are already active.")
                    
            elif scale_action == 'SCALE_DOWN':
                # --- EXECUTE REACTIVE SCALE DOWN ---
                print("\n[4][ACT-SCALE] ALERT: System load is below 30-minute sustained threshold! Triggering reactive scale down.")
                
                server_to_stop = find_next_server_to_power_off(current_active_ips) # Use fresh IP list
                
                if server_to_stop:
                    server_ip = SERVER_IP_MAP[server_to_stop]
                    
                    # 1. Add to Draining and Sync BEFORE wait
                    print(f"Step 1/3: Draining connections from {server_to_stop} ({server_ip})")
                    draining_server_ips.add(server_ip)
                    sync_server_status(GLOBAL_ACTIVE_IP_STATE, draining_server_ips, FAILED_SERVER_IPS)
                    
                    # ALERT: Connection draining started
                    alert_draining_started(server_to_stop, server_ip)
                    
                    print(f"Step 2/3: Waiting {CONNECTION_DRAINING_SECONDS}s...")
                    time.sleep(CONNECTION_DRAINING_SECONDS)
                    
                    # ALERT: Connection draining complete
                    alert_draining_complete(server_to_stop, server_ip)
                    
                    # 2. Power off, update GLOBAL_ACTIVE_IP_STATE, and Sync
                    print(f"Step 3/3: Powering off {server_to_stop} and removing from draining list.")
                    server_power_status_management.power_off_server(server_to_stop)
                    
                    GLOBAL_ACTIVE_IP_STATE.remove(server_ip)
                    draining_server_ips.discard(server_ip)
                    sync_server_status(GLOBAL_ACTIVE_IP_STATE, draining_server_ips, FAILED_SERVER_IPS)
                    
                    # ALERT: Graceful shutdown complete
                    alert_graceful_shutdown(server_to_stop, server_ip)
                    
                    # === ALERT: Reactive Scale-Down ===
                    alert_reactive_scale_down(server_to_stop, server_ip, scale_avg_cpu, scale_avg_mem, LOW_CPU_THRESHOLD, LOW_MEM_THRESHOLD, num_servers)
                    
                    USAGE_HISTORY = []
                else:
                    print("WARNING: Only one active server remains. Reactive scale down aborted.")
            
            else: # NO_ACTION
                print("\n[4][ACT-SCALE] OK: System load is within sustained thresholds.")

            wait_time = CHECK_INTERVAL_SECONDS
            
            print(f"\n--- Cycle complete. Waiting for {wait_time}s... ---")
            time.sleep(wait_time)
            
    except KeyboardInterrupt:
        print("\nShutting down.")


if __name__ == "__main__":
    # Wrap the entire execution in a try-except block
    try:
        main_orchestrator()
    except KeyboardInterrupt:
        print("\nShutting down.")