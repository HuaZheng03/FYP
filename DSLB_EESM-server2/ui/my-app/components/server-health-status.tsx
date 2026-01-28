"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Server, CheckCircle, XCircle, AlertCircle, Clock } from "lucide-react"
import { useEffect, useState } from "react"

interface HealthData {
  name: string
  ip: string
  active: boolean
  healthy: boolean
  reallyActive?: boolean  // Server is actually responding (has Prometheus metrics)
  configActive?: boolean  // Original active value from config
  configDraining?: boolean
  lastCheck?: string
  responseTime?: number
  endpoint?: string
}

export function ServerHealthStatus() {
  const [servers, setServers] = useState<HealthData[]>([])
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState<string | null>(null)

  useEffect(() => {
    fetchHealthData()
    const interval = setInterval(fetchHealthData, 10000)
    return () => clearInterval(interval)
  }, [])

  const fetchHealthData = async () => {
    try {
      const response = await fetch("/api/servers/health")
      if (response.ok) {
        const data = await response.json()
        setServers(data.servers)
      }
    } catch (error) {
      console.error("Failed to fetch health data:", error)
    } finally {
      setLoading(false)
    }
  }

  const toggleHealth = async (ip: string, currentHealth: boolean) => {
    setUpdating(ip)
    try {
      const response = await fetch("/api/servers/health", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ip, healthy: !currentHealth }),
      })

      if (response.ok) {
        await fetchHealthData()
      } else {
        console.error("Failed to update health status")
      }
    } catch (error) {
      console.error("Error updating health status:", error)
    } finally {
      setUpdating(null)
    }
  }

  const getHealthBadge = (server: HealthData) => {
    // Priority of status display:
    // 1. If healthy=false in config, always show as Unhealthy (regardless of active state)
    // 2. If server is not really responding (powered off), show as Inactive (Powered Off)
    // 3. If server is active and healthy, show as Healthy
    
    if (!server.healthy) {
      // Unhealthy takes priority - show if healthy=false regardless of active state
      const suffix = server.reallyActive ? "" : " (Inactive)"
      return (
        <Badge className="bg-red-500/10 text-red-500 hover:bg-red-500/20">
          <XCircle className="mr-1 h-3 w-3" />
          Unhealthy{suffix}
        </Badge>
      )
    }
    
    if (!server.reallyActive) {
      // Server is not responding (powered off) but config says healthy
      return (
        <Badge variant="secondary" className="text-muted-foreground">
          <AlertCircle className="mr-1 h-3 w-3" />
          Inactive (Powered Off)
        </Badge>
      )
    }
    
    if (server.active && server.healthy) {
      // Server is active and healthy
      return (
        <Badge className="bg-green-500/10 text-green-500 hover:bg-green-500/20">
          <CheckCircle className="mr-1 h-3 w-3" />
          Healthy
        </Badge>
      )
    }
    
    // Fallback for edge cases
    return (
      <Badge variant="secondary" className="text-muted-foreground">
        <AlertCircle className="mr-1 h-3 w-3" />
        Inactive
      </Badge>
    )
  }

  const getCardBorderColor = (server: HealthData) => {
    // Red border for unhealthy servers
    if (!server.healthy) return "border-red-500/50"
    // Gray border for powered-off servers
    if (!server.reallyActive) return "border-muted-foreground/30"
    // Green border for active and healthy servers
    if (server.active && server.healthy) return "border-green-500/50"
    return "border-border"
  }

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Server Health Management</CardTitle>
          <CardDescription>Monitor and control server health status</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8 text-muted-foreground">Loading health data...</div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Server Health Management</CardTitle>
        <CardDescription>Monitor and control server health status based on synthetic HTTP checks</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 md:grid-cols-3">
          {servers.map((server) => (
            <Card key={server.ip} className={`${getCardBorderColor(server)} transition-colors`}>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Server className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <CardTitle className="text-sm font-medium">{server.name}</CardTitle>
                      <CardDescription className="text-xs">{server.ip}</CardDescription>
                    </div>
                  </div>
                  {getHealthBadge(server)}
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {/* Health Check Details */}
                <div className="space-y-2 rounded-lg bg-secondary/50 p-3 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Health Check:</span>
                    <span className="font-mono text-foreground">
                      {server.endpoint || `http://${server.ip}:80/index.html`}
                    </span>
                  </div>
                  {server.responseTime && (
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Response Time:</span>
                      <span className="font-medium text-foreground">{server.responseTime}ms</span>
                    </div>
                  )}
                  {server.lastCheck && (
                    <div className="flex items-center justify-between">
                      <span className="flex items-center gap-1 text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        Last Check:
                      </span>
                      <span className="text-foreground">{new Date(server.lastCheck).toLocaleTimeString()}</span>
                    </div>
                  )}
                </div>

                {/* Manual Health Toggle */}
                <div className="flex items-center justify-between rounded-lg border border-border bg-card p-3">
                  <div>
                    <div className="text-sm font-medium">Manual Override</div>
                    <div className="text-xs text-muted-foreground">Toggle health status</div>
                  </div>
                  <Switch
                    checked={server.healthy}
                    onCheckedChange={() => toggleHealth(server.ip, server.healthy)}
                    disabled={updating === server.ip}
                  />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
