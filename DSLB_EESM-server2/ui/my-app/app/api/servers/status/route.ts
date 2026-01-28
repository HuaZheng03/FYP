import { NextResponse } from "next/server"
import { readFile } from "fs/promises"

interface ServerStatus {
  name: string
  ip: string
  active: boolean
  draining: boolean
  healthy: boolean
}

export async function GET() {
  try {
    const filePath = "/home/huazheng/DSLB_EESM/local_active_servers_status.json"

    const fileContent = await readFile(filePath, "utf-8")
    const statusData: Record<string, ServerStatus> = JSON.parse(fileContent)

    // Only count servers where active=true, draining=false, AND healthy=true
    const activeServers = Object.values(statusData).filter(
      (server) => server.active === true && server.draining === false && server.healthy === true,
    )

    return NextResponse.json({
      success: true,
      servers: statusData,
      activeServers,
      timestamp: new Date().toISOString(),
    })
  } catch (error) {
    console.error("[v0] Error reading server status file:", error)
    return NextResponse.json(
      {
        success: false,
        error: "Failed to read server status file",
        servers: {},
        activeServers: [],
      },
      { status: 500 },
    )
  }
}
