import { NextResponse } from "next/server"
import { getServerTelemetry } from "@/lib/server-telemetry"

// Prometheus configuration
const PROMETHEUS_URL = process.env.PROMETHEUS_URL || "http://192.168.126.2:9090"

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
    console.log("[v0] Querying Prometheus:", url)

    const response = await fetch(url, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
    })

    if (!response.ok) {
      const errorText = await response.text()
      console.error("[v0] Prometheus error:", response.status, errorText)
      throw new Error(`Prometheus query failed: ${response.statusText}`)
    }

    const contentType = response.headers.get("content-type")
    if (!contentType || !contentType.includes("application/json")) {
      const text = await response.text()
      console.error("[v0] Non-JSON response from Prometheus:", text)
      throw new Error("Prometheus returned non-JSON response")
    }

    const data = await response.json()
    console.log("[v0] Prometheus query returned", data.data?.result?.length || 0, "results")
    return data.data?.result || []
  } catch (error) {
    console.error("[v0] Error querying Prometheus:", error)
    return []
  }
}

export async function GET() {
  try {
    const { servers } = await getServerTelemetry()

    return NextResponse.json({
      success: true,
      servers,
      timestamp: new Date().toISOString(),
    })
  } catch (error) {
    console.error("[v0] Error fetching server telemetry:", error)
    return NextResponse.json(
      {
        success: false,
        error: "Failed to fetch server telemetry",
        servers: [],
      },
      { status: 200 },
    )
  }
}



