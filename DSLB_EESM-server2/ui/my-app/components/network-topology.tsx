"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Network } from "lucide-react"
import { SpineLeafTopology } from "@/components/spine-leaf-topology"
import { useEffect, useState } from "react"

interface PathData {
  pathIndex: number
  pathName: string
  txBytesPerSec: number
  rxBytesPerSec: number
  totalBytesPerSec: number
  txMbps: number
  rxMbps: number
  totalMbps: number
  utilizationPercent: number
}

interface PathBandwidthData {
  [pairKey: string]: PathData[]
}

export function NetworkTopology() {
  const [pathData, setPathData] = useState<PathBandwidthData>({})
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const fetchPathBandwidth = async () => {
      try {
        const response = await fetch("/api/paths/bandwidth", { cache: "no-store" })
        if (response.ok) {
          const data = await response.json()
          setPathData(data.paths || {})
        }
      } catch (error) {
        console.error("Failed to fetch path bandwidth:", error)
      } finally {
        setIsLoading(false)
      }
    }

    fetchPathBandwidth()
    const interval = setInterval(fetchPathBandwidth, 5000)
    return () => clearInterval(interval)
  }, [])

  const formatRate = (mbps: number): string => {
    if (mbps < 1) return `${(mbps * 1024).toFixed(2)} Kbps`
    return `${mbps.toFixed(2)} Mbps`
  }

  const getStatusBadge = (utilization: number) => {
    if (utilization < 50) return { variant: "default" as const, label: "optimal" }
    if (utilization < 75) return { variant: "secondary" as const, label: "moderate" }
    if (utilization < 90) return { variant: "outline" as const, label: "high" }
    return { variant: "destructive" as const, label: "critical" }
  }

  return (
    <div className="space-y-6">
      <SpineLeafTopology />

      <Card>
        <CardHeader>
          <CardTitle>Path Status & Bandwidth Utilization</CardTitle>
          <CardDescription>Real-time network path monitoring</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="text-muted-foreground">Loading path bandwidth data...</div>
            </div>
          ) : (
            <div className="space-y-6">
              {Object.entries(pathData).map(([pairKey, paths]) => {
                const [src, dst] = pairKey.split("-")
                return (
                  <div key={pairKey} className="space-y-3">
                    <div className="flex items-center gap-2 border-b border-border pb-2">
                      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                        <span className="rounded bg-primary/10 px-2 py-1 text-primary">{src}</span>
                        <span className="text-muted-foreground">-</span>
                        <span className="rounded bg-primary/10 px-2 py-1 text-primary">{dst}</span>
                      </div>
                      <span className="text-xs text-muted-foreground">({paths.length} paths available)</span>
                    </div>

                    <div className="grid gap-3">
                      {paths.map((path) => {
                        const status = getStatusBadge(path.utilizationPercent)
                        return (
                          <div
                            key={path.pathIndex}
                            className="flex items-center gap-4 rounded-lg border border-border bg-secondary/50 p-4"
                          >
                            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-chart-1/10">
                              <Network className="h-6 w-6 text-chart-1" />
                            </div>

                            <div className="flex-1 space-y-2">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                  <span className="font-semibold text-foreground">{path.pathName}</span>
                                  <Badge variant={status.variant}>{status.label}</Badge>
                                  <span className="text-sm text-muted-foreground">500 Mbps capacity</span>
                                </div>
                                <div className="flex items-center gap-4 text-sm">
                                  <span className="text-muted-foreground">
                                    TX: {formatRate(path.txMbps)} | RX: {formatRate(path.rxMbps)}
                                  </span>
                                  <span
                                    className={`font-medium ${
                                      path.utilizationPercent > 85 ? "text-destructive" : "text-foreground"
                                    }`}
                                  >
                                    {path.utilizationPercent.toFixed(1)}% utilized
                                  </span>
                                </div>
                              </div>
                              <Progress value={path.utilizationPercent} className="h-2" />
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              })}

              {Object.keys(pathData).length === 0 && !isLoading && (
                <div className="flex items-center justify-center py-8 text-muted-foreground">
                  No path bandwidth data available
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
