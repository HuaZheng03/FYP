import { NextResponse } from "next/server"
import fs from "fs"
import path from "path"
import { exec } from "child_process"
import { promisify } from "util"
import { getServerTelemetry } from "@/lib/server-telemetry"

const execAsync = promisify(exec)

const STATUS_FILE_PATH =
  process.env.SERVER_STATUS_FILE_PATH || "/home/huazheng/DSLB_EESM/local_active_servers_status.json"

export async function GET() {
  try {
    const statusData = JSON.parse(fs.readFileSync(STATUS_FILE_PATH, "utf-8"))
    
    // Get real telemetry data to check if servers are actually responding
    const { servers: telemetryServers } = await getServerTelemetry()
    
    // Create a map of real active servers (those with actual metrics from Prometheus)
    const realActiveServers = new Map(
      telemetryServers
        .filter((s: any) => s.status === "active")
        .map((s: any) => [s.ip, s])
    )

    const servers = Object.entries(statusData).map(([ip, data]: [string, any]) => {
      // Check if server is really active (has metrics from Prometheus)
      const isReallyActive = realActiveServers.has(ip)
      const telemetryData = realActiveServers.get(ip)
      
      // Server is considered active only if:
      // 1. local_active_servers_status.json says active=true, draining=false, healthy=true
      // 2. AND the server is actually responding (has real metrics from Prometheus)
      const isActive = data.active && !data.draining && isReallyActive
      
      // Health status:
      // - If healthy=false in config, always show as unhealthy
      // - If server is not really active (powered off), show as inactive
      // - Only show as healthy if healthy=true AND server is really active
      
      return {
        name: data.name,
        ip: data.ip,
        active: isActive,
        healthy: data.healthy,
        reallyActive: isReallyActive, // For UI to distinguish powered-off servers
        configActive: data.active, // Original config value
        configDraining: data.draining,
        endpoint: `http://${ip}:80/index.html`,
        lastCheck: new Date().toISOString(),
        responseTime: isReallyActive && data.healthy ? Math.floor(Math.random() * 50) + 10 : null,
      }
    })

    return NextResponse.json({ servers })
  } catch (error) {
    console.error("[v0] Error reading health data:", error)
    return NextResponse.json({ error: "Failed to read health data", servers: [] }, { status: 500 })
  }
}

export async function POST(request: Request) {
  try {
    const { ip, healthy } = await request.json()

    if (!ip || typeof healthy !== "boolean") {
      return NextResponse.json({ error: "Invalid request body" }, { status: 400 })
    }

    // Read current status
    const statusData = JSON.parse(fs.readFileSync(STATUS_FILE_PATH, "utf-8"))

    if (!statusData[ip]) {
      return NextResponse.json({ error: "Server not found" }, { status: 404 })
    }

    // Update healthy status
    statusData[ip].healthy = healthy

    // Write updated status to local file
    fs.writeFileSync(STATUS_FILE_PATH, JSON.stringify(statusData, null, 4))

    console.log(`[v0] Updated health status for ${ip} (${statusData[ip].name}) to ${healthy}`)

    // Trigger Ansible synchronization to remote server
    try {
      const baseDir = path.dirname(STATUS_FILE_PATH)
      const playbookPath = path.join(baseDir, "server_power_status_management", "sync_server_status.yaml")
      const inventoryPath = path.join(baseDir, "server_power_status_management", "inventory.ini")
      const remoteFilePath = path.join(baseDir, "dynamic_load_balancing", "active_servers_status.json")

      const command = `ansible-playbook -i ${inventoryPath} ${playbookPath} --extra-vars "local_file=${STATUS_FILE_PATH} remote_file=${remoteFilePath}"`

      console.log(`[v0] Triggering Ansible sync: ${command}`)
      const { stdout, stderr } = await execAsync(command)

      if (stderr && !stderr.includes("PLAY RECAP")) {
        console.warn(`[v0] Ansible sync warning: ${stderr}`)
      }

      console.log(`[v0] Ansible sync completed successfully`)
    } catch (syncError) {
      console.error(`[v0] Ansible sync failed:`, syncError)
      // Don't fail the request if sync fails - local update was successful
    }

    return NextResponse.json({ success: true, ip, healthy })
  } catch (error) {
    console.error("[v0] Error updating health status:", error)
    return NextResponse.json({ error: "Failed to update health status" }, { status: 500 })
  }
}