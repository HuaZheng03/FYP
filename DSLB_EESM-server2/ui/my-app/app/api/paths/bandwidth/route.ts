import { NextResponse } from "next/server"
import https from "https"

// ONOS Controller configuration
const ONOS_CONTROLLER_IP = process.env.ONOS_CONTROLLER_IP || "192.168.126.1"
const USE_HTTPS = process.env.ONOS_USE_HTTPS === "true"
const PROTOCOL = USE_HTTPS ? "https" : "http"
const ONOS_BASE_URL = `${PROTOCOL}://${ONOS_CONTROLLER_IP}:8181/onos/v1`
const ONOS_USERNAME = process.env.ONOS_USERNAME || ""
const ONOS_PASSWORD = process.env.ONOS_PASSWORD || ""

// Create Basic Auth header
const authHeader = `Basic ${Buffer.from(`${ONOS_USERNAME}:${ONOS_PASSWORD}`).toString("base64")}`

const httpsAgent = new https.Agent({
  rejectUnauthorized: false,
})

// Device ID mappings
const DEVICE_IDS: Record<string, string> = {
  leaf1: "of:000072ecfb3ccb4c",
  leaf2: "of:000042b1a1405d41",
  leaf3: "of:000032095cbf1043",
  leaf6: "of:0000ca44716bdf4b",
  spine1: "of:0000d6dee87ca841",
  spine2: "of:00000ac352fff34c",
}

// Path definitions - each pair has 2 paths (via spine1 and spine2)
const AVAILABLE_PATHS: Record<string, Array<Array<[string, string]>>> = {
  "leaf1-leaf6": [
    [
      [DEVICE_IDS["leaf1"], "1"],
      [DEVICE_IDS["spine1"], "2"],
    ],
    [
      [DEVICE_IDS["leaf1"], "5"],
      [DEVICE_IDS["spine2"], "4"],
    ],
  ],
  "leaf1-leaf2": [
    [
      [DEVICE_IDS["leaf1"], "1"],
      [DEVICE_IDS["spine1"], "3"],
    ],
    [
      [DEVICE_IDS["leaf1"], "5"],
      [DEVICE_IDS["spine2"], "2"],
    ],
  ],
  "leaf1-leaf3": [
    [
      [DEVICE_IDS["leaf1"], "1"],
      [DEVICE_IDS["spine1"], "4"],
    ],
    [
      [DEVICE_IDS["leaf1"], "5"],
      [DEVICE_IDS["spine2"], "3"],
    ],
  ],
  "leaf2-leaf3": [
    [
      [DEVICE_IDS["leaf2"], "3"],
      [DEVICE_IDS["spine1"], "4"],
    ],
    [
      [DEVICE_IDS["leaf2"], "1"],
      [DEVICE_IDS["spine2"], "3"],
    ],
  ],
  "leaf2-leaf6": [
    [
      [DEVICE_IDS["leaf2"], "3"],
      [DEVICE_IDS["spine1"], "2"],
    ],
    [
      [DEVICE_IDS["leaf2"], "1"],
      [DEVICE_IDS["spine2"], "4"],
    ],
  ],
  "leaf3-leaf6": [
    [
      [DEVICE_IDS["leaf3"], "1"],
      [DEVICE_IDS["spine1"], "2"],
    ],
    [
      [DEVICE_IDS["leaf3"], "2"],
      [DEVICE_IDS["spine2"], "4"],
    ],
  ],
}

// Store previous statistics for rate calculation
let previousStats: Record<string, Record<string, any>> = {}
let lastFetchTime = 0

async function fetchPortStats(deviceId: string): Promise<Record<string, any>> {
  const url = `${ONOS_BASE_URL}/statistics/ports/${deviceId}`
  const options: any = {
    headers: {
      Authorization: authHeader,
    },
    cache: "no-store",
  }

  if (USE_HTTPS) {
    options.agent = httpsAgent
  }

  try {
    const response = await fetch(url, options)
    if (!response.ok) {
      console.error(`Failed to fetch stats for ${deviceId}: ${response.statusText}`)
      return {}
    }

    const data = await response.json()
    const portStats: Record<string, any> = {}

    for (const statBlock of data.statistics || []) {
      for (const portStat of statBlock.ports || []) {
        const port = String(portStat.port)
        portStats[port] = {
          bytesSent: portStat.bytesSent || 0,
          bytesReceived: portStat.bytesReceived || 0,
        }
      }
    }

    return portStats
  } catch (error) {
    console.error(`Error fetching stats for ${deviceId}:`, error)
    return {}
  }
}

function calculatePathBandwidth(
  currentStats: Record<string, Record<string, any>>,
  timeDelta: number,
): Record<string, Array<any>> {
  const pathBandwidth: Record<string, Array<any>> = {}

  for (const [pairKey, paths] of Object.entries(AVAILABLE_PATHS)) {
    pathBandwidth[pairKey] = []

    paths.forEach((path, pathIndex) => {
      let totalTxRate = 0
      let totalRxRate = 0
      let hopCount = 0

      // Calculate bandwidth for each hop in the path
      for (const [deviceId, port] of path) {
        const deviceName = Object.keys(DEVICE_IDS).find((key) => DEVICE_IDS[key] === deviceId)
        if (!deviceName || !currentStats[deviceName] || !currentStats[deviceName][port]) {
          continue
        }

        const currentPort = currentStats[deviceName][port]
        const previousPort = previousStats[deviceName]?.[port]

        if (previousPort && timeDelta > 0) {
          const txRate = (currentPort.bytesSent - previousPort.bytesSent) / timeDelta
          const rxRate = (currentPort.bytesReceived - previousPort.bytesReceived) / timeDelta

          totalTxRate += Math.max(0, txRate)
          totalRxRate += Math.max(0, rxRate)
          hopCount++
        }
      }

      // Average bandwidth across hops
      const avgTxRate = hopCount > 0 ? totalTxRate / hopCount : 0
      const avgRxRate = hopCount > 0 ? totalRxRate / hopCount : 0

      // Determine path name based on which spine it uses
      const spineUsed = path.some(([deviceId]) => deviceId === DEVICE_IDS["spine1"]) ? "spine1" : "spine2"

      pathBandwidth[pairKey].push({
        pathIndex,
        pathName: `Path ${pathIndex + 1} (via ${spineUsed})`,
        txBytesPerSec: avgTxRate,
        rxBytesPerSec: avgRxRate,
        totalBytesPerSec: avgTxRate + avgRxRate,
        txMbps: (avgTxRate * 8) / (1024 * 1024),
        rxMbps: (avgRxRate * 8) / (1024 * 1024),
        totalMbps: ((avgTxRate + avgRxRate) * 8) / (1024 * 1024),
        utilizationPercent: (((avgTxRate + avgRxRate) * 8) / (1024 * 1024) / 500) * 100, // Assuming 500 Mbps links
      })
    })
  }

  return pathBandwidth
}

export async function GET() {
  try {
    const currentTime = Date.now() / 1000
    const timeDelta = lastFetchTime > 0 ? currentTime - lastFetchTime : 5

    // Fetch current statistics for all devices
    const currentStats: Record<string, Record<string, any>> = {}

    for (const [deviceName, deviceId] of Object.entries(DEVICE_IDS)) {
      currentStats[deviceName] = await fetchPortStats(deviceId)
    }

    // Calculate path bandwidth
    const pathBandwidth = calculatePathBandwidth(currentStats, timeDelta)

    // Update previous stats and time
    previousStats = currentStats
    lastFetchTime = currentTime

    return NextResponse.json({
      success: true,
      timestamp: new Date().toISOString(),
      paths: pathBandwidth,
    })
  } catch (error) {
    console.error("Error calculating path bandwidth:", error)
    return NextResponse.json(
      {
        success: false,
        error: "Failed to calculate path bandwidth",
        paths: {},
      },
      { status: 500 },
    )
  }
}
