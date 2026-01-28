"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
} from "recharts"
import { Brain, Activity, TrendingUp, TrendingDown, Minus } from "lucide-react"
import { useEffect, useState } from "react"
import { useTheme } from "next-themes"

// Professional chart colors that work well in both light and dark modes
const CHART_COLORS = {
  light: {
    actual: "#0ea5e9",      // Sky 500 - bright cyan blue for actual data
    predicted: "#f97316",   // Orange 500 - warm orange for predictions
    sparkActual: "#06b6d4", // Cyan 500 - for sparklines actual
    sparkPred: "#f59e0b",   // Amber 500 - for sparklines predicted
    axisText: "#64748b",    // Slate 500 - for axis labels and ticks
    grid: "#e2e8f0",        // Slate 200 - for grid lines
  },
  dark: {
    actual: "#38bdf8",      // Sky 400 - brighter cyan for dark backgrounds
    predicted: "#fb923c",   // Orange 400 - brighter orange for dark mode
    sparkActual: "#22d3ee", // Cyan 400 - brighter for sparklines
    sparkPred: "#fbbf24",   // Amber 400 - brighter for sparklines
    axisText: "#94a3b8",    // Slate 400 - for axis labels and ticks in dark mode
    grid: "#334155",        // Slate 700 - for grid lines in dark mode
  },
}

interface PredictionEntry {
  time: string
  predicted: number
  actual: number | null
}

interface DailyPredictions {
  date: string
  entries: PredictionEntry[]
}

// Path bandwidth history interfaces
interface PathBandwidthData {
  predicted_mb?: number  // Optional - only present after iteration 10 when predictions start
  actual_mb: number | null
}

interface PathHistoryEntry {
  timestamp: string
  time: string
  paths: { [pathName: string]: PathBandwidthData }
}

// Next predictions (predicted only, actual pending)
interface NextPredictions {
  timestamp: string
  time: string
  iteration: number
  mode: string
  paths: { [pathName: string]: PathBandwidthData }
}

interface PathBandwidthHistoryResponse {
  last_updated: string | null
  iteration: number | null
  using_predictions: boolean
  history_window_minutes: number
  paths: string[]
  current_state: { [pathName: string]: PathBandwidthData }
  next_predictions: NextPredictions | null
  history: PathHistoryEntry[]
}

// Sparkline data point
interface SparklinePoint {
  time: string
  predicted: number | null  // null when no predictions available (iterations 1-9)
  actual: number | null
}

export function MLPredictions() {
  const { resolvedTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  const [forecastValue, setForecastValue] = useState<number | null>(null)
  const [validUntil, setValidUntil] = useState<string | null>(null)
  const [lstmAccuracy, setLstmAccuracy] = useState<string | null>(null)
  const [tcnAccuracy, setTcnAccuracy] = useState<number | null>(null)
  const [tcnModelsCount, setTcnModelsCount] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [dailyPredictions, setDailyPredictions] = useState<PredictionEntry[]>([])
  const [predictionDate, setPredictionDate] = useState<string | null>(null)
  
  // Path bandwidth history state
  const [pathBandwidthHistory, setPathBandwidthHistory] = useState<PathBandwidthHistoryResponse | null>(null)
  const [pathHistoryLoading, setPathHistoryLoading] = useState(true)

  // For theme-aware colors
  useEffect(() => {
    setMounted(true)
  }, [])

  const colors = mounted ? CHART_COLORS[resolvedTheme === 'dark' ? 'dark' : 'light'] : CHART_COLORS.light

  // Helper function to calculate current hour from valid_until (which points to next hour)
  const getCurrentHourFromValidUntil = (validUntilStr: string | null): string | null => {
    if (!validUntilStr) return null
    // validUntil is in "HH:MM" format, current hour is one hour before
    const [hours] = validUntilStr.split(':').map(Number)
    const currentHour = hours - 1
    // Handle edge case where hours would be negative (midnight)
    const adjustedHour = currentHour < 0 ? 23 : currentHour
    return `${adjustedHour.toString().padStart(2, '0')}:00`
  }

  // Filter daily predictions to exclude current hour (only show previous hours)
  const chartPredictions = dailyPredictions.filter(entry => {
    const currentHour = getCurrentHourFromValidUntil(validUntil)
    if (!currentHour) return true // If no validUntil, show all
    return entry.time !== currentHour
  })

  useEffect(() => {
    const fetchForecast = async () => {
      try {
        const response = await fetch("/api/forecast", { cache: "no-store" })
        if (response.ok) {
          const data = await response.json()
          setForecastValue(data.predicted_requests || data.forecast || data.value || null)
          if (data.valid_until) {
            const timeStr = data.valid_until.split("T")[1]
            const timeHHMM = timeStr.substring(0, 5)
            setValidUntil(timeHHMM)
          }
        } else {
          console.error("Failed to fetch forecast data")
        }
      } catch (error) {
        console.error("Error fetching forecast:", error)
      } finally {
        setLoading(false)
      }
    }

    const fetchModelValidity = async () => {
      try {
        const response = await fetch("/api/model-validity", { cache: "no-store" })
        if (response.ok) {
          const data = await response.json()
          setLstmAccuracy(data.accuracy_percentage || null)
        } else {
          console.error("Failed to fetch model validity data")
        }
      } catch (error) {
        console.error("Error fetching model validity:", error)
      }
    }

    const fetchTcnAccuracy = async () => {
      try {
        const response = await fetch("/api/tcn-accuracy", { cache: "no-store" })
        if (response.ok) {
          const data = await response.json()
          setTcnAccuracy(data.average_accuracy_percentage || null)
          setTcnModelsCount(data.models_count || null)
        } else {
          console.error("Failed to fetch TCN accuracy data")
        }
      } catch (error) {
        console.error("Error fetching TCN accuracy:", error)
      }
    }

    const fetchDailyPredictions = async () => {
      try {
        const response = await fetch("/api/daily-predictions", { cache: "no-store" })
        if (response.ok) {
          const data: DailyPredictions = await response.json()
          setDailyPredictions(data.entries || [])
          setPredictionDate(data.date || null)
        } else {
          console.error("Failed to fetch daily predictions")
        }
      } catch (error) {
        console.error("Error fetching daily predictions:", error)
      }
    }

    const fetchPathBandwidthHistory = async () => {
      try {
        const response = await fetch("/api/path-bandwidth-history", { cache: "no-store" })
        if (response.ok) {
          const data: PathBandwidthHistoryResponse = await response.json()
          setPathBandwidthHistory(data)
        } else {
          console.error("Failed to fetch path bandwidth history")
        }
      } catch (error) {
        console.error("Error fetching path bandwidth history:", error)
      } finally {
        setPathHistoryLoading(false)
      }
    }

    fetchForecast()
    fetchModelValidity()
    fetchTcnAccuracy()
    fetchDailyPredictions()
    fetchPathBandwidthHistory()
    
    const interval = setInterval(() => {
      fetchForecast()
      fetchModelValidity()
      fetchTcnAccuracy()
      fetchDailyPredictions()
      fetchPathBandwidthHistory()
    }, 30000)

    return () => clearInterval(interval)
  }, [])

  // Helper function to get sparkline data for a path
  const getSparklineData = (pathName: string): SparklinePoint[] => {
    if (!pathBandwidthHistory?.history) return []
    
    return pathBandwidthHistory.history.map(entry => ({
      time: entry.time,
      // predicted_mb may not exist for iterations 1-9 (realtime mode)
      predicted: entry.paths[pathName]?.predicted_mb ?? null,
      actual: entry.paths[pathName]?.actual_mb ?? null
    }))
  }

  // Helper function to get current values for a path
  const getCurrentValues = (pathName: string) => {
    if (pathBandwidthHistory?.current_state?.[pathName]) {
      return pathBandwidthHistory.current_state[pathName]
    }
    if (pathBandwidthHistory?.history && pathBandwidthHistory.history.length > 0) {
      const lastEntry = pathBandwidthHistory.history[pathBandwidthHistory.history.length - 1]
      return lastEntry.paths[pathName] || { predicted_mb: undefined, actual_mb: null }
    }
    return { predicted_mb: undefined, actual_mb: null }
  }

  // Helper to format path name for display
  const formatPathName = (pathName: string) => {
    // leaf1-spine1-leaf2 -> "L1↔L2 via S1"
    const parts = pathName.split('-')
    if (parts.length === 3) {
      const src = parts[0].replace('leaf', 'L')
      const spine = parts[1].replace('spine', 'S')
      const dst = parts[2].replace('leaf', 'L')
      return { route: `${src}↔${dst}`, spine: `via ${spine}` }
    }
    return { route: pathName, spine: '' }
  }

  // Calculate trend (comparing last two entries)
  // Use predicted_mb if available, otherwise use actual_mb
  const getTrend = (pathName: string) => {
    if (!pathBandwidthHistory?.history || pathBandwidthHistory.history.length < 2) {
      return 'stable'
    }
    const history = pathBandwidthHistory.history
    const currentEntry = history[history.length - 1].paths[pathName]
    const previousEntry = history[history.length - 2].paths[pathName]
    
    // Use predicted_mb if available, fallback to actual_mb
    const current = currentEntry?.predicted_mb ?? currentEntry?.actual_mb ?? 0
    const previous = previousEntry?.predicted_mb ?? previousEntry?.actual_mb ?? 0
    
    const diff = ((current - previous) / (previous || 1)) * 100
    if (diff > 5) return 'up'
    if (diff < -5) return 'down'
    return 'stable'
  }

  // Group paths by route (leaf pairs)
  const pathGroups = [
    { title: 'leaf1 ↔ leaf2', paths: ['leaf1-spine1-leaf2', 'leaf1-spine2-leaf2'] },
    { title: 'leaf1 ↔ leaf3', paths: ['leaf1-spine1-leaf3', 'leaf1-spine2-leaf3'] },
    { title: 'leaf1 ↔ leaf6', paths: ['leaf1-spine1-leaf6', 'leaf1-spine2-leaf6'] },
    { title: 'leaf2 ↔ leaf3', paths: ['leaf2-spine1-leaf3', 'leaf2-spine2-leaf3'] },
    { title: 'leaf2 ↔ leaf6', paths: ['leaf2-spine1-leaf6', 'leaf2-spine2-leaf6'] },
    { title: 'leaf3 ↔ leaf6', paths: ['leaf3-spine1-leaf6', 'leaf3-spine2-leaf6'] },
  ]

  return (
    <div className="space-y-6">
      <div className="grid gap-6 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-3">
            <CardDescription>BiLSTM Model Accuracy</CardDescription>
            <CardTitle className="text-3xl">{loading ? "..." : lstmAccuracy || "N/A"}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xs text-muted-foreground">Web traffic prediction accuracy</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardDescription>TCN Model Accuracy</CardDescription>
            <CardTitle className="text-3xl">
              {loading ? "..." : tcnAccuracy !== null ? `${tcnAccuracy}%` : "N/A"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xs text-muted-foreground">
              Avg accuracy of {tcnModelsCount || 12} path bandwidth prediction models
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardDescription>Hourly Web Traffic Forecast</CardDescription>
            <CardTitle className="text-3xl">
              {loading ? "..." : forecastValue !== null ? forecastValue.toLocaleString() + " requests": "N/A"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xs text-muted-foreground">
              {validUntil ? `(valid until ${validUntil})` : "Predicted hourly requests"}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>BiLSTM HTTP Request Predictions</CardTitle>
              <CardDescription>
                {predictionDate 
                  ? `Today's hourly predictions vs actual requests (${predictionDate})`
                  : "Hourly request forecasting for server power management"}
              </CardDescription>
            </div>
            <Badge variant="outline" className="gap-2">
              <Brain className="h-3 w-3" />
              BiLSTM Model
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          {chartPredictions.length > 0 ? (
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartPredictions} margin={{ top: 5, right: 30, left: 20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
                  <XAxis 
                    dataKey="time" 
                    stroke={colors.axisText} 
                    tick={{ fill: colors.axisText, fontSize: 12 }}
                    label={{ value: "Time (Hour)", position: "insideBottom", offset: 2, fill: colors.axisText, fontSize: 12 }}
                  />
                  <YAxis
                    stroke={colors.axisText}
                    tick={{ fill: colors.axisText, fontSize: 12 }}
                    domain={[0, 'auto']}
                    label={{ value: "Requests", angle: -90, position: "insideLeft", offset: -10, fill: colors.axisText, fontSize: 12 }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px",
                    }}
                    formatter={(value, name) => {
                      if (value === null || value === undefined) return ["Pending", name]
                      return [typeof value === 'number' ? value.toLocaleString() : String(value), name]
                    }}
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="actual"
                    stroke={colors.actual}
                    strokeWidth={2}
                    name="Actual Requests"
                    dot={{ fill: colors.actual, r: 4, strokeWidth: 2, stroke: colors.actual }}
                    activeDot={{ r: 6, fill: colors.actual, stroke: resolvedTheme === 'dark' ? '#1e293b' : '#fff', strokeWidth: 2 }}
                    connectNulls={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="predicted"
                    stroke={colors.predicted}
                    strokeWidth={2}
                    strokeDasharray="5 5"
                    name="Predicted Requests"
                    dot={{ fill: colors.predicted, r: 4, strokeWidth: 2, stroke: colors.predicted }}
                    activeDot={{ r: 6, fill: colors.predicted, stroke: resolvedTheme === 'dark' ? '#1e293b' : '#fff', strokeWidth: 2 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="flex h-80 items-center justify-center text-muted-foreground">
              <div className="text-center">
                <Brain className="mx-auto h-12 w-12 opacity-50" />
                <p className="mt-4">No predictions available for today yet.</p>
                <p className="text-sm">Predictions will appear as the system runs.</p>
              </div>
            </div>
          )}

          {dailyPredictions.length > 0 && (
            <div className="mt-4 rounded-lg border border-border bg-secondary/50 p-4">
              <div className="text-xs text-muted-foreground mb-2">Today's Prediction Summary</div>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <div className="text-lg font-semibold text-foreground">{dailyPredictions.length}</div>
                  <div className="text-xs text-muted-foreground">Total Entries</div>
                </div>
                <div>
                  <div className="text-lg font-semibold text-foreground">
                    {dailyPredictions.filter(e => e.actual !== null).length}
                  </div>
                  <div className="text-xs text-muted-foreground">With Actual Data</div>
                </div>
                <div>
                  <div className="text-lg font-semibold text-foreground">
                    {dailyPredictions.filter(e => e.actual === null).length}
                  </div>
                  <div className="text-xs text-muted-foreground">Pending Actual</div>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Per-minute Path Bandwidth Prediction - Shows predicted values only (like Hourly Web Traffic Forecast) */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Per-minute Path Bandwidth Prediction</CardTitle>
              <CardDescription>
                {pathBandwidthHistory?.next_predictions && (pathBandwidthHistory?.iteration ?? 0) >= 10
                  ? `Predicted bandwidth for ${pathBandwidthHistory.next_predictions.time}`
                  : "TCN model predictions for all 12 network paths"}
              </CardDescription>
            </div>
            {pathBandwidthHistory?.next_predictions && (pathBandwidthHistory?.iteration ?? 0) >= 10 && (
              <Badge variant="outline" className="gap-2">
                <Brain className="h-3 w-3" />
                {pathBandwidthHistory.next_predictions.mode === "hybrid" 
                  ? "Hybrid (30% TCN + 70% Actual)" 
                  : pathBandwidthHistory.next_predictions.mode === "prediction" 
                    ? "TCN Model" 
                    : "Real-time"}
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {pathHistoryLoading ? (
            <div className="flex h-32 items-center justify-center text-muted-foreground">
              <div className="text-center">
                <Activity className="mx-auto h-8 w-8 animate-pulse opacity-50" />
                <p className="mt-2 text-sm">Loading predictions...</p>
              </div>
            </div>
          ) : pathBandwidthHistory?.next_predictions && (pathBandwidthHistory?.iteration ?? 0) >= 10 ? (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {pathGroups.flatMap(group => group.paths).map((pathName) => {
                const nextPred = pathBandwidthHistory.next_predictions?.paths?.[pathName]
                const parts = pathName.split('-')
                const src = parts[0].replace('leaf', 'L')
                const dst = parts[2].replace('leaf', 'L')
                const spineLabel = parts[1].replace('spine', 'S')
                
                return (
                  <div 
                    key={pathName} 
                    className="rounded-lg border border-border bg-secondary/30 p-3 hover:bg-secondary/50 transition-colors"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium text-foreground">
                        {src} ↔ {dst}
                      </span>
                      <span className="text-xs text-muted-foreground">{spineLabel}</span>
                    </div>
                    <div className="text-xl font-semibold" style={{ color: colors.sparkPred }}>
                      {nextPred?.predicted_mb !== undefined && nextPred?.predicted_mb !== null ? `${nextPred.predicted_mb.toFixed(2)} MB` : '—'}
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="flex h-32 items-center justify-center text-muted-foreground">
              <div className="text-center">
                <Brain className="mx-auto h-8 w-8 opacity-50" />
                <p className="mt-2 text-sm">
                  {(pathBandwidthHistory?.iteration ?? 0) < 10 
                    ? `Collecting history data... (Iteration ${pathBandwidthHistory?.iteration ?? 0}/10)`
                    : "No predictions available yet."}
                </p>
                <p className="text-xs">
                  {(pathBandwidthHistory?.iteration ?? 0) < 10 
                    ? "TCN predictions will start from iteration 10 after collecting sufficient history."
                    : "Predictions will appear when the system starts."}
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* TCN Path Bandwidth Predictions - Sparklines Grid */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>TCN Path Bandwidth Predictions</CardTitle>
              <CardDescription>
                {pathBandwidthHistory?.last_updated 
                  ? `Last updated: ${pathBandwidthHistory.last_updated}`
                  : "Real-time predicted vs actual bandwidth for all 12 network paths (rolling 15 min window)"}
              </CardDescription>
            </div>
            <Badge variant="outline" className="gap-2">
              <Activity className="h-3 w-3" />
              {pathBandwidthHistory?.using_predictions ? "Prediction Mode" : "Real-time Mode"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          {pathHistoryLoading ? (
            <div className="flex h-64 items-center justify-center text-muted-foreground">
              <div className="text-center">
                <Activity className="mx-auto h-12 w-12 animate-pulse opacity-50" />
                <p className="mt-4">Loading path bandwidth data...</p>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {pathGroups.map((group) => (
                <div key={group.title} className="rounded-lg border border-border bg-card p-4">
                  <div className="text-sm font-medium text-foreground mb-3">{group.title}</div>
                  <div className="space-y-4">
                    {group.paths.map((pathName) => {
                      const sparklineData = getSparklineData(pathName)
                      const currentValues = getCurrentValues(pathName)
                      const { route, spine } = formatPathName(pathName)
                      const trend = getTrend(pathName)
                      
                      return (
                        <div key={pathName} className="space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-muted-foreground">
                              {spine}
                            </span>
                            <div className="flex items-center gap-1">
                              {trend === 'up' && <TrendingUp className="h-3 w-3 text-red-500" />}
                              {trend === 'down' && <TrendingDown className="h-3 w-3 text-green-500" />}
                              {trend === 'stable' && <Minus className="h-3 w-3 text-muted-foreground" />}
                            </div>
                          </div>
                          
                          {/* Mini Sparkline with Axes */}
                          <div className="h-32 w-full">
                            {sparklineData.length > 0 && sparklineData.some(d => d.actual !== null) ? (
                              <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={sparklineData} margin={{ top: 4, right: 4, left: 10, bottom: 3 }}>
                                  <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} opacity={0.5} />
                                  <XAxis 
                                    dataKey="time" 
                                    stroke={colors.axisText}
                                    tick={{ fill: colors.axisText, fontSize: 9 }}
                                    tickLine={{ stroke: colors.axisText }}
                                    interval="preserveStartEnd"
                                    label={{ value: "Time", position: "insideBottom", offset: -2, fill: colors.axisText, fontSize: 9 }}
                                  />
                                  <YAxis 
                                    domain={[0, 'auto']} 
                                    stroke={colors.axisText}
                                    tick={{ fill: colors.axisText, fontSize: 9 }}
                                    tickLine={{ stroke: colors.axisText }}
                                    tickFormatter={(value) => {
                                      // Use 2 decimal places if all values < 1, otherwise use 1 decimal place
                                      const hasValueGeOne = sparklineData.some(d => 
                                        (d.actual !== null && d.actual >= 1) || 
                                        (d.predicted !== null && d.predicted >= 1)
                                      )
                                      return hasValueGeOne ? value.toFixed(1) : value.toFixed(2)
                                    }}
                                    width={30}
                                    label={{ value: "MB", angle: -90, position: "insideLeft", offset: -7, fill: colors.axisText, fontSize: 9 }}
                                  />
                                  <Tooltip
                                    contentStyle={{
                                      backgroundColor: "hsl(var(--card))",
                                      border: "1px solid hsl(var(--border))",
                                      borderRadius: "6px",
                                      padding: "8px 12px",
                                      fontSize: "11px",
                                    }}
                                    labelStyle={{ color: "hsl(var(--foreground))", fontWeight: "bold", marginBottom: "4px" }}
                                    formatter={(value, name) => {
                                      // Skip showing predicted if value is null (iterations 1-9)
                                      if (value === null || value === undefined) {
                                        if (name === "predicted") return null  // Don't show predicted row if null
                                        return ["—", "Actual"]
                                      }
                                      const numValue = typeof value === 'number' ? value : null
                                      if (numValue === null) return null
                                      return [`${numValue.toFixed(2)} MB`, name === "predicted" ? "Predicted" : "Actual"]
                                    }}
                                    labelFormatter={(label) => `Time: ${label}`}
                                  />
                                  {/* Always show actual line (solid) - dots only on hover */}
                                  <Line
                                    type="monotone"
                                    dataKey="actual"
                                    stroke={colors.sparkActual}
                                    strokeWidth={2}
                                    dot={false}
                                    activeDot={{ r: 4, fill: colors.sparkActual }}
                                    connectNulls={true}
                                    isAnimationActive={false}
                                    name="actual"
                                  />
                                  {/* Only show predicted line if we have prediction data (dashed) - dots only on hover */}
                                  {sparklineData.some(d => d.predicted !== null) && (
                                    <Line
                                      type="monotone"
                                      dataKey="predicted"
                                      stroke={colors.sparkPred}
                                      strokeWidth={2}
                                      strokeDasharray="4 2"
                                      dot={false}
                                      activeDot={{ r: 4, fill: colors.sparkPred }}
                                      connectNulls={true}
                                      isAnimationActive={false}
                                      name="predicted"
                                    />
                                  )}
                                </LineChart>
                              </ResponsiveContainer>
                            ) : (
                              <div className="flex items-center justify-center h-full text-xs text-muted-foreground">
                                {sparklineData.length > 0 ? "Collecting data..." : "No data"}
                              </div>
                            )}
                          </div>
                          
                          {/* Values - Only show P: when predicted_mb exists and is not null in actual history data */}
                          <div className="flex justify-between text-xs">
                            {currentValues.predicted_mb !== undefined && currentValues.predicted_mb !== null && pathBandwidthHistory?.history && pathBandwidthHistory.history.length > 0 && (
                              <div>
                                <span className="text-muted-foreground">P:</span>
                                <span className="ml-1 font-medium" style={{ color: colors.sparkPred }}>
                                  {currentValues.predicted_mb.toFixed(2)} MB
                                </span>
                              </div>
                            )}
                            <div className={!(currentValues.predicted_mb !== undefined && currentValues.predicted_mb !== null && pathBandwidthHistory?.history && pathBandwidthHistory.history.length > 0) ? "w-full text-center" : ""}>
                              <span className="text-muted-foreground">A:</span>
                              <span className="ml-1 font-medium" style={{ color: colors.sparkActual }}>
                                {currentValues.actual_mb !== null 
                                  ? `${currentValues.actual_mb.toFixed(2)} MB` 
                                  : '—'}
                              </span>
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
          
          {/* Legend */}
          <div className="mt-4 flex items-center justify-center gap-6 text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <div className="h-2 w-4 rounded" style={{ backgroundColor: colors.sparkPred }} />
              <span>Predicted (TCN)</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-2 w-4 rounded" style={{ backgroundColor: colors.sparkActual }} />
              <span>Actual (Telemetry)</span>
            </div>
            <div className="flex items-center gap-2">
              <TrendingUp className="h-3 w-3 text-red-500" />
              <span>Increasing</span>
            </div>
            <div className="flex items-center gap-2">
              <TrendingDown className="h-3 w-3 text-green-500" />
              <span>Decreasing</span>
            </div>
          </div>
          
          {/* Summary Stats */}
          {pathBandwidthHistory && (
            <div className="mt-4 rounded-lg border border-border bg-secondary/50 p-4">
              <div className="text-xs text-muted-foreground mb-2">Path Bandwidth Summary</div>
              <div className="grid grid-cols-4 gap-4">
                <div>
                  <div className="text-lg font-semibold text-foreground">12</div>
                  <div className="text-xs text-muted-foreground">Total Paths</div>
                </div>
                <div>
                  <div className="text-lg font-semibold text-foreground">
                    {pathBandwidthHistory.history?.length ?? 0}
                  </div>
                  <div className="text-xs text-muted-foreground">History Points</div>
                </div>
                <div>
                  <div className="text-lg font-semibold text-foreground">
                    {pathBandwidthHistory.history_window_minutes ?? 15} min
                  </div>
                  <div className="text-xs text-muted-foreground">Window Size</div>
                </div>
                <div>
                  <div className="text-lg font-semibold text-foreground">60s</div>
                  <div className="text-xs text-muted-foreground">Update Interval</div>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

