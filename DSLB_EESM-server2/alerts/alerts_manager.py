import os
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict
from enum import Enum

# --- Configuration ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ALERTS_FILE = os.path.join(SCRIPT_DIR, 'system_alerts.json')

# Alert retention settings
MAX_ALERTS = 100  # Maximum number of alerts to keep
ALERT_RETENTION_HOURS = 24  # Auto-delete alerts older than this

# Timezone
LOCAL_TZ = timezone(timedelta(hours=8))


class AlertType(Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    SUCCESS = "success"
    INFO = "info"


class AlertCategory(Enum):
    SERVER_POWER = "server_power"
    SERVER_HEALTH = "server_health"
    ML_MODEL = "ml_model"
    CONNECTION_DRAINING = "connection_draining"
    RESOURCE_THRESHOLD = "resource_threshold"
    SYSTEM_TELEMETRY = "system_telemetry"
    NETWORK_PATH = "network_path"


def _load_alerts() -> Dict:
    """Load alerts from JSON file."""
    try:
        if os.path.exists(ALERTS_FILE):
            with open(ALERTS_FILE, 'r') as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"[ALERTS] Error loading alerts file: {e}")
    
    return {"alerts": [], "last_cleanup": None}


def _save_alerts(data: Dict) -> bool:
    """Save alerts to JSON file."""
    try:
        with open(ALERTS_FILE, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        return True
    except IOError as e:
        print(f"[ALERTS] Error saving alerts file: {e}")
        return False


def _cleanup_old_alerts(data: Dict) -> Dict:
    """Remove alerts older than ALERT_RETENTION_HOURS."""
    current_time = datetime.now(LOCAL_TZ)
    cutoff_time = current_time - timedelta(hours=ALERT_RETENTION_HOURS)
    
    original_count = len(data["alerts"])
    data["alerts"] = [
        alert for alert in data["alerts"]
        if datetime.fromisoformat(alert["timestamp"]) > cutoff_time
    ]
    
    removed_count = original_count - len(data["alerts"])
    if removed_count > 0:
        print(f"[ALERTS] Cleaned up {removed_count} old alerts")
    
    # Also enforce MAX_ALERTS limit (keep most recent)
    if len(data["alerts"]) > MAX_ALERTS:
        data["alerts"] = sorted(
            data["alerts"], 
            key=lambda x: x["timestamp"], 
            reverse=True
        )[:MAX_ALERTS]
    
    data["last_cleanup"] = current_time.isoformat()
    return data


def add_alert(
    alert_type: AlertType,
    category: AlertCategory,
    title: str,
    message: str,
    server_name: Optional[str] = None,
    server_ip: Optional[str] = None,
    additional_data: Optional[Dict] = None
) -> str:
    """
    Add a new alert to the system.
    
    Args:
        alert_type: Type of alert (critical, warning, success, info)
        category: Category of alert
        title: Short title for the alert
        message: Detailed message
        server_name: Optional server name involved
        server_ip: Optional server IP involved
        additional_data: Optional extra data
        
    Returns:
        str: Alert ID
    """
    data = _load_alerts()
    # data = _cleanup_old_alerts(data)
    
    alert_id = str(uuid.uuid4())[:8]
    current_time = datetime.now(LOCAL_TZ)
    
    alert = {
        "id": alert_id,
        "type": alert_type.value,
        "category": category.value,
        "title": title,
        "message": message,
        "timestamp": current_time.isoformat(),
        "server_name": server_name,
        "server_ip": server_ip,
        "acknowledged": False,
        "additional_data": additional_data or {}
    }
    
    # Add to beginning of list (most recent first)
    data["alerts"].insert(0, alert)
    _save_alerts(data)
    
    print(f"[ALERTS] Added {alert_type.value.upper()} alert: {title}")
    return alert_id


def get_alerts(
    limit: Optional[int] = 50,
    category: Optional[AlertCategory] = None,
    alert_type: Optional[AlertType] = None,
    include_acknowledged: bool = True
) -> List[Dict]:
    """
    Get alerts with optional filtering.
    
    Args:
        limit: Maximum number of alerts to return
        category: Filter by category
        alert_type: Filter by type
        include_acknowledged: Include acknowledged alerts
        
    Returns:
        List of alert dictionaries
    """
    data = _load_alerts()
    # data = _cleanup_old_alerts(data)
    # _save_alerts(data)
    
    alerts = data["alerts"]
    
    # Apply filters
    if category:
        alerts = [a for a in alerts if a["category"] == category.value]
    
    if alert_type:
        alerts = [a for a in alerts if a["type"] == alert_type.value]
    
    if not include_acknowledged:
        alerts = [a for a in alerts if not a.get("acknowledged", False)]
    
    # Apply limit
    if limit:
        alerts = alerts[:limit]
    
    return alerts


def acknowledge_alert(alert_id: str) -> bool:
    """Mark an alert as acknowledged."""
    data = _load_alerts()
    
    for alert in data["alerts"]:
        if alert["id"] == alert_id:
            alert["acknowledged"] = True
            alert["acknowledged_at"] = datetime.now(LOCAL_TZ).isoformat()
            _save_alerts(data)
            print(f"[ALERTS] Acknowledged alert: {alert_id}")
            return True
    
    return False


def delete_alert(alert_id: str) -> bool:
    """Delete a specific alert."""
    data = _load_alerts()
    original_count = len(data["alerts"])
    
    data["alerts"] = [a for a in data["alerts"] if a["id"] != alert_id]
    
    if len(data["alerts"]) < original_count:
        _save_alerts(data)
        print(f"[ALERTS] Deleted alert: {alert_id}")
        return True
    
    return False


def clear_all_alerts() -> int:
    """Clear all alerts. Returns count of deleted alerts."""
    data = _load_alerts()
    count = len(data["alerts"])
    data["alerts"] = []
    data["last_cleanup"] = datetime.now(LOCAL_TZ).isoformat()
    _save_alerts(data)
    print(f"[ALERTS] Cleared all {count} alerts")
    return count


def get_alert_counts() -> Dict[str, int]:
    """Get counts of alerts by type."""
    data = _load_alerts()
    
    counts = {
        "total": len(data["alerts"]),
        "critical": 0,
        "warning": 0,
        "success": 0,
        "info": 0,
        "unacknowledged": 0
    }
    
    for alert in data["alerts"]:
        alert_type = alert.get("type", "info")
        if alert_type in counts:
            counts[alert_type] += 1
        if not alert.get("acknowledged", False):
            counts["unacknowledged"] += 1
    
    return counts


# =============================================================================
# Convenience Functions for Specific Alert Types
# =============================================================================

# --- 1. Server Power State Changes ---

def alert_proactive_scale_up(server_name: str, server_ip: str, predicted_traffic: int):
    """Alert for proactive scale-up based on traffic forecast."""
    add_alert(
        AlertType.SUCCESS,
        AlertCategory.SERVER_POWER,
        "Proactive Scale-Up",
        f"{server_name} powered on proactively based on traffic forecast of {predicted_traffic:,} requests/hour",
        server_name=server_name,
        server_ip=server_ip,
        additional_data={"predicted_traffic": predicted_traffic, "scaling_type": "proactive"}
    )


def alert_proactive_scale_down(server_name: str, server_ip: str, predicted_traffic: int):
    """Alert for proactive scale-down based on traffic forecast."""
    add_alert(
        AlertType.SUCCESS,
        AlertCategory.SERVER_POWER,
        "Proactive Scale-Down",
        f"{server_name} powered off proactively - forecast shows lower traffic demand ({predicted_traffic:,} requests/hour)",
        server_name=server_name,
        server_ip=server_ip,
        additional_data={"predicted_traffic": predicted_traffic, "scaling_type": "proactive"}
    )


def alert_reactive_scale_up(server_name: str, server_ip: str, avg_cpu: float, avg_mem: float, threshold_type: str, cpu_threshold: float, mem_threshold: float, num_servers: int):
    """Alert for reactive scale-up due to high load."""
    if num_servers > 1:
        load_desc = "average"
        data = {"avg_cpu": avg_cpu, "avg_mem": avg_mem, "scaling_type": "reactive", "cpu_threshold": cpu_threshold, "mem_threshold": mem_threshold, "num_servers": num_servers}
    else:
        load_desc = "server"
        data = {"cpu": avg_cpu, "mem": avg_mem, "scaling_type": "reactive", "cpu_threshold": cpu_threshold, "mem_threshold": mem_threshold, "num_servers": num_servers}
    
    if threshold_type == "cpu":
        msg = f"{server_name} powered on reactively - 5-minute {load_desc} CPU: {avg_cpu:.1f}% exceeded threshold of {cpu_threshold:.1f}%"
    else:
        msg = f"{server_name} powered on reactively - 5-minute {load_desc} Memory: {avg_mem:.1f}% exceeded threshold of {mem_threshold:.1f}%"
    
    add_alert(
        AlertType.WARNING,
        AlertCategory.SERVER_POWER,
        "Reactive Scale-Up",
        msg,
        server_name=server_name,
        server_ip=server_ip,
        additional_data=data
    )


def alert_reactive_scale_down(server_name: str, server_ip: str, avg_cpu: float, avg_mem: float, cpu_threshold: float, mem_threshold: float, num_servers: int):
    """Alert for reactive scale-down due to sustained low load."""
    if num_servers > 1:
        load_desc = "average"
        data = {"avg_cpu": avg_cpu, "avg_mem": avg_mem, "scaling_type": "reactive", "cpu_threshold": cpu_threshold, "mem_threshold": mem_threshold, "num_servers": num_servers}
    else:
        load_desc = "server"
        data = {"cpu": avg_cpu, "mem": avg_mem, "scaling_type": "reactive", "cpu_threshold": cpu_threshold, "mem_threshold": mem_threshold, "num_servers": num_servers}
    
    add_alert(
        AlertType.INFO,
        AlertCategory.SERVER_POWER,
        "Reactive Scale-Down",
        f"{server_name} powered off reactively - 30-minute {load_desc} load below threshold (CPU: {avg_cpu:.1f}% < {cpu_threshold:.1f}%, Mem: {avg_mem:.1f}% < {mem_threshold:.1f}%)",
        server_name=server_name,
        server_ip=server_ip,
        additional_data=data
    )


# --- 2. Server Health & Failover Events ---

def alert_health_check_failed(server_name: str, server_ip: str, reason: str):
    """Alert when server health check fails."""
    add_alert(
        AlertType.CRITICAL,
        AlertCategory.SERVER_HEALTH,
        "Server Health Check Failed",
        f"{server_name} ({server_ip}) failed synthetic health check - {reason}",
        server_name=server_name,
        server_ip=server_ip,
        additional_data={"failure_reason": reason}
    )


def alert_failover_initiated(failed_server: str, failed_ip: str, replacement_server: str):
    """Alert when failover is initiated."""
    add_alert(
        AlertType.CRITICAL,
        AlertCategory.SERVER_HEALTH,
        "Server Failover Initiated",
        f"Initiating failover for {failed_server} - replacement server: {replacement_server}",
        server_name=failed_server,
        server_ip=failed_ip,
        additional_data={"replacement_server": replacement_server}
    )


def alert_failover_complete(failed_server: str, replacement_server: str, replacement_ip: str):
    """Alert when failover completes successfully."""
    add_alert(
        AlertType.SUCCESS,
        AlertCategory.SERVER_HEALTH,
        "Server Failover Complete",
        f"Failover complete: {replacement_server} successfully replaced {failed_server}",
        server_name=replacement_server,
        server_ip=replacement_ip,
        additional_data={"replaced_server": failed_server}
    )


def alert_no_replacement_available(failed_server: str, failed_ip: str):
    """Alert when no replacement server is available."""
    add_alert(
        AlertType.WARNING,
        AlertCategory.SERVER_HEALTH,
        "No Replacement Available",
        f"{failed_server} failed but no healthy replacement server available",
        server_name=failed_server,
        server_ip=failed_ip
    )


def alert_server_blacklisted(server_name: str, server_ip: str):
    """Alert when server is added to failed blacklist."""
    add_alert(
        AlertType.WARNING,
        AlertCategory.SERVER_HEALTH,
        "Server Added to Blacklist",
        f"{server_name} ({server_ip}) added to failed server blacklist",
        server_name=server_name,
        server_ip=server_ip
    )


def alert_server_recovered(server_name: str, server_ip: str):
    """Alert when server recovers and is removed from blacklist."""
    add_alert(
        AlertType.SUCCESS,
        AlertCategory.SERVER_HEALTH,
        "Server Recovered",
        f"{server_name} ({server_ip}) recovered and removed from failed server blacklist",
        server_name=server_name,
        server_ip=server_ip
    )


# --- 3. ML Model & Prediction Alerts ---

def alert_forecast_failed(error_message: str):
    """Alert when web traffic forecast fails."""
    add_alert(
        AlertType.WARNING,
        AlertCategory.ML_MODEL,
        "Forecast Generation Failed",
        f"Web traffic forecast failed - {error_message}",
        additional_data={"error": error_message}
    )


def alert_model_retraining_started():
    """Alert when LSTM model retraining starts."""
    add_alert(
        AlertType.INFO,
        AlertCategory.ML_MODEL,
        "LSTM Model Retraining Started",
        "LSTM model retraining initiated - weekly validity period expired"
    )


def alert_model_retraining_complete(accuracy: float, r2_score: float, smape: float):
    """Alert when LSTM model retraining completes."""
    add_alert(
        AlertType.SUCCESS,
        AlertCategory.ML_MODEL,
        "LSTM Model Retraining Complete",
        f"LSTM model retrained - Accuracy: {accuracy:.1f}%, R²: {r2_score:.2f}, sMAPE: {smape:.1f}%",
        additional_data={"accuracy": accuracy, "r2_score": r2_score, "smape": smape}
    )


# --- 4. Connection Draining Events ---

def alert_draining_started(server_name: str, server_ip: str):
    """Alert when connection draining starts."""
    add_alert(
        AlertType.INFO,
        AlertCategory.CONNECTION_DRAINING,
        "Connection Draining Started",
        f"{server_name} entering connection draining mode - excluded from load balancer",
        server_name=server_name,
        server_ip=server_ip
    )


def alert_draining_complete(server_name: str, server_ip: str):
    """Alert when connection draining completes."""
    add_alert(
        AlertType.INFO,
        AlertCategory.CONNECTION_DRAINING,
        "Connection Draining Complete",
        f"{server_name} draining complete - server will be powered off",
        server_name=server_name,
        server_ip=server_ip
    )


def alert_graceful_shutdown(server_name: str, server_ip: str):
    """Alert when server gracefully shuts down after draining."""
    add_alert(
        AlertType.SUCCESS,
        AlertCategory.CONNECTION_DRAINING,
        "Server Gracefully Shutdown",
        f"{server_name} gracefully shutdown after connection draining",
        server_name=server_name,
        server_ip=server_ip
    )


# --- 5. Resource Threshold Alerts ---

def alert_high_cpu(avg_cpu: float, threshold: float, num_servers: int, server_name: Optional[str] = None, server_ip: Optional[str] = None):
    """
    Alert for high CPU usage.
    If num_servers > 1: Shows average CPU of all active servers.
    If num_servers == 1: Shows the single server's CPU usage.
    """
    if num_servers > 1:
        title = "High Average CPU Usage Detected"
        msg = f"Average CPU across {num_servers} active servers at {avg_cpu:.1f}% (threshold: {threshold:.1f}%) - monitoring for sustained high load"
        data = {"avg_cpu": avg_cpu, "threshold": threshold, "num_servers": num_servers}
    else:
        title = "High CPU Usage Detected"
        msg = f"{server_name} CPU at {avg_cpu:.1f}% (threshold: {threshold:.1f}%) - monitoring for sustained high load"
        data = {"cpu": avg_cpu, "threshold": threshold, "num_servers": num_servers}
    
    add_alert(
        AlertType.WARNING,
        AlertCategory.RESOURCE_THRESHOLD,
        title,
        msg,
        server_name=server_name if num_servers == 1 else None,
        server_ip=server_ip if num_servers == 1 else None,
        additional_data=data
    )


def alert_high_memory(avg_mem: float, threshold: float, num_servers: int, server_name: Optional[str] = None, server_ip: Optional[str] = None):
    """
    Alert for high memory usage.
    If num_servers > 1: Shows average memory of all active servers.
    If num_servers == 1: Shows the single server's memory usage.
    """
    if num_servers > 1:
        title = "High Average Memory Usage Detected"
        msg = f"Average memory across {num_servers} active servers at {avg_mem:.1f}% (threshold: {threshold:.1f}%) - approaching threshold"
        data = {"avg_mem": avg_mem, "threshold": threshold, "num_servers": num_servers}
    else:
        title = "High Memory Usage Detected"
        msg = f"{server_name} memory at {avg_mem:.1f}% (threshold: {threshold:.1f}%) - approaching threshold"
        data = {"mem": avg_mem, "threshold": threshold, "num_servers": num_servers}
    
    add_alert(
        AlertType.WARNING,
        AlertCategory.RESOURCE_THRESHOLD,
        title,
        msg,
        server_name=server_name if num_servers == 1 else None,
        server_ip=server_ip if num_servers == 1 else None,
        additional_data=data
    )


def alert_low_utilization(avg_cpu: float, avg_mem: float):
    """Alert for low resource utilization (scale down opportunity)."""
    add_alert(
        AlertType.INFO,
        AlertCategory.RESOURCE_THRESHOLD,
        "Low Resource Utilization",
        f"System average CPU: {avg_cpu:.1f}%, Memory: {avg_mem:.1f}% - scale down opportunity",
        additional_data={"avg_cpu": avg_cpu, "avg_mem": avg_mem}
    )


# --- 6. System Status & Telemetry Alerts ---

def alert_prometheus_connection_failed(prometheus_url: str, error: str):
    """Alert when Prometheus connection fails."""
    add_alert(
        AlertType.WARNING,
        AlertCategory.SYSTEM_TELEMETRY,
        "Prometheus Connection Failed",
        f"Cannot connect to Prometheus at {prometheus_url} - {error}",
        additional_data={"prometheus_url": prometheus_url, "error": error}
    )


def alert_onos_connection_failed(onos_host: str, error: str):
    """Alert when ONOS connection fails."""
    add_alert(
        AlertType.WARNING,
        AlertCategory.SYSTEM_TELEMETRY,
        "ONOS Connection Failed",
        f"Cannot connect to ONOS controller at {onos_host} - {error}",
        additional_data={"onos_host": onos_host, "error": error}
    )


def alert_apache_exporter_down(server_ip: str):
    """Alert when Apache exporter is down."""
    add_alert(
        AlertType.WARNING,
        AlertCategory.SYSTEM_TELEMETRY,
        "Apache Exporter Down",
        f"Apache exporter on {server_ip} is not responding",
        server_ip=server_ip
    )


def alert_status_sync_success():
    """Alert when server status sync succeeds."""
    add_alert(
        AlertType.SUCCESS,
        AlertCategory.SYSTEM_TELEMETRY,
        "Server Status Synced",
        "Server status successfully synced to Server 1"
    )


def alert_status_sync_failed(error: str):
    """Alert when server status sync fails."""
    add_alert(
        AlertType.WARNING,
        AlertCategory.SYSTEM_TELEMETRY,
        "Status Sync Failed",
        f"Failed to sync server status to Server 1 - {error}",
        additional_data={"error": error}
    )


# --- 7. Network Path Alerts ---

def alert_high_path_congestion(path_name: str, utilization: float):
    """Alert for high path congestion."""
    add_alert(
        AlertType.WARNING,
        AlertCategory.NETWORK_PATH,
        "High Path Congestion",
        f"Path {path_name} congestion at {utilization:.1f}% - may affect traffic routing",
        additional_data={"path_name": path_name, "utilization": utilization}
    )


# =============================================================================
# Initialize alerts file if it doesn't exist
# =============================================================================
if not os.path.exists(ALERTS_FILE):
    _save_alerts({"alerts": [], "last_cleanup": datetime.now(LOCAL_TZ).isoformat()})
    print(f"[ALERTS] Initialized alerts file at: {ALERTS_FILE}")
