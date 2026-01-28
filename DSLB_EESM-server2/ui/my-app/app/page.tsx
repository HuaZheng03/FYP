"use client"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ServerOverview } from "@/components/server-overview"
import { NetworkTopology } from "@/components/network-topology"
import { LoadBalancingMetrics } from "@/components/load-balancing-metrics"
import { MLPredictions } from "@/components/ml-predictions"
import { AlertsPanel } from "@/components/alerts-panel"
import { Activity, Server, Network, Brain } from "lucide-react"
import { SpineLeafTopology } from "@/components/spine-leaf-topology"
import { useEffect, useState } from "react"
import { ServerHealthStatus } from "@/components/server-health-status"
import { ThemeToggle } from "@/components/theme-toggle"

export default function SDNDashboard() {
  const [serverStats, setServerStats] = useState({
    active: 0,
    total: 3,
    totalRps: 0,
    avgResponseTime: 0,
  })

  useEffect(() => {
    const fetchServerStats = async () => {
      try {
        const [statusResponse, telemetryResponse, healthResponse] = await Promise.all([
          fetch("/api/servers/status", { cache: "no-store" }),
          fetch("/api/servers/telemetry", { cache: "no-store" }),
          fetch("/api/servers/health", { cache: "no-store" }),
        ])

        if (statusResponse.ok && telemetryResponse.ok && healthResponse.ok) {
          const statusData = await statusResponse.json()
          const telemetryData = await telemetryResponse.json()
          const healthData = await healthResponse.json()

          // Use telemetry data for active count (servers that are really responding)
          const activeServers = telemetryData.servers.filter((s: any) => s.status === "active")
          const activeCount = activeServers.length
          const totalCount = Object.keys(statusData.servers).length

          const totalRps = activeServers.reduce((sum: number, server: any) => sum + (server.rps || 0), 0)

          const activeHealthyServers = healthData.servers.filter(
            (s: any) => s.active && s.healthy && s.responseTime !== undefined,
          )
          const avgResponseTime =
            activeHealthyServers.length > 0
              ? activeHealthyServers.reduce((sum: number, server: any) => sum + server.responseTime, 0) /
                activeHealthyServers.length
              : 0

          setServerStats({
            active: activeCount,
            total: totalCount,
            totalRps: Math.round(totalRps),
            avgResponseTime: Math.round(avgResponseTime),
          })
        }
      } catch (error) {
        console.error("Failed to fetch server stats:", error)
      }
    }

    fetchServerStats()
    const interval = setInterval(fetchServerStats, 10000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border bg-card">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary">
                <Network className="h-6 w-6 text-primary-foreground" />
              </div>
              <div>
                <h1 className="text-xl font-semibold text-foreground">DSLB_EESM</h1>
                <p className="text-sm text-muted-foreground">Dynamic Server & Energy Management</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2 rounded-lg bg-accent/10 px-3 py-1.5">
                <div className="h-2 w-2 animate-pulse rounded-full bg-accent" />
                <span className="text-sm font-medium text-accent">System Active</span>
              </div>
              <ThemeToggle />
            </div>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-6 py-6">
        <Tabs defaultValue="overview" className="space-y-6">
          <TabsList className="grid w-full grid-cols-4 lg:w-auto lg:inline-grid">
            <TabsTrigger value="overview" className="gap-2">
              <Activity className="h-4 w-4" />
              Overview
            </TabsTrigger>
            <TabsTrigger value="servers" className="gap-2">
              <Server className="h-4 w-4" />
              Servers
            </TabsTrigger>
            <TabsTrigger value="network" className="gap-2">
              <Network className="h-4 w-4" />
              Network
            </TabsTrigger>
            <TabsTrigger value="predictions" className="gap-2">
              <Brain className="h-4 w-4" />
              ML Predictions
            </TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-6">
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              <Card>
                <CardHeader className="pb-3">
                  <CardDescription>Active Servers</CardDescription>
                  <CardTitle className="text-3xl">
                    {serverStats.active} / {serverStats.total}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-xs text-muted-foreground">
                    {serverStats.total - serverStats.active} servers in standby
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-3">
                  <CardDescription>Total Requests/s</CardDescription>
                  <CardTitle className="text-3xl">
                    {serverStats.active > 0 ? serverStats.totalRps.toLocaleString() : "—"}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-xs text-muted-foreground">
                    {serverStats.active > 0 ? "Sum of all active servers" : "No active servers"}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-3">
                  <CardDescription>Avg Response Time</CardDescription>
                  <CardTitle className="text-3xl">
                    {serverStats.active > 0 ? `${serverStats.avgResponseTime}ms` : "—"}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-xs text-muted-foreground">
                    {serverStats.active > 0 ? "Across active servers" : "No active servers"}
                  </div>
                </CardContent>
              </Card>
            </div>

            <SpineLeafTopology />

            <div className="grid gap-6 lg:grid-cols-3">
              <div className="lg:col-span-2">
                <ServerOverview />
              </div>
              <div>
                <AlertsPanel />
              </div>
            </div>

            <LoadBalancingMetrics />
          </TabsContent>

          <TabsContent value="servers" className="space-y-6">
            <ServerHealthStatus />
            <ServerOverview detailed />
          </TabsContent>

          <TabsContent value="network" className="space-y-6">
            <NetworkTopology />
          </TabsContent>

          <TabsContent value="predictions" className="space-y-6">
            <MLPredictions />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  )
}

