"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Server, Cpu, HardDrive, Activity, Database, Layers } from "lucide-react"
import { useEffect, useState } from "react"

interface ServerOverviewProps {
  detailed?: boolean
}

interface ServerData {
  ip: string
  name: string
  cpu: number
  memory: number
  rps: number
  totalMemory: number // Added total memory
  totalCpuCores: number // Added total CPU cores
  status: "active" | "inactive"
  comprehensiveLoad: number
  dynamicWeight: number
}

export function ServerOverview({ detailed = false }: ServerOverviewProps) {
  const [servers, setServers] = useState<ServerData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchServerData = async () => {
      try {
        const response = await fetch("/api/servers/weights")
        if (!response.ok) throw new Error("Failed to fetch server data")

        const data = await response.json()

        setServers(data.servers)
        setError(null)
      } catch (err) {
        console.error("Error fetching server data:", err)
        setError("Failed to load server data")
      } finally {
        setLoading(false)
      }
    }

    fetchServerData()
    const interval = setInterval(fetchServerData, 10000)
    return () => clearInterval(interval)
  }, [])

  const formatMemory = (bytes: number) => {
    return (bytes / 1024 / 1024 / 1024).toFixed(2)
  }

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Server Status & Load Distribution</CardTitle>
          <CardDescription>Dynamic Weight Random Selection Algorithm</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8 text-muted-foreground">Loading server data...</div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Server Status & Load Distribution</CardTitle>
          <CardDescription>Dynamic Weight Random Selection Algorithm</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8 text-destructive">{error}</div>
        </CardContent>
      </Card>
    )
  }

  const displayServers = servers // Always show all servers, don't filter by active status

  return (
    <Card>
      <CardHeader>
        <CardTitle>Server Status & Load Distribution</CardTitle>
        <CardDescription>Dynamic Weight Random Selection Algorithm</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {displayServers.map((server) => (
            <div
              key={server.ip}
              className="flex items-center gap-4 rounded-lg border border-border bg-secondary/50 p-4"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
                <Server
                  className={`h-6 w-6 ${server.status === "active" ? "text-primary" : "text-muted-foreground"}`}
                />
              </div>

              <div className="flex-1 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="font-semibold text-foreground">{server.name}</span>
                    <span className="text-xs text-muted-foreground">{server.ip}</span>
                    <Badge variant={server.status === "active" ? "default" : "secondary"}>{server.status}</Badge>
                    {server.status === "active" && (
                      <span className="text-sm text-muted-foreground">Weight: {server.dynamicWeight}</span>
                    )}
                  </div>
                  {server.status === "active" && (
                    <div className="flex items-center gap-2 text-sm">
                      <Activity className="h-4 w-4 text-chart-1" />
                      <span className="font-medium text-foreground">{server.rps.toFixed(2)} req/s</span>
                    </div>
                  )}
                </div>

                {server.status === "active" && (
                  <>
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <div className="flex items-center gap-1">
                        <Layers className="h-3 w-3" />
                        <span>{server.totalCpuCores} CPU Cores</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <Database className="h-3 w-3" />
                        <span>{formatMemory(server.totalMemory)} GB Total Memory</span>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-1">
                        <div className="flex items-center justify-between text-xs">
                          <span className="flex items-center gap-1 text-muted-foreground">
                            <Cpu className="h-3 w-3" />
                            CPU
                          </span>
                          <span className={`font-medium ${server.cpu > 80 ? "text-destructive" : "text-foreground"}`}>
                            {server.cpu.toFixed(1)}%
                          </span>
                        </div>
                        <Progress value={server.cpu} className="h-1.5" />
                      </div>
                      <div className="space-y-1">
                        <div className="flex items-center justify-between text-xs">
                          <span className="flex items-center gap-1 text-muted-foreground">
                            <HardDrive className="h-3 w-3" />
                            Memory
                          </span>
                          <span
                            className={`font-medium ${server.memory > 80 ? "text-destructive" : "text-foreground"}`}
                          >
                            {server.memory.toFixed(1)}%
                          </span>
                        </div>
                        <Progress value={server.memory} className="h-1.5" />
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}


