import { NextResponse } from "next/server"
import { getServerTelemetry } from "@/lib/server-telemetry"

// DWRS Algorithm Configuration
const ALPHA = 0.55 // Weight for CPU
const BETA = 0.45 // Weight for Memory

interface ServerWithWeight {
  ip: string
  name: string
  cpu: number
  memory: number
  rps: number
  totalMemory: number
  totalCpuCores: number
  status: "active" | "inactive"
  comprehensiveLoad: number
  dynamicWeight: number
}

function calculateComprehensiveLoad(cpu: number, memory: number): number {
  return cpu * ALPHA + memory * BETA
}

function convertLoadToWeight(load: number): number {
  if (load >= 100) return 1
  return 100 - Math.floor(load)
}

export async function GET() {
  try {
    const { servers } = await getServerTelemetry()

    const serversWithWeights: ServerWithWeight[] = servers.map((server: any) => {
      if (server.status === "inactive") {
        return {
          ...server,
          rps: 0,
          totalMemory: 0,
          totalCpuCores: 0,
          comprehensiveLoad: 0,
          dynamicWeight: 0,
        }
      }

      const load = calculateComprehensiveLoad(server.cpu, server.memory)
      const weight = convertLoadToWeight(load)

      return {
        ...server,
        rps: server.rps || 0,
        totalMemory: server.totalMemory || 0,
        totalCpuCores: server.totalCpuCores || 0,
        comprehensiveLoad: Math.round(load * 100) / 100,
        dynamicWeight: weight,
      }
    })

    // Calculate total weight for active servers
    const totalWeight = serversWithWeights
      .filter((s) => s.status === "active")
      .reduce((sum: number, s) => sum + s.dynamicWeight, 0)

    // Select target server using DWRS algorithm
    let selectedServer = null
    const activeServers = serversWithWeights.filter((s) => s.status === "active")

    if (activeServers.length === 1) {
      selectedServer = activeServers[0]
    } else if (activeServers.length > 1 && totalWeight > 0) {
      const randomPick = Math.floor(Math.random() * totalWeight) + 1
      let cumulativeWeight = 0

      for (const server of activeServers) {
        cumulativeWeight += server.dynamicWeight
        if (cumulativeWeight >= randomPick) {
          selectedServer = server
          break
        }
      }
    }

    return NextResponse.json({
      success: true,
      servers: serversWithWeights,
      totalWeight,
      selectedServer,
      algorithm: {
        name: "Dynamic Weight Random Selection (DWRS)",
        alpha: ALPHA,
        beta: BETA,
      },
      timestamp: new Date().toISOString(),
    })
  } catch (error) {
    console.error("Error calculating server weights:", error)
    return NextResponse.json(
      {
        success: false,
        error: "Failed to calculate server weights",
      },
      { status: 500 },
    )
  }
}



