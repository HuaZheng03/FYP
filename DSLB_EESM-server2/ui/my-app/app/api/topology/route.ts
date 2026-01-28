import { NextResponse } from "next/server"
import https from "https"

// ONOS Controller configuration
const ONOS_CONTROLLER_IP = process.env.ONOS_CONTROLLER_IP
const USE_HTTPS = process.env.ONOS_USE_HTTPS === "true"
const PROTOCOL = USE_HTTPS ? "https" : "http"
const ONOS_BASE_URL = `${PROTOCOL}://${ONOS_CONTROLLER_IP}:8181/onos/v1`
const ONOS_USERNAME = process.env.ONOS_USERNAME
const ONOS_PASSWORD = process.env.ONOS_PASSWORD

// Map OpenFlow Device IDs to their human-readable names
const DEVICE_ID_TO_NAME: Record<string, string> = {
  "of:000072ecfb3ccb4c": "leaf1",
  "of:000042b1a1405d41": "leaf2",
  "of:000032095cbf1043": "leaf3",
  "of:0000ca44716bdf4b": "leaf6",
  "of:0000d6dee87ca841": "spine1",
  "of:00000ac352fff34c": "spine2",
}

// Create Basic Auth header
const authHeader = `Basic ${Buffer.from(`${ONOS_USERNAME}:${ONOS_PASSWORD}`).toString("base64")}`

const httpsAgent = new https.Agent({
  rejectUnauthorized: false, // Allow self-signed certificates in development
})

interface Device {
  id: string
  type: string
  available: boolean
  role: string
  mfr: string
  hw: string
  sw: string
  serial: string
  driver: string
  chassisId: string
  lastUpdate: number
  humanReadableLastUpdate: string
  annotations: Record<string, string>
  name?: string
}

interface Link {
  src: {
    device: string
    port: string
  }
  dst: {
    device: string
    port: string
  }
  type: string
  state: string
  annotations: Record<string, string>
}

interface Host {
  id: string
  mac: string
  vlan: string
  ipAddresses: string[]
  locations: Array<{
    elementId: string
    port: string
  }>
}

async function fetchDevices(): Promise<Device[]> {
  try {
    console.log("[v0] Fetching devices from:", `${ONOS_BASE_URL}/devices`)

    const fetchOptions: RequestInit = {
      headers: {
        Authorization: authHeader,
      },
      cache: "no-store",
    }

    if (USE_HTTPS) {
      // @ts-ignore - Node.js specific option
      fetchOptions.agent = httpsAgent
    }

    const response = await fetch(`${ONOS_BASE_URL}/devices`, fetchOptions)

    if (!response.ok) {
      const errorText = await response.text()
      console.error("[v0] ONOS devices error:", response.status, errorText)
      throw new Error(`Failed to fetch devices: ${response.statusText}`)
    }

    const contentType = response.headers.get("content-type")
    if (!contentType || !contentType.includes("application/json")) {
      const text = await response.text()
      console.error("[v0] Non-JSON response from ONOS devices:", text)
      throw new Error("ONOS returned non-JSON response")
    }

    const data = await response.json()
    const devices = (data.devices || []).map((device: Device) => ({
      ...device,
      name: DEVICE_ID_TO_NAME[device.id] || device.annotations?.name || device.id,
    }))

    console.log("[v0] Successfully fetched", devices.length, "devices")
    return devices
  } catch (error) {
    console.error("[v0] Error fetching devices:", error)
    return []
  }
}

async function fetchLinks(): Promise<Link[]> {
  try {
    console.log("[v0] Fetching links from:", `${ONOS_BASE_URL}/links`)

    const fetchOptions: RequestInit = {
      headers: {
        Authorization: authHeader,
      },
      cache: "no-store",
    }

    if (USE_HTTPS) {
      // @ts-ignore - Node.js specific option
      fetchOptions.agent = httpsAgent
    }

    const response = await fetch(`${ONOS_BASE_URL}/links`, fetchOptions)

    if (!response.ok) {
      const errorText = await response.text()
      console.error("[v0] ONOS links error:", response.status, errorText)
      throw new Error(`Failed to fetch links: ${response.statusText}`)
    }

    const contentType = response.headers.get("content-type")
    if (!contentType || !contentType.includes("application/json")) {
      const text = await response.text()
      console.error("[v0] Non-JSON response from ONOS links:", text)
      throw new Error("ONOS returned non-JSON response")
    }

    const data = await response.json()
    console.log("[v0] Successfully fetched", data.links?.length || 0, "links")
    return data.links || []
  } catch (error) {
    console.error("[v0] Error fetching links:", error)
    return []
  }
}

async function fetchHosts(): Promise<Host[]> {
  try {
    console.log("[v0] Fetching hosts from:", `${ONOS_BASE_URL}/hosts`)

    const fetchOptions: RequestInit = {
      headers: {
        Authorization: authHeader,
      },
      cache: "no-store",
    }

    if (USE_HTTPS) {
      // @ts-ignore - Node.js specific option
      fetchOptions.agent = httpsAgent
    }

    const response = await fetch(`${ONOS_BASE_URL}/hosts`, fetchOptions)

    if (!response.ok) {
      const errorText = await response.text()
      console.error("[v0] ONOS hosts error:", response.status, errorText)
      throw new Error(`Failed to fetch hosts: ${response.statusText}`)
    }

    const contentType = response.headers.get("content-type")
    if (!contentType || !contentType.includes("application/json")) {
      const text = await response.text()
      console.error("[v0] Non-JSON response from ONOS hosts:", text)
      throw new Error("ONOS returned non-JSON response")
    }

    const data = await response.json()
    console.log("[v0] Successfully fetched", data.hosts?.length || 0, "hosts")
    return data.hosts || []
  } catch (error) {
    console.error("[v0] Error fetching hosts:", error)
    return []
  }
}

export async function GET() {
  try {
    // Fetch all topology data in parallel
    const [devices, links, hosts] = await Promise.all([fetchDevices(), fetchLinks(), fetchHosts()])

    const topologyData = {
      devices,
      links,
      hosts,
      timestamp: new Date().toISOString(),
    }

    return NextResponse.json(topologyData)
  } catch (error) {
    console.error("[v0] Error fetching topology data:", error)
    return NextResponse.json({ error: "Failed to fetch topology data from ONOS controller" }, { status: 500 })
  }
}
