"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts"
import { Zap, TrendingDown, Server, AlertTriangle } from "lucide-react"
import { useTheme } from "next-themes"
import { useEffect, useState } from "react"

// Chart colors for light and dark modes
const CHART_COLORS = {
  light: {
    power: "#eab308",      // Yellow 500 - for power consumption
    powerFill: "#fef08a",  // Yellow 200 - for area fill
    servers: "#3b82f6",    // Blue 500 - for active servers
  },
  dark: {
    power: "#facc15",      // Yellow 400 - brighter yellow for dark mode
    powerFill: "#854d0e",  // Yellow 900 with alpha - for area fill
    servers: "#60a5fa",    // Blue 400 - brighter blue for dark mode
  },
}

const powerData = [
  { time: "00:00", consumption: 4.2, servers: 10, efficiency: 78 },
  { time: "04:00", consumption: 2.8, servers: 6, efficiency: 85 },
  { time: "08:00", consumption: 3.6, servers: 8, efficiency: 82 },
  { time: "12:00", consumption: 4.8, servers: 11, efficiency: 76 },
  { time: "16:00", consumption: 5.2, servers: 12, efficiency: 74 },
  { time: "20:00", consumption: 3.2, servers: 7, efficiency: 84 },
  { time: "24:00", consumption: 2.4, servers: 5, efficiency: 88 },
]

const thresholds = [
  { metric: "CPU Threshold", current: 80, threshold: 85, status: "normal" },
  { metric: "Memory Threshold", current: 75, threshold: 85, status: "normal" },
  { metric: "Min Active Servers", current: 8, threshold: 4, status: "normal" },
  { metric: "Max Response Time", current: 42, threshold: 100, status: "optimal" },
]

export function PowerManagement() {
  const { resolvedTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const colors = mounted ? CHART_COLORS[resolvedTheme === 'dark' ? 'dark' : 'light'] : CHART_COLORS.light

  return (
    <div className="space-y-6">
      <div className="grid gap-6 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-3">
            <CardDescription>Current Power</CardDescription>
            <CardTitle className="text-3xl">3.2 kW</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xs text-accent">-28% vs baseline</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardDescription>Energy Saved Today</CardDescription>
            <CardTitle className="text-3xl">18.4 kWh</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xs text-muted-foreground">$2.76 cost savings</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardDescription>Power Efficiency</CardDescription>
            <CardTitle className="text-3xl">84%</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xs text-accent">+6% improvement</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardDescription>Standby Servers</CardDescription>
            <CardTitle className="text-3xl">4 / 12</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xs text-muted-foreground">Ready for activation</div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Power Consumption & Server Scaling</CardTitle>
          <CardDescription>Dynamic server power management based on LSTM predictions</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={powerData}>
                <defs>
                  <linearGradient id="colorPower" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={colors.power} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={colors.power} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="time" stroke="hsl(var(--muted-foreground))" style={{ fontSize: "12px" }} />
                <YAxis
                  yAxisId="left"
                  stroke="hsl(var(--muted-foreground))"
                  style={{ fontSize: "12px" }}
                  label={{ value: "Power (kW)", angle: -90, position: "insideLeft" }}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  stroke="hsl(var(--muted-foreground))"
                  style={{ fontSize: "12px" }}
                  label={{ value: "Active Servers", angle: 90, position: "insideRight" }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "8px",
                  }}
                />
                <Legend />
                <Area
                  yAxisId="left"
                  type="monotone"
                  dataKey="consumption"
                  stroke={colors.power}
                  fill="url(#colorPower)"
                  strokeWidth={2}
                  name="Power Consumption (kW)"
                />
                <Line
                  yAxisId="right"
                  type="stepAfter"
                  dataKey="servers"
                  stroke={colors.servers}
                  strokeWidth={2}
                  name="Active Servers"
                  dot={{ fill: colors.servers, r: 4 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Power Management Thresholds</CardTitle>
          <CardDescription>Server activation/deactivation based on resource utilization</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {thresholds.map((item) => (
              <div
                key={item.metric}
                className="flex items-center gap-4 rounded-lg border border-border bg-secondary/50 p-4"
              >
                <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-accent/10">
                  {item.status === "optimal" ? (
                    <Zap className="h-6 w-6 text-accent" />
                  ) : item.status === "warning" ? (
                    <AlertTriangle className="h-6 w-6 text-chart-3" />
                  ) : (
                    <Server className="h-6 w-6 text-chart-1" />
                  )}
                </div>

                <div className="flex-1 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="font-semibold text-foreground">{item.metric}</span>
                      <Badge
                        variant={
                          item.status === "optimal" ? "default" : item.status === "warning" ? "secondary" : "outline"
                        }
                      >
                        {item.status}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-4 text-sm">
                      <span className="text-muted-foreground">
                        Threshold: {item.threshold}
                        {typeof item.threshold === "number" && item.threshold < 10 ? "" : "%"}
                      </span>
                      <span className="font-medium text-foreground">
                        Current: {item.current}
                        {typeof item.current === "number" && item.current < 10 ? "" : "%"}
                      </span>
                    </div>
                  </div>
                  <Progress value={(item.current / item.threshold) * 100} className="h-2" />
                </div>
              </div>
            ))}
          </div>

          <div className="mt-6 rounded-lg border border-border bg-muted/50 p-4">
            <div className="flex items-start gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/10">
                <TrendingDown className="h-4 w-4 text-accent" />
              </div>
              <div className="flex-1">
                <h4 className="font-semibold text-foreground">Power Management Strategy</h4>
                <p className="mt-1 text-sm text-muted-foreground">
                  Servers are automatically powered on when predicted requests exceed capacity or when CPU/Memory usage
                  exceeds 85% threshold. Servers are powered off during low-traffic periods to minimize energy
                  consumption while maintaining service quality.
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
