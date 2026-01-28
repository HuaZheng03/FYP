"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts"
import { useEffect, useState } from "react"
import { Activity } from "lucide-react"
import { useTheme } from "next-themes"

// Chart colors that work well in both light and dark modes
const CHART_COLORS = {
  light: {
    bar: "#3b82f6", // Blue 500 - vibrant blue for bars
    tooltipText: "#1f2937", // Gray 800 - dark text for light mode tooltip
    tooltipLabel: "#374151", // Gray 700 - slightly lighter for labels
    axisText: "#4b5563", // Gray 600 - for axis labels and ticks
    grid: "#e5e7eb", // Gray 200 - for grid lines
  },
  dark: {
    bar: "#60a5fa", // Blue 400 - brighter blue for dark mode
    tooltipText: "#1f2937", // Gray 800 - dark text (tooltip bg is light in recharts)
    tooltipLabel: "#374151", // Gray 700 - slightly lighter for labels
    axisText: "#d1d5db", // Gray 300 - light text for dark mode axes
    grid: "#374151", // Gray 700 - for grid lines in dark mode
  },
}

interface ServerData {
  ip: string
  name: string
  cpu: number
  memory: number
  rps: number
  status: "active" | "inactive"
  weight?: number
}

export function LoadBalancingMetrics() {
  const { resolvedTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  const [servers, setServers] = useState<ServerData[]>([])
  const [metrics, setMetrics] = useState({
    avgLoad: 0,
    variance: 0,
    efficiency: 0,
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setMounted(true)
  }, [])

  const colors = mounted ? CHART_COLORS[resolvedTheme === 'dark' ? 'dark' : 'light'] : CHART_COLORS.light

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch("/api/servers/weights", { cache: "no-store" })
        if (!response.ok) throw new Error("Failed to fetch")

        const data = await response.json()
        if (data.success && data.servers) {
          const activeServers = data.servers.filter((s: ServerData) => s.status === "active")
          setServers(activeServers)

          if (activeServers.length > 0) {
            const rpsValues = activeServers.map((s: ServerData) => s.rps)
            const totalRps = rpsValues.reduce((sum: number, rps: number) => sum + rps, 0)
            const avgRps = totalRps / activeServers.length

            const squaredDiffs = rpsValues.map((rps: number) => Math.pow(rps - avgRps, 2))
            const variance = squaredDiffs.reduce((sum: number, val: number) => sum + val, 0) / activeServers.length
            const stdDev = Math.sqrt(variance)
            const variancePercent = avgRps > 0 ? (stdDev / avgRps) * 100 : 0

            const efficiency = Math.max(0, Math.min(100, 100 - variancePercent))

            setMetrics({
              avgLoad: avgRps,
              variance: variancePercent,
              efficiency: efficiency,
            })
          } else {
            setMetrics({ avgLoad: 0, variance: 0, efficiency: 0 })
          }
        }
        setLoading(false)
      } catch (error) {
        console.error("Error fetching load balancing data:", error)
        setLoading(false)
      }
    }

    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => clearInterval(interval)
  }, [])

  const chartData = servers.map((server) => ({
    server: server.name,
    requests: Number(server.rps.toFixed(2)),
    weight: server.weight || 0,
  }))

  const maxRps = Math.max(...chartData.map((d) => d.requests), 10)
  const yAxisMax = Math.ceil(maxRps * 1.2)

  const getEfficiencyColor = (efficiency: number) => {
    if (efficiency >= 80) return "text-green-500"
    if (efficiency >= 60) return "text-yellow-500"
    return "text-red-500"
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Load Distribution Across Servers</CardTitle>
        <CardDescription>Real-time request distribution using Dynamic Weight Random Selection</CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex h-80 items-center justify-center">
            <Activity className="h-8 w-8 animate-pulse text-muted-foreground" />
          </div>
        ) : (
          <>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
                  <XAxis 
                    dataKey="server" 
                    stroke={colors.axisText} 
                    tick={{ fill: colors.axisText, fontSize: 12 }}
                    style={{ fontSize: "12px" }} 
                  />
                  <YAxis
                    stroke={colors.axisText}
                    tick={{ fill: colors.axisText, fontSize: 12 }}
                    style={{ fontSize: "12px" }}
                    label={{ value: "Requests/s", angle: -90, position: "insideLeft", fill: colors.axisText }}
                    domain={[0, yAxisMax]}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: resolvedTheme === 'dark' ? "#1e293b" : "#ffffff",
                      border: resolvedTheme === 'dark' ? "1px solid #334155" : "1px solid #e2e8f0",
                      borderRadius: "8px",
                      zIndex: 1000,
                    }}
                    labelStyle={{
                      color: resolvedTheme === 'dark' ? "#f1f5f9" : "#1e293b",
                      fontWeight: 600,
                      marginBottom: "4px",
                    }}
                    itemStyle={{
                      color: resolvedTheme === 'dark' ? "#e2e8f0" : "#334155",
                    }}
                    cursor={{ fill: 'transparent' }}
                    wrapperStyle={{ zIndex: 1000 }}
                  />
                  <Legend />
                  <Bar dataKey="requests" fill={colors.bar} name="Requests per Second" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-4 rounded-lg border border-border bg-secondary/50 p-4 md:grid-cols-4">
              <div>
                <div className="text-xs text-muted-foreground">Avg Load per Server</div>
                <div className="text-lg font-semibold text-foreground">
                  {servers.length > 0 ? `${metrics.avgLoad.toFixed(2)} req/s` : "—"}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Load Variance (CV)</div>
                <div className="text-lg font-semibold text-foreground">
                  {servers.length > 0 ? `±${metrics.variance.toFixed(1)}%` : "—"}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Balancing Efficiency</div>
                <div className={`text-lg font-semibold ${servers.length > 0 ? getEfficiencyColor(metrics.efficiency) : "text-foreground"}`}>
                  {servers.length > 0 ? `${metrics.efficiency.toFixed(1)}%` : "—"}
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {servers.length > 0 
                    ? (metrics.efficiency >= 80 ? "Excellent" : metrics.efficiency >= 60 ? "Good" : "Needs Improvement")
                    : "No active servers"
                  }
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Algorithm</div>
                <div className="text-lg font-semibold text-foreground">DWRS</div>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}



