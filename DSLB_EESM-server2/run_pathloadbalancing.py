from flask import Flask, request, jsonify
import threading
import time
import sys
import json
import subprocess
import os
from datetime import datetime, timezone, timedelta
from data_reception.network_telemetry import get_onos_port_stats
from dynamic_load_balancing.link_load_balancing import (
    LinkLoadBalancer,
    AVAILABLE_PATHS,
    DEVICE_IDS
)

# Import TCN prediction functions
from predict_network_link_bandwidth_usage.TCN import (
    initialize_prediction_system,
    update_path_history,
    predict_path_costs_for_route,
    compute_ratios_from_predictions,
    update_history_from_telemetry,
    get_all_route_predictions,
    print_prediction_summary,
    load_history_from_json,
    get_loaded_history_count,
    ROUTE_TO_PATH_MODELS
)

# Import path bandwidth database manager for storing actual bandwidth usage
try:
    from database.path_bandwidth_database_manager import (
        insert_path_bandwidth,
        initialize_database as init_path_db
    )
    PATH_DB_AVAILABLE = True
    # Initialize database on import
    init_path_db()
except ImportError as e:
    print(f"⚠️ Path bandwidth database not available: {e}")
    PATH_DB_AVAILABLE = False

# ==============================================================================
# ===                           CONFIGURATION                            ===
# ==============================================================================

COLLECTION_INTERVAL = 60  # Collect cumulative stats over 60 seconds
API_HOST = "0.0.0.0"
API_PORT = 5000

# Mode selection: "prediction" uses TCN models, "realtime" uses live telemetry
# Options: "prediction", "realtime", "hybrid"
# - "prediction": Pure TCN model predictions (may be inaccurate without proper training data)
# - "realtime": Pure real-time telemetry measurements
# - "hybrid": Weighted average of TCN prediction and recent actual (recommended when models aren't trained on your data)
LOAD_BALANCING_MODE = "prediction"  # Changed from "prediction" to "hybrid" for better accuracy

# Hybrid mode weight: How much to trust TCN predictions vs recent actual measurements
# 0.0 = 100% actual (same as realtime), 1.0 = 100% prediction, 0.3 = 30% prediction + 70% actual
HYBRID_PREDICTION_WEIGHT = 0.3  # Recommended: 0.2-0.4 until models are trained on your data

# Minimum iterations to collect before using predictions (for history buffer)
MIN_HISTORY_ITERATIONS = 10

# UTC+8 timezone for timestamps
UTC_PLUS_8 = timezone(timedelta(hours=8))

# File paths
LOCAL_FILE = "/home/huazheng/DSLB_EESM/dynamic_load_balancing/onos_path_selection.json"
ANSIBLE_PLAYBOOK = "/home/huazheng/DSLB_EESM/dynamic_load_balancing/sync_to_onos_docker_server1.yml"
ANSIBLE_INVENTORY = "/home/huazheng/DSLB_EESM/dynamic_load_balancing/inventory.ini"

# Remote Server 1 details (for reference/logging)
REMOTE_HOST = "192.168.126.1"
REMOTE_CONTAINER = "onos"
REMOTE_CONTAINER_PATH = "/root/onos/apache-karaf-4.2.9/data/onos_path_selection.json"

# Path bandwidth history file for UI sparklines display
PATH_BANDWIDTH_HISTORY_FILE = "/home/huazheng/DSLB_EESM/predict_network_link_bandwidth_usage/path_bandwidth_history.json"
MAX_HISTORY_ENTRIES = 15  # Keep last 15 minutes of data

# Global state
load_balancer = LinkLoadBalancer()
cumulative_usage = {}
stats_lock = threading.Lock()
running = True

# Statistics
push_stats = {
    'total_pushes': 0,
    'successful_pushes': 0,
    'failed_pushes': 0,
    'last_push_time': None,
    'last_error': None
}
stats_lock_push = threading.Lock()

# ==============================================================================
# ===                        HELPER FUNCTIONS                             ===
# ==============================================================================

def get_spine_name(src, dst, path_index):
    """Determine which spine switch a path uses"""
    paths = AVAILABLE_PATHS.get((src, dst), [])
    if int(path_index) < len(paths):
        path_hops = paths[int(path_index)]
        # Check the second hop (spine switch)
        for device_id, port in path_hops:
            if device_id == DEVICE_IDS.get("spine1"):
                return "spine1"
            elif device_id == DEVICE_IDS.get("spine2"):
                return "spine2"
    return "unknown"


def save_next_predictions(timestamp_str, iteration):
    """
    Save predicted bandwidth values for the next iteration BEFORE actual values are computed.
    These predictions will have actual_mb: null until they are updated.
    
    IMPORTANT: Predictions are ONLY saved when iteration >= MIN_HISTORY_ITERATIONS (10).
    Before that, next_predictions will be null since TCN models need sufficient history.
    
    Args:
        timestamp_str: Timestamp string for this prediction
        iteration: Current iteration number
    """
    try:
        # Read existing history
        history_data = {
            "last_updated": None,
            "iteration": None,
            "using_predictions": False,
            "history_window_minutes": 15,
            "max_entries": MAX_HISTORY_ENTRIES,
            "paths": [
                "leaf1-spine1-leaf2", "leaf1-spine2-leaf2",
                "leaf1-spine1-leaf3", "leaf1-spine2-leaf3",
                "leaf1-spine1-leaf6", "leaf1-spine2-leaf6",
                "leaf2-spine1-leaf3", "leaf2-spine2-leaf3",
                "leaf2-spine1-leaf6", "leaf2-spine2-leaf6",
                "leaf3-spine1-leaf6", "leaf3-spine2-leaf6"
            ],
            "next_predictions": None,
            "history": []
        }
        
        if os.path.exists(PATH_BANDWIDTH_HISTORY_FILE):
            try:
                with open(PATH_BANDWIDTH_HISTORY_FILE, 'r') as f:
                    history_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        
        # Determine if we're using predictions - ONLY after MIN_HISTORY_ITERATIONS
        use_predictions = (LOAD_BALANCING_MODE == "prediction" and iteration >= MIN_HISTORY_ITERATIONS)
        use_hybrid = (LOAD_BALANCING_MODE == "hybrid" and iteration >= MIN_HISTORY_ITERATIONS)
        
        # Update metadata
        history_data["last_updated"] = timestamp_str
        history_data["iteration"] = iteration
        history_data["using_predictions"] = use_predictions or use_hybrid
        
        # Ensure history field exists
        if "history" not in history_data:
            history_data["history"] = []
        
        # Only save next_predictions if we have sufficient history for TCN models
        if iteration >= MIN_HISTORY_ITERATIONS:
            # Build next_predictions entry
            # next_predictions shows predictions for the CURRENT minute that is just starting
            # These predictions will be verified when actual values are computed at the end of this minute
            time_only = timestamp_str.split(' ')[1][:5] if ' ' in timestamp_str else timestamp_str[:5]
            
            next_predictions = {
                "timestamp": timestamp_str,
                "time": time_only,
                "iteration": iteration,
                "mode": "hybrid" if use_hybrid else ("prediction" if use_predictions else "realtime"),
                "paths": {}
            }
            
            # Get predictions for each route using TCN models
            for (src, dst) in AVAILABLE_PATHS.keys():
                if src.startswith("spine") or dst.startswith("spine") or src == dst:
                    continue
                
                if (src, dst) in ROUTE_TO_PATH_MODELS:
                    # Get predicted costs from TCN
                    predicted_costs = predict_path_costs_for_route(src, dst)
                    
                    for path_idx, cost_bytes in (predicted_costs or {}).items():
                        spine = get_spine_name(src, dst, path_idx)
                        
                        if src < dst:
                            path_name = f"{src}-{spine}-{dst}"
                        else:
                            path_name = f"{dst}-{spine}-{src}"
                        
                        if path_name not in next_predictions["paths"]:
                            predicted_mb = cost_bytes / (1024 * 1024)
                            # Only store predicted_mb - no actual_mb needed for next_predictions
                            next_predictions["paths"][path_name] = {
                                "predicted_mb": round(predicted_mb, 2)
                            }
            
            # Save next_predictions
            history_data["next_predictions"] = next_predictions
            print(f"[History] ✓ Saved next predictions for {len(next_predictions['paths'])} paths (actual pending)")
        else:
            # Before MIN_HISTORY_ITERATIONS, set next_predictions to null
            history_data["next_predictions"] = None
            print(f"[History] ℹ Iteration {iteration}/{MIN_HISTORY_ITERATIONS}: Collecting history data (no predictions yet)")
        
        with open(PATH_BANDWIDTH_HISTORY_FILE, 'w') as f:
            json.dump(history_data, f, indent=2)
        
    except Exception as e:
        print(f"[History] ⚠ Error saving next predictions: {e}")


def save_path_bandwidth_history(timestamp_str, all_weights, actual_usage):
    """
    Save predicted vs actual path bandwidth to history file for UI display.
    
    IMPORTANT: The predicted_mb values come from next_predictions (which were saved
    in the previous iteration for this minute), NOT from all_weights (which contains
    predictions for the NEXT minute).
    
    Flow:
    - At minute N, we call save_next_predictions() which saves predictions for minute N
    - At minute N+1, we call this function with timestamp_str = minute N
    - The next_predictions in the file contains predictions for minute N (saved last iteration)
    - We use those predictions + the actual values just computed for the history entry
    
    Args:
        timestamp_str: Timestamp string in format 'YYYY-MM-DD HH:MM:SS' (the minute we're saving data for)
        all_weights: Dict with route weights (NOT used for predicted_mb anymore)
        actual_usage: Dict with actual bandwidth usage from telemetry
    """
    try:
        # Read existing history
        history_data = {
            "last_updated": None,
            "iteration": None,
            "using_predictions": False,
            "history_window_minutes": 15,
            "max_entries": MAX_HISTORY_ENTRIES,
            "paths": [
                "leaf1-spine1-leaf2", "leaf1-spine2-leaf2",
                "leaf1-spine1-leaf3", "leaf1-spine2-leaf3",
                "leaf1-spine1-leaf6", "leaf1-spine2-leaf6",
                "leaf2-spine1-leaf3", "leaf2-spine2-leaf3",
                "leaf2-spine1-leaf6", "leaf2-spine2-leaf6",
                "leaf3-spine1-leaf6", "leaf3-spine2-leaf6"
            ],
            "next_predictions": None,
            "history": []
        }
        
        if os.path.exists(PATH_BANDWIDTH_HISTORY_FILE):
            try:
                with open(PATH_BANDWIDTH_HISTORY_FILE, 'r') as f:
                    history_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        
        # Build new entry
        time_only = timestamp_str.split(' ')[1][:5] if ' ' in timestamp_str else timestamp_str[:5]
        
        new_entry = {
            "timestamp": timestamp_str,
            "time": time_only,
            "paths": {}
        }
        
        # Compute actual bandwidth for each path from usage data
        id_to_name = {v: k for k, v in DEVICE_IDS.items()}
        actual_path_bandwidth = {}
        
        for (src, dst), paths in AVAILABLE_PATHS.items():
            if src.startswith("spine") or dst.startswith("spine") or src == dst:
                continue
            
            for path_idx, path_hops in enumerate(paths):
                spine_name = None
                for device_id, port in path_hops:
                    name = id_to_name.get(device_id, "")
                    if name.startswith("spine"):
                        spine_name = name
                        break
                
                if not spine_name:
                    continue
                
                # Canonical path name (smaller leaf first)
                if src < dst:
                    path_name = f"{src}-{spine_name}-{dst}"
                else:
                    path_name = f"{dst}-{spine_name}-{src}"
                
                if path_name in actual_path_bandwidth:
                    continue
                
                # Sum bandwidth from all hops
                total_bw = 0
                for device_id, port in path_hops:
                    port_str = str(port)
                    if device_id in actual_usage and port_str in actual_usage[device_id]:
                        total_bw += actual_usage[device_id][port_str].get('total_bytes', 0)
                
                actual_path_bandwidth[path_name] = total_bw / (1024 * 1024)  # Convert to MB
        
        # Get current iteration to determine if we should include predicted_mb
        current_iteration = history_data.get("iteration", 0)
        use_predictions = current_iteration >= MIN_HISTORY_ITERATIONS
        
        # Get predictions from next_predictions (saved in PREVIOUS iteration for THIS minute)
        # These are the predictions that were made at the start of this minute
        prev_predictions = {}
        next_pred = history_data.get("next_predictions")
        if next_pred and next_pred.get("timestamp") == timestamp_str:
            # next_predictions matches the minute we're saving - use these predictions
            prev_predictions = next_pred.get("paths", {})
            print(f"[History] ✓ Found matching predictions from previous iteration for {timestamp_str}")
        elif next_pred:
            # next_predictions exists but for different timestamp - shouldn't happen normally
            print(f"[History] ⚠ next_predictions timestamp mismatch: expected {timestamp_str}, found {next_pred.get('timestamp')}")
        
        # Build history entry using predictions from next_predictions (not all_weights)
        for path_name in history_data.get("paths", []):
            actual_mb = actual_path_bandwidth.get(path_name, None)
            
            if use_predictions:
                # Get predicted_mb from previous iteration's next_predictions
                prev_pred_data = prev_predictions.get(path_name, {})
                predicted_mb = prev_pred_data.get("predicted_mb")
                
                new_entry["paths"][path_name] = {
                    "predicted_mb": predicted_mb,  # From previous iteration's predictions
                    "actual_mb": round(actual_mb, 2) if actual_mb is not None else None,
                    "source": "prediction" if predicted_mb is not None else "realtime"
                }
            else:
                # Realtime mode (iterations 1-9): only store actual_mb
                new_entry["paths"][path_name] = {
                    "actual_mb": round(actual_mb, 2) if actual_mb is not None else None,
                    "source": "realtime"
                }
        
        # Add new entry to history
        history_data["history"].append(new_entry)
        history_data["last_updated"] = timestamp_str
        
        # Trim to max entries
        if len(history_data["history"]) > MAX_HISTORY_ENTRIES:
            history_data["history"] = history_data["history"][-MAX_HISTORY_ENTRIES:]
        
        # Save to file
        with open(PATH_BANDWIDTH_HISTORY_FILE, 'w') as f:
            json.dump(history_data, f, indent=2)
        
        print(f"[History] ✓ Saved path bandwidth history ({len(new_entry['paths'])} paths)")
        
    except Exception as e:
        print(f"[History] ⚠ Error saving path bandwidth history: {e}")


def compute_and_save_path_bandwidth(usage, timestamp):
    """
    Computes bandwidth usage for all 12 paths and saves to database.
    
    This function calculates the bandwidth for each path based on the
    port statistics and saves to the SQLite database for TCN model training.
    
    Args:
        usage: Dictionary of device -> port -> {tx_bytes, rx_bytes, total_bytes}
        timestamp: datetime object for this measurement
    
    Returns:
        dict: Path bandwidth values that were saved
    """
    if not PATH_DB_AVAILABLE:
        return {}
    
    # Mapping from path name to the (device, port) pairs that constitute the path
    # Each path goes through a leaf switch and a spine switch
    # We measure the bandwidth at the leaf switch's uplink port to the spine
    
    # Device ID to name mapping (reverse of DEVICE_IDS)
    id_to_name = {v: k for k, v in DEVICE_IDS.items()}
    
    path_bandwidth = {}
    
    # Compute bandwidth for each of the 12 paths
    for (src, dst) in AVAILABLE_PATHS.keys():
        if src.startswith("spine") or dst.startswith("spine") or src == dst:
            continue
        
        paths = AVAILABLE_PATHS.get((src, dst), [])
        
        for path_idx, path_hops in enumerate(paths):
            # Determine spine switch for this path
            spine_name = None
            for device_id, port in path_hops:
                name = id_to_name.get(device_id, "")
                if name.startswith("spine"):
                    spine_name = name
                    break
            
            if not spine_name:
                continue
            
            # Path name format: leaf{src}_spine{N}_leaf{dst}
            # Only process unique paths (src < dst to avoid duplicates)
            if src < dst:
                path_name = f"{src}_{spine_name}_{dst}"
            else:
                path_name = f"{dst}_{spine_name}_{src}"
            
            # Skip if we've already computed this path
            if path_name in path_bandwidth:
                continue
            
            # Sum up the bandwidth from all hops in the path
            total_bandwidth = 0
            for device_id, port in path_hops:
                device_name = id_to_name.get(device_id, "")
                if device_name in usage and port in usage[device_name]:
                    total_bandwidth += usage[device_name][port].get('total_bytes', 0)
            
            path_bandwidth[path_name] = total_bandwidth
    
    # Save to database
    if path_bandwidth:
        try:
            success = insert_path_bandwidth(timestamp, path_bandwidth)
            if success:
                print(f"[DB] ✓ Saved path bandwidth to database: {len(path_bandwidth)} paths")
            else:
                print(f"[DB] ⚠ Failed to save path bandwidth to database")
        except Exception as e:
            print(f"[DB] ⚠ Error saving path bandwidth: {e}")
    
    return path_bandwidth


# ==============================================================================
# ===            CUMULATIVE BANDWIDTH COLLECTION THREAD                   ===
# ==============================================================================

def wait_until_next_minute():
    """
    Wait until the start of the next minute boundary.
    Returns the target minute's timestamp string (for the minute that just started).
    
    For example, if called at 20:43:45, it waits until 20:44:00 and returns '20:44'.
    """
    now = datetime.now(UTC_PLUS_8)
    # Calculate seconds until next minute
    seconds_to_wait = 60 - now.second - (now.microsecond / 1_000_000)
    
    if seconds_to_wait > 0:
        print(f"[Timing] Waiting {seconds_to_wait:.1f}s until next minute boundary...")
        time.sleep(seconds_to_wait)
    
    # Get the timestamp at the minute boundary
    target_time = datetime.now(UTC_PLUS_8)
    return target_time.strftime('%Y-%m-%d %H:%M:%S'), target_time.strftime('%H:%M')


def calculate_cumulative_usage(start_stats, end_stats):
    """Calculate total bandwidth usage over the interval."""
    usage = {}
    
    for device in end_stats:
        if device not in start_stats:
            continue
        
        usage[device] = {}
        
        for port in end_stats[device]:
            if port not in start_stats[device]:
                continue
            
            start_port = start_stats[device][port]
            end_port = end_stats[device][port]
            
            tx_bytes = end_port.get('bytesSent', 0) - start_port.get('bytesSent', 0)
            rx_bytes = end_port.get('bytesReceived', 0) - start_port.get('bytesReceived', 0)
            
            # Handle counter rollover
            if tx_bytes < 0:
                tx_bytes = end_port.get('bytesSent', 0)
            if rx_bytes < 0:
                rx_bytes = end_port.get('bytesReceived', 0)
            
            usage[device][port] = {
                'tx_bytes': tx_bytes,
                'rx_bytes': rx_bytes,
                'total_bytes': tx_bytes + rx_bytes
            }
    
    return usage

def telemetry_and_push_worker():
    """Background thread that collects stats and writes weights to file.
    
    Uses minute-aligned snapshots for consistent timestamps:
    - Waits until the start of the next minute to capture first snapshot
    - Captures second snapshot at the start of the following minute
    - This ensures timestamps are always aligned to minute boundaries
      regardless of processing time for ansible, predictions, etc.
    """
    global cumulative_usage, running
    
    print("\n[Telemetry] Worker started - Ansible-based distribution mode")
    print("[Telemetry] Using minute-aligned snapshots for consistent timestamps")
    
    # Load iteration count and history from JSON file if available
    # This allows predictions to resume immediately after restart
    print("\n[Telemetry] Checking for saved history from previous session...")
    saved_iteration = load_history_from_json()
    loaded_history_count = get_loaded_history_count()
    
    if saved_iteration > 0 and loaded_history_count >= MIN_HISTORY_ITERATIONS:
        # We have sufficient history - continue from saved iteration
        iteration = saved_iteration
        print(f"[Telemetry] ✓ Resuming from iteration {iteration} with {loaded_history_count} history entries")
        print(f"[Telemetry] ✓ Predictions will be active immediately!")
    elif saved_iteration > 0:
        # We have some history but not enough - continue from saved iteration
        iteration = saved_iteration
        needed = MIN_HISTORY_ITERATIONS - loaded_history_count
        print(f"[Telemetry] ⚠ Resuming from iteration {iteration} with {loaded_history_count} history entries")
        print(f"[Telemetry] ⚠ Need {needed} more iterations before predictions start")
    else:
        # No history file or empty - start fresh
        iteration = 0
        print(f"[Telemetry] Starting fresh (no valid history found)")
    
    time.sleep(5)
    
    # Initialize: wait for first minute boundary and get initial snapshot
    print("\n[Telemetry] Waiting for first minute boundary to start...")
    prev_timestamp_full, prev_timestamp = wait_until_next_minute()
    
    print(f"\n[Collection] Capturing initial snapshot at minute {prev_timestamp}...")
    prev_stats = get_onos_port_stats()
    if not prev_stats:
        print("[Collection] ⚠ Failed to get initial stats, will retry...")
    else:
        print(f"[Collection] ✓ Initial snapshot captured from {len(prev_stats)} devices")
    
    while running:
        try:
            iteration += 1
            start_time = time.time()
            
            print(f"\n{'='*70}")
            print(f"[Collection] Iteration {iteration} - Waiting for next minute boundary...")
            print(f"{'='*70}")
            
            # Step 1: Wait until the next minute boundary
            current_timestamp_full, current_timestamp = wait_until_next_minute()
            
            # The data we're about to compute represents traffic during the PREVIOUS minute
            # So we use prev_timestamp for labeling the data
            data_minute_full = prev_timestamp_full  # e.g., "2026-01-01 22:30:00"
            data_minute = prev_timestamp            # e.g., "22:30"
            
            print(f"\n[Collection] Iteration {iteration} - Processing data for minute {data_minute}")
            print(f"  Data Period: {data_minute_full} to {current_timestamp_full}")
            print(f"  Collection Method: snapshot-based (1 minute)")
            print(f"{'='*70}")
            
            # Step 2: Get current snapshot at this minute boundary
            print("\n[Collection] Step 1/6: Capturing current port statistics...")
            current_stats = get_onos_port_stats()
            
            if not current_stats:
                print("[Collection] ⚠ Failed to get current stats, will retry next minute")
                # Update previous timestamp for next iteration
                prev_timestamp_full = current_timestamp_full
                prev_timestamp = current_timestamp
                continue
            
            print(f"[Collection] ✓ Current snapshot captured from {len(current_stats)} devices")
            
            # If we don't have previous stats, save current and continue
            if not prev_stats:
                print("[Collection] ⚠ No previous snapshot, saving current and waiting for next minute")
                prev_stats = current_stats
                prev_timestamp_full = current_timestamp_full
                prev_timestamp = current_timestamp
                continue
            
            # NOTE: save_next_predictions is called AFTER save_path_bandwidth_history
            # This ensures that save_path_bandwidth_history can use the previous iteration's
            # next_predictions (which contain predictions for data_minute) before they get overwritten
            
            # Step 3: Calculate usage as difference between snapshots
            # This represents bandwidth during the PREVIOUS minute (data_minute)
            print(f"\n[Collection] Step 2/6: Calculating bandwidth for minute {data_minute}...")
            usage = calculate_cumulative_usage(prev_stats, current_stats)
            
            # Save current stats and timestamp as previous for next iteration
            prev_stats = current_stats
            prev_timestamp_full = current_timestamp_full
            prev_timestamp = current_timestamp
            
            if not usage:
                print("[Collection] ⚠ Failed to calculate usage")
                continue
            
            print(f"[Collection] ✓ Usage calculated from {len(usage)} devices")
            
            with stats_lock:
                cumulative_usage = usage
            
            # Calculate total network traffic
            total_network_bytes = sum(
                sum(port_data['total_bytes'] for port_data in ports.values())
                for ports in usage.values()
            )
            total_network_mb = total_network_bytes / (1024 * 1024)
            
            print(f"[Collection] ✓ Cumulative usage calculated")
            print(f"[Collection] Total Network Traffic: {total_network_mb:.2f} MB")
            
            if total_network_mb == 0:
                print(f"[Collection] ⚠ WARNING: No traffic detected!")
                print(f"[Collection]   All path costs will be zero.")
                print(f"[Collection]   Generate traffic during the next minute window.")
            
            # Save path bandwidth to database for TCN model training
            print(f"\n[Collection] Step 3/6: Saving path bandwidth to database...")
            measurement_timestamp = datetime.now(UTC_PLUS_8)
            path_bw_saved = compute_and_save_path_bandwidth(usage, measurement_timestamp)
            if path_bw_saved:
                print(f"[Collection] ✓ Saved {len(path_bw_saved)} path bandwidth measurements")
            
            # Update TCN prediction history with current telemetry data
            print(f"\n[Collection] Step 4/6: Updating prediction history buffer...")
            update_history_from_telemetry(usage, AVAILABLE_PATHS, DEVICE_IDS)
            print(f"[Collection] ✓ Prediction history updated with current telemetry")
            
            # Step 5: Compute path weights grouped by src->dst
            print(f"\n[Collection] Step 5/6: Computing path weights (grouped by route)...")
            print(f"[Collection] Mode: {LOAD_BALANCING_MODE.upper()}")
            
            all_weights = {}
            groups_processed = 0
            
            # Determine mode based on configuration and iteration count
            use_predictions = (LOAD_BALANCING_MODE == "prediction" and iteration >= MIN_HISTORY_ITERATIONS)
            use_hybrid = (LOAD_BALANCING_MODE == "hybrid" and iteration >= MIN_HISTORY_ITERATIONS)
            
            if LOAD_BALANCING_MODE in ["prediction", "hybrid"] and iteration < MIN_HISTORY_ITERATIONS:
                print(f"[Collection] ⚠ Building history buffer: iteration {iteration}/{MIN_HISTORY_ITERATIONS}")
                print(f"[Collection]   Using real-time data until history is sufficient")
            
            if use_predictions:
                print(f"[Collection] Using TCN PREDICTED bandwidth for ratio computation")
            elif use_hybrid:
                print(f"[Collection] Using HYBRID mode: {HYBRID_PREDICTION_WEIGHT*100:.0f}% TCN + {(1-HYBRID_PREDICTION_WEIGHT)*100:.0f}% Actual")
            else:
                print(f"[Collection] Using REAL-TIME bandwidth measurements")
            
            # Group paths by (src, dst)
            for (src, dst) in AVAILABLE_PATHS.keys():
                # Skip spine-to-spine or same device
                if src.startswith("spine") or dst.startswith("spine") or src == dst:
                    continue
                
                route_key = f"{src}->{dst}"
                
                # Always compute real-time costs first (needed for hybrid mode)
                realtime_costs = load_balancer.compute_path_costs_cumulative(usage, src, dst)
                
                if use_predictions and (src, dst) in ROUTE_TO_PATH_MODELS:
                    # === USE PURE TCN PREDICTIONS ===
                    predicted_costs = predict_path_costs_for_route(src, dst)
                    
                    if not predicted_costs:
                        print(f"  ⚠ Route {route_key}: No predictions available, using real-time")
                        path_costs = realtime_costs
                        path_ratios = load_balancer.compute_path_ratios_from_costs(path_costs) if path_costs else {}
                        data_source = "realtime"
                    else:
                        path_costs = predicted_costs
                        path_ratios = compute_ratios_from_predictions(predicted_costs)
                        data_source = "prediction"
                        
                elif use_hybrid and (src, dst) in ROUTE_TO_PATH_MODELS:
                    # === USE HYBRID MODE: Blend TCN predictions with actual measurements ===
                    predicted_costs = predict_path_costs_for_route(src, dst)
                    
                    if not predicted_costs or not realtime_costs:
                        print(f"  ⚠ Route {route_key}: Missing data, using real-time only")
                        path_costs = realtime_costs if realtime_costs else {}
                        path_ratios = load_balancer.compute_path_ratios_from_costs(path_costs) if path_costs else {}
                        data_source = "realtime"
                    else:
                        # Blend predicted and actual costs
                        path_costs = {}
                        for path_idx in predicted_costs.keys():
                            pred_val = predicted_costs.get(path_idx, 0)
                            actual_val = realtime_costs.get(path_idx, 0)
                            # Weighted average: hybrid = weight * predicted + (1-weight) * actual
                            hybrid_val = (HYBRID_PREDICTION_WEIGHT * pred_val) + ((1 - HYBRID_PREDICTION_WEIGHT) * actual_val)
                            path_costs[path_idx] = hybrid_val
                        
                        path_ratios = compute_ratios_from_predictions(path_costs)
                        data_source = "hybrid"
                        
                else:
                    # === USE REAL-TIME MEASUREMENTS ===
                    # Compute costs for all paths in this route
                    path_costs = load_balancer.compute_path_costs_cumulative(usage, src, dst)
                    data_source = "realtime"
                    
                    if not path_costs:
                        print(f"  ⚠ Route {route_key}: No costs computed (path definition issue?)")
                        continue
                    
                    # Compute ratios based on inverse costs
                    path_ratios = load_balancer.compute_path_ratios_from_costs(path_costs)
                
                if path_ratios:
                    all_weights[route_key] = {
                        "ratios": {str(k): v for k, v in path_ratios.items()},
                        "costs": {str(k): v for k, v in path_costs.items()},
                        "source": data_source  # Use tracked data_source variable
                    }
                    groups_processed += 1
                    
                    # Log details for each route
                    source_tag = "[PRED]" if all_weights[route_key]["source"] == "prediction" else "[REAL]"
                    print(f"  {source_tag} Route: {route_key}")
                    print(f"    Paths: {len(path_ratios)}")
                    print(f"    Ratios: {path_ratios}")
                    
                    cost_str = ", ".join([f"path{k}={v/1024/1024:.2f}MB" 
                                         for k, v in path_costs.items()])
                    print(f"    Costs: {cost_str}")
            
            print(f"[Collection] ✓ Computed weights for {groups_processed} route groups")
            
            # Save path bandwidth history for UI sparklines display
            # IMPORTANT: This must be called BEFORE save_next_predictions so that we can
            # use the existing next_predictions (from previous iteration) which contain
            # the predictions that were made for data_minute
            # Use data_minute_full because this data represents traffic during that minute
            save_path_bandwidth_history(data_minute_full, all_weights, usage)
            
            # Now save next predictions for the CURRENT minute (with actual_mb: null) for UI display
            # These predictions are for the current minute that is just starting
            # This overwrites next_predictions, so it must come AFTER save_path_bandwidth_history
            print(f"\n[Collection] Step 5a/6: Saving next predictions for minute {current_timestamp}...")
            save_next_predictions(current_timestamp_full, iteration)
            
            # Step 6: Write to file and copy to Server 1 ONOS container
            print(f"\n[Collection] Step 6/6: Writing to file and syncing to ONOS...")
            
            payload = {
                "metadata": {
                    "timestamp_unix": time.time(),
                    "timestamp_utc8": current_timestamp_full,  # Current time for ONOS
                    "data_period_start": data_minute_full,     # When the data period started
                    "data_period_end": current_timestamp_full, # When the data period ended
                    "iteration": iteration,
                    "collection_interval_seconds": COLLECTION_INTERVAL,
                    "total_network_traffic_mb": round(total_network_mb, 2),
                    "route_groups_computed": groups_processed,
                    "load_balancing_mode": LOAD_BALANCING_MODE,
                    "using_predictions": use_predictions,
                    "description": "Path selection weights based on " + ("TCN-predicted" if use_predictions else "real-time cumulative") + " bandwidth usage"
                },
                "path_selection_weights": {}
            }
            
            # Format weights with meaningful descriptions
            for route_key, data in all_weights.items():
                src, dst = route_key.split("->")
                
                data_source = data.get("source", "realtime")
                source_desc = "TCN model prediction" if data_source == "prediction" else "real-time measurement"
                
                payload["path_selection_weights"][route_key] = {
                    "description": f"Traffic distribution ratios for {route_key}",
                    "data_source": source_desc,
                    "note": "Lower bandwidth usage = higher ratio (path receives more new flows)",
                    "path_details": {}
                }
                
                for path_idx, ratio in data["ratios"].items():
                    spine = get_spine_name(src, dst, path_idx)
                    cost_bytes = data["costs"][path_idx]
                    cost_mb = cost_bytes / (1024 * 1024)
                    
                    cost_description = f"{'Predicted' if data_source == 'prediction' else 'Measured'} bandwidth over {COLLECTION_INTERVAL}s"
                    
                    payload["path_selection_weights"][route_key]["path_details"][f"path_{path_idx}"] = {
                        "via_spine": spine,
                        "selection_ratio": round(ratio, 4),
                        "bandwidth_cost": {
                            "bytes": cost_bytes,
                            "megabytes": round(cost_mb, 2),
                            "source": data_source,
                            "description": cost_description
                        }
                    }
            
            success = write_and_copy_weights(payload)
            
            with stats_lock_push:
                push_stats['total_pushes'] += 1
                if success:
                    push_stats['successful_pushes'] += 1
                    push_stats['last_push_time'] = current_timestamp_full
                    push_stats['last_error'] = None
                else:
                    push_stats['failed_pushes'] += 1
                    push_stats['last_error'] = current_timestamp_full
            
            if success:
                print(f"[Sync] ✓ Successfully synced weights to ONOS container")
                print(f"[Sync] Container: {REMOTE_CONTAINER} on {REMOTE_HOST}")
                print(f"[Sync] Path: {REMOTE_CONTAINER_PATH}")
            else:
                print(f"[Sync] ✗ Failed to sync weights")
            
            elapsed_time = time.time() - start_time
            print(f"\n[Collection] Iteration {iteration} - Data for minute {data_minute} completed in {elapsed_time:.1f}s")
            print(f"  Success rate: {push_stats['successful_pushes']}/{push_stats['total_pushes']}")
            print(f"{'='*70}\n")
            
        except Exception as e:
            print(f"\n[Collection] ✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            
            with stats_lock_push:
                push_stats['last_error'] = str(e)
            
            time.sleep(10)
    
    print("\n[Telemetry] Worker stopped")

def write_and_copy_weights(payload):
    """Write weights to local file and copy to Server 1 ONOS container using Ansible."""
    try:
        # Write to local file
        with open(LOCAL_FILE, 'w') as f:
            json.dump(payload, f, indent=2)
        
        print(f"[File] ✓ Wrote to local file: {LOCAL_FILE}")
        
        # Run Ansible playbook to copy to ONOS container
        ansible_command = [
            "ansible-playbook",
            "-i", ANSIBLE_INVENTORY,
            ANSIBLE_PLAYBOOK
        ]
        
        print(f"[Ansible] Running playbook: {ANSIBLE_PLAYBOOK}")
        
        result = subprocess.run(
            ansible_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30
        )
        
        if result.returncode == 0:
            stdout = result.stdout.decode().strip()
            # Check for failures in Ansible output
            if "failed=0" in stdout:
                print(f"[Ansible] ✓ Playbook executed successfully")
                return True
            else:
                print(f"[Ansible] ⚠ Playbook completed with warnings")
                print(f"[Ansible] Output: {stdout[-500:]}")  # Last 500 chars
                return False
        else:
            error_msg = result.stderr.decode().strip()
            print(f"[Ansible] ✗ Playbook failed with return code {result.returncode}")
            print(f"[Ansible] Error: {error_msg[:500]}")  # First 500 chars
            return False
            
    except subprocess.TimeoutExpired:
        print(f"[Ansible] ✗ Playbook timeout (30s)")
        return False
    except FileNotFoundError:
        print(f"[Ansible] ✗ ansible-playbook command not found. Is Ansible installed?")
        return False
    except Exception as e:
        print(f"[Ansible] ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

# ==============================================================================
# ===                         REST API ENDPOINTS                         ===
# ==============================================================================

app = Flask(__name__)

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.route('/health', methods=['GET'])
def health_check():
    with stats_lock_push:
        stats_copy = push_stats.copy()
    
    return jsonify({
        "status": "healthy",
        "mode": "ansible-based-cumulative",
        "local_file": LOCAL_FILE,
        "remote_location": f"{REMOTE_HOST}:{REMOTE_CONTAINER}:{REMOTE_CONTAINER_PATH}",
        "collection_interval": COLLECTION_INTERVAL,
        "push_statistics": stats_copy
    })

@app.route('/current_weights', methods=['GET'])
def get_current_weights():
    """Read and return current weights from file."""
    try:
        with open(LOCAL_FILE, 'r') as f:
            data = json.load(f)
        
        return jsonify({
            "success": True,
            "data": data
        })
    except FileNotFoundError:
        return jsonify({
            "success": False,
            "error": "Weights file not found yet"
        }), 404
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/stats', methods=['GET'])
def get_stats():
    """Get collection statistics."""
    with stats_lock_push:
        stats_copy = push_stats.copy()
    
    with stats_lock:
        usage_copy = cumulative_usage.copy()
    
    total_bytes = sum(
        sum(port_data['total_bytes'] for port_data in ports.values())
        for ports in usage_copy.values()
    )
    
    return jsonify({
        "success": True,
        "push_stats": stats_copy,
        "last_collection": {
            "total_bytes": total_bytes,
            "total_mb": round(total_bytes / 1024 / 1024, 2),
            "devices": len(usage_copy)
        }
    })

@app.route('/force_sync', methods=['POST'])
def force_sync():
    """Manually trigger a sync to ONOS container."""
    try:
        with open(LOCAL_FILE, 'r') as f:
            payload = json.load(f)
        
        success = write_and_copy_weights(payload)
        
        return jsonify({
            "success": success,
            "message": "Sync completed" if success else "Sync failed"
        })
    except FileNotFoundError:
        return jsonify({
            "success": False,
            "error": "No weights file available to sync"
        }), 404
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# ==============================================================================
# ===                              MAIN                                  ===
# ==============================================================================

def main():
    global running
    
    print("="*70)
    print("=== Ansible-Based Cumulative Link Load Balancing System ===")
    print("=== Weights Synced to ONOS Docker Container via Ansible ===")
    print("="*70)
    print(f"\nConfiguration:")
    print(f"  Mode: ANSIBLE-BASED DISTRIBUTION (Cumulative)")
    print(f"  Load Balancing Mode: {LOAD_BALANCING_MODE.upper()}")
    if LOAD_BALANCING_MODE == "prediction":
        print(f"    -> Using TCN-predicted bandwidth for path selection")
        print(f"    -> Min history iterations: {MIN_HISTORY_ITERATIONS}")
    else:
        print(f"    -> Using real-time measured bandwidth for path selection")
    print(f"  Timezone: UTC+8")
    print(f"  Local File: {LOCAL_FILE}")
    print(f"  Ansible Playbook: {ANSIBLE_PLAYBOOK}")
    print(f"  Ansible Inventory: {ANSIBLE_INVENTORY}")
    print(f"  Remote Server: {REMOTE_HOST}")
    print(f"  ONOS Container: {REMOTE_CONTAINER}")
    print(f"  Container Path: {REMOTE_CONTAINER_PATH}")
    print(f"  Collection Interval: {COLLECTION_INTERVAL} seconds")
    print(f"  API Server: http://{API_HOST}:{API_PORT}")
    print(f"\nWorkflow:")
    print(f"  1. Collect bandwidth over {COLLECTION_INTERVAL}s")
    if LOAD_BALANCING_MODE == "prediction":
        print(f"  2. Update TCN prediction history buffer")
        print(f"  3. Compute path weights using TCN predictions")
    else:
        print(f"  2. Compute path weights (grouped by src->dst)")
    print(f"  3. Write to {LOCAL_FILE}")
    print(f"  4. Run Ansible playbook to:")
    print(f"     a. Copy to Server 1: /tmp/onos_path_selection.json")
    print(f"     b. Docker cp to container: {REMOTE_CONTAINER_PATH}")
    print(f"  5. Java reads file every 5 seconds")
    print(f"  6. Java selects path via deterministic round-robin")
    print(f"\nEndpoints:")
    print(f"  GET  /health          - Health check")
    print(f"  GET  /current_weights - View current weights")
    print(f"  GET  /stats           - Collection statistics")
    print(f"  POST /force_sync      - Manually trigger sync")
    print("="*70)
    
    # Initialize TCN prediction system if in prediction or hybrid mode
    if LOAD_BALANCING_MODE in ["prediction", "hybrid"]:
        print(f"\n[Init] Initializing TCN Prediction System (mode: {LOAD_BALANCING_MODE})...")
        if initialize_prediction_system():
            print("[Init] ✓ TCN models loaded successfully")
            print(f"[Init]   Models available for {len(ROUTE_TO_PATH_MODELS)} routes")
        else:
            print("[Init] ⚠ WARNING: TCN models could not be loaded")
            print("[Init]   Will fall back to real-time measurements")
    
    # Verify Ansible is installed
    try:
        result = subprocess.run(
            ["ansible-playbook", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        if result.returncode == 0:
            print("\n✓ Ansible detected")
        else:
            print("\n⚠ WARNING: Ansible may not be properly configured")
    except FileNotFoundError:
        print("\n✗ ERROR: ansible-playbook not found. Please install Ansible!")
        print("  Run: sudo apt install ansible")
        sys.exit(1)
    except Exception as e:
        print(f"\n⚠ WARNING: Could not verify Ansible: {e}")
    
    # Verify playbook exists
    import os
    if not os.path.exists(ANSIBLE_PLAYBOOK):
        print(f"\n✗ ERROR: Playbook not found: {ANSIBLE_PLAYBOOK}")
        sys.exit(1)
    else:
        print(f"✓ Playbook found: {ANSIBLE_PLAYBOOK}")
    
    # Verify inventory exists
    if not os.path.exists(ANSIBLE_INVENTORY):
        print(f"\n✗ ERROR: Inventory not found: {ANSIBLE_INVENTORY}")
        sys.exit(1)
    else:
        print(f"✓ Inventory found: {ANSIBLE_INVENTORY}")
    
    # Start telemetry collection thread
    telemetry_thread = threading.Thread(target=telemetry_and_push_worker, daemon=True)
    telemetry_thread.start()
    
    print("\n⏳ Telemetry worker started...")
    print("✓ API server starting...")
    print("➤ Weights will be synced to ONOS every 60 seconds")
    print("➤ Generate traffic during 60-second collection window!")
    print("➤ Press Ctrl+C to stop")
    print("="*70 + "\n")
    
    try:
        app.run(host=API_HOST, port=API_PORT, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\n" + "="*70)
        print("Shutdown requested...")
        running = False
        
        print("\nFinal Statistics:")
        with stats_lock_push:
            print(f"  Total syncs: {push_stats['total_pushes']}")
            print(f"  Successful: {push_stats['successful_pushes']}")
            print(f"  Failed: {push_stats['failed_pushes']}")
            if push_stats['total_pushes'] > 0:
                success_rate = (push_stats['successful_pushes'] / 
                              push_stats['total_pushes'] * 100)
                print(f"  Success rate: {success_rate:.1f}%")
            if push_stats['last_push_time']:
                print(f"  Last successful sync: {push_stats['last_push_time']}")
        
        print("\nGoodbye!")
        print("="*70)
        sys.exit(0)

if __name__ == "__main__":
    main()