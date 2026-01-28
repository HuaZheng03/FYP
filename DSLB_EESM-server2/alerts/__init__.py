# Alerts Module for DSLB_EESM
# This module provides system alert management functionality

from .alerts_manager import (
    # Core functions
    add_alert,
    get_alerts,
    acknowledge_alert,
    delete_alert,
    clear_all_alerts,
    get_alert_counts,
    
    # Enums
    AlertType,
    AlertCategory,
    
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

__all__ = [
    # Core functions
    'add_alert',
    'get_alerts',
    'acknowledge_alert',
    'delete_alert',
    'clear_all_alerts',
    'get_alert_counts',
    
    # Enums
    'AlertType',
    'AlertCategory',
    
    # Server Power State Changes
    'alert_proactive_scale_up',
    'alert_proactive_scale_down',
    'alert_reactive_scale_up',
    'alert_reactive_scale_down',
    
    # Server Health & Failover Events
    'alert_health_check_failed',
    'alert_failover_initiated',
    'alert_failover_complete',
    'alert_no_replacement_available',
    'alert_server_blacklisted',
    'alert_server_recovered',
    
    # ML Model & Prediction Alerts
    'alert_forecast_failed',
    'alert_model_retraining_started',
    'alert_model_retraining_complete',
    
    # Connection Draining Events
    'alert_draining_started',
    'alert_draining_complete',
    'alert_graceful_shutdown',
    
    # Resource Threshold Alerts
    'alert_high_cpu',
    'alert_high_memory',
    'alert_low_utilization',
    
    # System Status & Telemetry Alerts
    'alert_prometheus_connection_failed',
    'alert_onos_connection_failed',
    'alert_apache_exporter_down',
    'alert_status_sync_success',
    'alert_status_sync_failed',
    
    # Network Path Alerts
    'alert_high_path_congestion',
]
