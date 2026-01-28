"use client"

import { useEffect, useState, useCallback } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { 
  AlertTriangle, 
  CheckCircle, 
  Info, 
  XCircle, 
  Trash2, 
  RefreshCw,
  Server,
  Activity,
  Cpu,
  Network,
  Brain,
  Unplug,
  Bell,
  BellOff,
  ChevronDown,
  ChevronUp
} from "lucide-react"

// Alert type definitions
interface Alert {
  id: string
  type: 'critical' | 'warning' | 'success' | 'info'
  category: string
  title: string
  message: string
  timestamp: string
  relativeTime: string
  server_name?: string
  server_ip?: string
  acknowledged: boolean
  additional_data?: Record<string, any>
}

interface AlertCounts {
  total: number
  critical: number
  warning: number
  success: number
  info: number
  unacknowledged: number
}

// Category icon mapping
const getCategoryIcon = (category: string) => {
  switch (category) {
    case 'server_power':
      return <Server className="h-4 w-4" />
    case 'server_health':
      return <Activity className="h-4 w-4" />
    case 'ml_model':
      return <Brain className="h-4 w-4" />
    case 'connection_draining':
      return <Unplug className="h-4 w-4" />
    case 'resource_threshold':
      return <Cpu className="h-4 w-4" />
    case 'system_telemetry':
      return <Activity className="h-4 w-4" />
    case 'network_path':
      return <Network className="h-4 w-4" />
    default:
      return <Bell className="h-4 w-4" />
  }
}

// Type icon and color mapping
const getTypeStyles = (type: string) => {
  switch (type) {
    case 'critical':
      return {
        icon: <XCircle className="h-4 w-4" />,
        bgColor: 'bg-red-500/10',
        iconBg: 'bg-red-500/20',
        iconColor: 'text-red-500',
        borderColor: 'border-red-500/30'
      }
    case 'warning':
      return {
        icon: <AlertTriangle className="h-4 w-4" />,
        bgColor: 'bg-amber-500/10',
        iconBg: 'bg-amber-500/20',
        iconColor: 'text-amber-500',
        borderColor: 'border-amber-500/30'
      }
    case 'success':
      return {
        icon: <CheckCircle className="h-4 w-4" />,
        bgColor: 'bg-emerald-500/10',
        iconBg: 'bg-emerald-500/20',
        iconColor: 'text-emerald-500',
        borderColor: 'border-emerald-500/30'
      }
    case 'info':
    default:
      return {
        icon: <Info className="h-4 w-4" />,
        bgColor: 'bg-blue-500/10',
        iconBg: 'bg-blue-500/20',
        iconColor: 'text-blue-500',
        borderColor: 'border-blue-500/30'
      }
  }
}

// Category label mapping
const getCategoryLabel = (category: string) => {
  const labels: Record<string, string> = {
    server_power: 'Server Power',
    server_health: 'Server Health',
    ml_model: 'ML Model',
    connection_draining: 'Connection Draining',
    resource_threshold: 'Resource Threshold',
    system_telemetry: 'System Telemetry',
    network_path: 'Network Path'
  }
  return labels[category] || category
}

export function AlertsPanel() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [counts, setCounts] = useState<AlertCounts>({
    total: 0,
    critical: 0,
    warning: 0,
    success: 0,
    info: 0,
    unacknowledged: 0
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [showAcknowledged, setShowAcknowledged] = useState(true)
  const [expandedAlert, setExpandedAlert] = useState<string | null>(null)
  const [displayLimit, setDisplayLimit] = useState(10)

  // Fetch alerts
  const fetchAlerts = useCallback(async () => {
    try {
      setIsRefreshing(true)
      const response = await fetch(`/api/alerts?limit=100&includeAcknowledged=${showAcknowledged}`)
      
      if (!response.ok) {
        throw new Error('Failed to fetch alerts')
      }
      
      const data = await response.json()
      setAlerts(data.alerts || [])
      setCounts(data.counts || {
        total: 0,
        critical: 0,
        warning: 0,
        success: 0,
        info: 0,
        unacknowledged: 0
      })
      setError(null)
    } catch (err) {
      console.error('Error fetching alerts:', err)
      setError('Failed to load alerts')
    } finally {
      setLoading(false)
      setIsRefreshing(false)
    }
  }, [showAcknowledged])

  // Delete alert
  const deleteAlert = async (alertId: string) => {
    try {
      const response = await fetch(`/api/alerts?id=${alertId}`, {
        method: 'DELETE'
      })
      
      if (response.ok) {
        setAlerts(prev => prev.filter(a => a.id !== alertId))
        setCounts(prev => ({
          ...prev,
          total: Math.max(0, prev.total - 1)
        }))
      }
    } catch (err) {
      console.error('Error deleting alert:', err)
    }
  }

  // Acknowledge alert
  const acknowledgeAlert = async (alertId: string) => {
    try {
      const response = await fetch('/api/alerts', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alertId, acknowledged: true })
      })
      
      if (response.ok) {
        setAlerts(prev => prev.map(a => 
          a.id === alertId ? { ...a, acknowledged: true } : a
        ))
        setCounts(prev => ({
          ...prev,
          unacknowledged: Math.max(0, prev.unacknowledged - 1)
        }))
      }
    } catch (err) {
      console.error('Error acknowledging alert:', err)
    }
  }

  // Clear all alerts
  const clearAllAlerts = async () => {
    if (!confirm('Are you sure you want to clear all alerts?')) return
    
    try {
      const response = await fetch('/api/alerts?clearAll=true', {
        method: 'DELETE'
      })
      
      if (response.ok) {
        setAlerts([])
        setCounts({
          total: 0,
          critical: 0,
          warning: 0,
          success: 0,
          info: 0,
          unacknowledged: 0
        })
      }
    } catch (err) {
      console.error('Error clearing alerts:', err)
    }
  }

  // Initial fetch and auto-refresh every 10 seconds
  useEffect(() => {
    fetchAlerts()
    const interval = setInterval(fetchAlerts, 10000)
    return () => clearInterval(interval)
  }, [fetchAlerts])

  // Alerts to display
  const displayedAlerts = alerts.slice(0, displayLimit)

  return (
    <Card className="flex flex-col h-full">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              System Alerts
              {counts.unacknowledged > 0 && (
                <Badge variant="destructive" className="text-xs">
                  {counts.unacknowledged} new
                </Badge>
              )}
            </CardTitle>
            <CardDescription>
              Recent events and notifications
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowAcknowledged(!showAcknowledged)}
              title={showAcknowledged ? 'Hide acknowledged' : 'Show acknowledged'}
            >
              {showAcknowledged ? (
                <Bell className="h-4 w-4" />
              ) : (
                <BellOff className="h-4 w-4" />
              )}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={fetchAlerts}
              disabled={isRefreshing}
            >
              <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            </Button>
            {alerts.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={clearAllAlerts}
                className="text-muted-foreground hover:text-destructive"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
        
        {/* Alert type summary badges */}
        {counts.total > 0 && (
          <div className="flex gap-2 mt-2 flex-wrap">
            {counts.critical > 0 && (
              <Badge variant="outline" className="text-red-500 border-red-500/50 text-xs">
                {counts.critical} Critical
              </Badge>
            )}
            {counts.warning > 0 && (
              <Badge variant="outline" className="text-amber-500 border-amber-500/50 text-xs">
                {counts.warning} Warning
              </Badge>
            )}
            {counts.success > 0 && (
              <Badge variant="outline" className="text-emerald-500 border-emerald-500/50 text-xs">
                {counts.success} Success
              </Badge>
            )}
            {counts.info > 0 && (
              <Badge variant="outline" className="text-blue-500 border-blue-500/50 text-xs">
                {counts.info} Info
              </Badge>
            )}
          </div>
        )}
      </CardHeader>
      
      <CardContent className="flex-1 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-32 text-muted-foreground">
            <AlertTriangle className="h-6 w-6 mb-2" />
            <p className="text-sm">{error}</p>
            <Button variant="link" size="sm" onClick={fetchAlerts}>
              Try again
            </Button>
          </div>
        ) : alerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-muted-foreground">
            <CheckCircle className="h-8 w-8 mb-2 text-emerald-500" />
            <p className="text-sm">No alerts - all systems operational</p>
          </div>
        ) : (
          <div className="space-y-2 overflow-y-auto max-h-[400px] pr-1">
            {displayedAlerts.map((alert) => {
              const styles = getTypeStyles(alert.type)
              const isExpanded = expandedAlert === alert.id
              
              return (
                <div
                  key={alert.id}
                  className={`
                    relative rounded-lg border p-3 transition-all
                    ${styles.bgColor} ${styles.borderColor}
                    ${alert.acknowledged ? 'opacity-60' : ''}
                    hover:opacity-100
                  `}
                >
                  <div className="flex gap-3">
                    {/* Type icon */}
                    <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${styles.iconBg}`}>
                      <span className={styles.iconColor}>{styles.icon}</span>
                    </div>
                    
                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-semibold text-foreground">
                            {alert.title}
                          </span>
                          <Badge variant="outline" className="text-xs px-1.5 py-0">
                            {getCategoryLabel(alert.category)}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          <Badge variant="outline" className="text-xs whitespace-nowrap">
                            {alert.relativeTime}
                          </Badge>
                        </div>
                      </div>
                      
                      <p className="text-xs text-muted-foreground mt-1 break-words">
                        {alert.message}
                      </p>
                      
                      {/* Server info if available */}
                      {(alert.server_name || alert.server_ip) && (
                        <div className="flex items-center gap-2 mt-1.5">
                          <Server className="h-3 w-3 text-muted-foreground" />
                          <span className="text-xs text-muted-foreground">
                            {alert.server_name && alert.server_ip
                              ? `${alert.server_name} (${alert.server_ip})`
                              : alert.server_name || alert.server_ip
                            }
                          </span>
                        </div>
                      )}
                      
                      {/* Additional data (expandable) */}
                      {alert.additional_data && Object.keys(alert.additional_data).length > 0 && (
                        <div className="mt-2">
                          <button
                            onClick={() => setExpandedAlert(isExpanded ? null : alert.id)}
                            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                          >
                            {isExpanded ? (
                              <>
                                <ChevronUp className="h-3 w-3" /> Hide details
                              </>
                            ) : (
                              <>
                                <ChevronDown className="h-3 w-3" /> Show details
                              </>
                            )}
                          </button>
                          
                          {isExpanded && (
                            <div className="mt-2 p-2 rounded bg-background/50 text-xs">
                              {Object.entries(alert.additional_data).map(([key, value]) => (
                                <div key={key} className="flex justify-between py-0.5">
                                  <span className="text-muted-foreground">{key}:</span>
                                  <span className="font-mono">{String(value)}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                      
                      {/* Action buttons */}
                      <div className="flex items-center gap-2 mt-2">
                        {!alert.acknowledged && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 text-xs px-2"
                            onClick={() => acknowledgeAlert(alert.id)}
                          >
                            <CheckCircle className="h-3 w-3 mr-1" />
                            Acknowledge
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 text-xs px-2 text-muted-foreground hover:text-destructive"
                          onClick={() => deleteAlert(alert.id)}
                        >
                          <Trash2 className="h-3 w-3 mr-1" />
                          Dismiss
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
            
            {/* Load more button */}
            {alerts.length > displayLimit && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full mt-2"
                onClick={() => setDisplayLimit(prev => prev + 10)}
              >
                Show more ({alerts.length - displayLimit} remaining)
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
