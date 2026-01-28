import fs from "fs"

const PROMETHEUS_URL = process.env.PROMETHEUS_URL || "http://192.168.126.2:9090"
const SERVER_STATUS_FILE_PATH =
  process.env.SERVER_STATUS_FILE_PATH || "/home/huazheng/DSLB_EESM/local_active_servers_status.json"

interface ServerMetrics {
  ip: string
  name: string
  cpu: number
  memory: number
  rps: number
  totalMemory: number
  totalCpuCores: number
  status: "active" | "inactive"
}

async function queryPrometheus(query: string): Promise<any> {
  try {
    const url = `${PROMETHEUS_URL}/api/v1/query?query=${encodeURIComponent(query)}`
    const response = await fetch(url, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
    })

    if (!response.ok) {
      return []
    }

    const data = await response.json()
    return data.data?.result || []
  } catch (error) {
    console.error("[v0] Error querying Prometheus:", error)
    return []
  }
}

export async function getServerTelemetry(): Promise<{ servers: ServerMetrics[]; activeServers: any[] }> {
  try {
    // Read server status from JSON file
    let allServers: any[] = []
    let activeServerIps: Set<string> = new Set()

    try {
      const fileContent = fs.readFileSync(SERVER_STATUS_FILE_PATH, "utf-8")
      const statusData = JSON.parse(fileContent)
      allServers = Object.values(statusData)
      // Only include servers where active=true, draining=false, AND healthy=true
      activeServerIps = new Set(
        Object.values(statusData)
          .filter((s: any) => s.active === true && s.draining === false && s.healthy === true)
          .map((s: any) => s.ip),
      )
    } catch (fileError) {
      console.error("[v0] Error reading server status file:", fileError)
      // Return empty data if file doesn't exist
      return { servers: [], activeServers: [] }
    }

    // PromQL queries
    const memUsageQuery = "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100"
    const cpuUsageQuery = 'avg by (instance) ((1 - rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)'
    const rpsQuery = "rate(apache_accesses_total[1m])"
    const totalMemQuery = "node_memory_MemTotal_bytes"
    const totalCpuQuery = 'count(node_cpu_seconds_total{mode="idle"}) by (instance)'

    const [cpuData, memData, rpsData, totalMemData, totalCpuData] = await Promise.all([
      queryPrometheus(cpuUsageQuery),
      queryPrometheus(memUsageQuery),
      queryPrometheus(rpsQuery),
      queryPrometheus(totalMemQuery),
      queryPrometheus(totalCpuQuery),
    ])

    // Create a map of IP to metrics
    const metricsMap = new Map<
      string,
      { cpu?: number; memory?: number; rps?: number; totalMemory?: number; totalCpuCores?: number }
    >()

    // Process metrics
    cpuData.forEach((result: any) => {
      const ip = result.metric.instance.split(":")[0]
      if (!metricsMap.has(ip)) metricsMap.set(ip, {})
      metricsMap.get(ip)!.cpu = Number.parseFloat(result.value[1])
    })

    memData.forEach((result: any) => {
      const ip = result.metric.instance.split(":")[0]
      if (!metricsMap.has(ip)) metricsMap.set(ip, {})
      metricsMap.get(ip)!.memory = Number.parseFloat(result.value[1])
    })

    rpsData.forEach((result: any) => {
      const ip = result.metric.instance.split(":")[0]
      if (!metricsMap.has(ip)) metricsMap.set(ip, {})
      metricsMap.get(ip)!.rps = Number.parseFloat(result.value[1])
    })

    totalMemData.forEach((result: any) => {
      const ip = result.metric.instance.split(":")[0]
      if (!metricsMap.has(ip)) metricsMap.set(ip, {})
      metricsMap.get(ip)!.totalMemory = Number.parseFloat(result.value[1])
    })

    totalCpuData.forEach((result: any) => {
      const ip = result.metric.instance.split(":")[0]
      if (!metricsMap.has(ip)) metricsMap.set(ip, {})
      metricsMap.get(ip)!.totalCpuCores = Number.parseFloat(result.value[1])
    })

    const serverMetrics: ServerMetrics[] = allServers.map((server: any) => {
      const metrics = metricsMap.get(server.ip)
      const hasMetrics = metrics && metrics.cpu !== undefined && metrics.memory !== undefined
      const isActive = activeServerIps.has(server.ip) && hasMetrics

      return {
        ip: server.ip,
        name: server.name,
        cpu: hasMetrics ? metrics.cpu! : 0,
        memory: hasMetrics ? metrics.memory! : 0,
        rps: metrics?.rps || 0,
        totalMemory: metrics?.totalMemory || 0,
        totalCpuCores: metrics?.totalCpuCores || 0,
        status: isActive ? "active" : "inactive",
      }
    })

    const activeServers = serverMetrics.filter((s) => s.status === "active")

    return { servers: serverMetrics, activeServers }
  } catch (error) {
    console.error("[v0] Error in getServerTelemetry:", error)
    return { servers: [], activeServers: [] }
  }
}
