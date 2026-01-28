"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Network, Server, RefreshCw } from "lucide-react"
import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { useTheme } from "next-themes"

interface Device {
  id: string
  type: string
  available: boolean
  role: string
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
}

interface Host {
  id: string
  mac: string
  ipAddresses: string[]
  locations: Array<{
    elementId: string
    port: string
  }>
}

interface TopologyData {
  devices: Device[]
  links: Link[]
  hosts: Host[]
  timestamp: string
}

interface ProcessedSwitch {
  id: string
  displayName: string
  status: string
  load: number
  connections: number
  type: "spine" | "leaf"
}

interface ProcessedHost {
  id: string
  name: string
  ip: string
  mac: string
  connectedTo: string
}

// Host name mapping based on MAC addresses
const HOST_NAMES: Record<string, string> = {
  "1A:94:F6:54:93:19": "Gateway",
  "52:54:00:40:96:B5": "ubuntu-guest",
  "52:54:00:66:F0:ED": "apache-vm-1",
  "52:54:00:A4:CD:19": "apache-vm-2",
}

export function SpineLeafTopology() {
  const { resolvedTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  const [topology, setTopology] = useState<TopologyData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [spineLayer, setSpineLayer] = useState<ProcessedSwitch[]>([])
  const [leafLayer, setLeafLayer] = useState<ProcessedSwitch[]>([])
  const [hosts, setHosts] = useState<ProcessedHost[]>([])

  useEffect(() => {
    setMounted(true)
  }, [])

  // Theme-aware colors
  const isDark = mounted && resolvedTheme === 'dark'
  const svgBgColor = isDark ? '#1f2937' : '#ffffff'  // gray-800 for dark, white for light
  const textPrimaryColor = isDark ? '#f9fafb' : '#1f2937'  // gray-50 for dark, gray-800 for light
  const textSecondaryColor = isDark ? '#9ca3af' : '#6b7280'  // gray-400 for dark, gray-500 for light
  const nodesBgColor = isDark ? '#374151' : '#ffffff'  // gray-700 for dark, white for light

  const fetchTopology = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch("/api/topology")
      if (!response.ok) {
        throw new Error("Failed to fetch topology")
      }
      const data: TopologyData = await response.json()
      setTopology(data)
      processTopologyData(data)
    } catch (err) {
      console.error("[v0] Error fetching topology:", err)
      setError("Unable to connect to ONOS controller")
    } finally {
      setLoading(false)
    }
  }

  const processTopologyData = (data: TopologyData) => {
    // Process devices into spine and leaf switches
    const spines: ProcessedSwitch[] = []
    const leaves: ProcessedSwitch[] = []

    data.devices.forEach((device) => {
      const deviceName = device.name || device.id
      const isSpine = deviceName.toLowerCase().includes("spine")

      // Count connections
      const connections = data.links.filter(
        (link) => link.src.device === device.id || link.dst.device === device.id,
      ).length

      const processedSwitch: ProcessedSwitch = {
        id: device.id,
        displayName: deviceName,
        status: device.available ? "active" : "inactive",
        load: 0, // Set to 0 as we're not displaying load anymore
        connections,
        type: isSpine ? "spine" : "leaf",
      }

      if (isSpine) {
        spines.push(processedSwitch)
      } else {
        leaves.push(processedSwitch)
      }
    })

    setSpineLayer(spines)
    setLeafLayer(leaves)

    // Process hosts
    const processedHosts: ProcessedHost[] = data.hosts.map((host) => {
      const macUpper = host.mac.toUpperCase()
      const hostName = HOST_NAMES[macUpper] || "Unknown Host"
      
      return {
        id: host.id,
        name: hostName,
        ip: host.ipAddresses[0] || "N/A",
        mac: host.mac,
        connectedTo: host.locations[0]?.elementId || "Unknown",
      }
    })
    setHosts(processedHosts)
  }

  useEffect(() => {
    fetchTopology()
    // Refresh topology every 10 seconds
    const interval = setInterval(fetchTopology, 10000)
    return () => clearInterval(interval)
  }, [])

  if (loading && !topology) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>2-Tier Spine-Leaf Network Topology</CardTitle>
          <CardDescription>Loading topology from ONOS controller...</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-12">
            <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>2-Tier Spine-Leaf Network Topology</CardTitle>
          <CardDescription className="text-destructive">{error}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center gap-4 py-12">
            <p className="text-sm text-muted-foreground">Check ONOS controller connection</p>
            <Button onClick={fetchTopology} variant="outline" size="sm">
              <RefreshCw className="mr-2 h-4 w-4" />
              Retry
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  // Calculate actual link count based on topology
  // Links = (spine-leaf connections) + (leaf-host connections)
  const calculateLinkCount = () => {
    // Spine-Leaf links: each spine connects to each leaf
    const spineLeafLinks = spineLayer.length * leafLayer.length
    // Leaf-Host links: count actual connected hosts
    const leafHostLinks = hosts.length
    return spineLeafLinks + leafHostLinks
  }

  const totalLinks = calculateLinkCount()

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>2-Tier Spine-Leaf Network Topology</CardTitle>
            <CardDescription>Live data from ONOS SDN Controller</CardDescription>
          </div>
          <Button onClick={fetchTopology} variant="outline" size="sm" disabled={loading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {/* Topology Stats */}
        <div className="mb-6 grid grid-cols-4 gap-4">
          <div className="rounded-lg border border-border bg-secondary/30 p-3 text-center">
            <div className="text-2xl font-bold" style={{ color: '#ea580c' }}>{spineLayer.length}</div>
            <div className="text-xs text-muted-foreground">Spine Switches</div>
          </div>
          <div className="rounded-lg border border-border bg-secondary/30 p-3 text-center">
            <div className="text-2xl font-bold" style={{ color: '#14b8a6' }}>{leafLayer.length}</div>
            <div className="text-xs text-muted-foreground">Leaf Switches</div>
          </div>
          <div className="rounded-lg border border-border bg-secondary/30 p-3 text-center">
            <div className="text-2xl font-bold" style={{ color: '#3b82f6' }}>{hosts.length}</div>
            <div className="text-xs text-muted-foreground">Hosts</div>
          </div>
          <div className="rounded-lg border border-border bg-secondary/30 p-3 text-center">
            <div className="text-2xl font-bold text-foreground">{totalLinks}</div>
            <div className="text-xs text-muted-foreground">Links</div>
          </div>
        </div>

        {/* SVG Topology Diagram */}
        <div className="relative rounded-lg border border-border p-8" style={{ minHeight: "750px", backgroundColor: svgBgColor }}>
          <svg width="100%" height="750" viewBox="0 0 1200 750" preserveAspectRatio="xMidYMid meet" className="overflow-visible">
            <defs>
              <linearGradient id="spineLeafGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#ea580c" stopOpacity="0.8" />
                <stop offset="100%" stopColor="#14b8a6" stopOpacity="0.8" />
              </linearGradient>
              <linearGradient id="leafHostGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#14b8a6" stopOpacity="0.8" />
                <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.8" />
              </linearGradient>
              <filter id="glow">
                <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
                <feMerge>
                  <feMergeNode in="coloredBlur"/>
                  <feMergeNode in="SourceGraphic"/>
                </feMerge>
              </filter>
            </defs>

            {/* Draw connections between spine and leaf */}
            {spineLayer.map((spine, spineIdx) => {
              const spineX = 400 + spineIdx * 400
              const spineY = 200
              return leafLayer.map((leaf, leafIdx) => {
                const leafX = 250 + leafIdx * 230
                const leafY = 410
                return (
                  <line
                    key={`spine-leaf-${spineIdx}-${leafIdx}`}
                    x1={spineX}
                    y1={spineY + 50}
                    x2={leafX}
                    y2={leafY - 40}
                    stroke="url(#spineLeafGradient)"
                    strokeWidth="2.5"
                    opacity="0.9"
                  />
                )
              })
            })}

            {/* Draw connections between leaf and hosts */}
            {leafLayer.map((leaf, leafIdx) => {
              const leafX = 250 + leafIdx * 230
              const leafY = 410
              const connectedHosts = hosts.filter((h) => h.connectedTo === leaf.id)
              return connectedHosts.map((host, hostIdx) => {
                const hostX = leafX
                const hostY = 650
                return (
                  <g key={`leaf-host-${leafIdx}-${hostIdx}`}>
                    {/* Main connection line */}
                    <line
                      x1={leafX}
                      y1={leafY + 40}
                      x2={hostX}
                      y2={hostY - 40}
                      stroke="#14b8a6"
                      strokeWidth="3"
                      opacity="0.8"
                    />
                    {/* Gradient overlay line */}
                    <line
                      x1={leafX}
                      y1={leafY + 40}
                      x2={hostX}
                      y2={hostY - 40}
                      stroke="url(#leafHostGradient)"
                      strokeWidth="2.5"
                      opacity="0.9"
                    />
                  </g>
                )
              })
            })}

            {/* Layer Labels */}
            <text x="40" y="140" fill={textSecondaryColor} fontSize="14" fontWeight="700" letterSpacing="0.5">
              SPINE LAYER ({spineLayer.length} Switches)
            </text>
            <rect x="30" y="145" width="220" height="2" fill="#ea580c" opacity="0.6" rx="1" />

            <text x="40" y="350" fill={textSecondaryColor} fontSize="14" fontWeight="700" letterSpacing="0.5">
              LEAF LAYER ({leafLayer.length} Switches)
            </text>
            <rect x="30" y="355" width="220" height="2" fill="#14b8a6" opacity="0.6" rx="1" />

            <text x="40" y="590" fill={textSecondaryColor} fontSize="14" fontWeight="700" letterSpacing="0.5">
              HOST LAYER ({hosts.length} Hosts)
            </text>
            <rect x="30" y="595" width="220" height="2" fill="#3b82f6" opacity="0.6" rx="1" />

            {/* Spine Layer Switches */}
            {spineLayer.map((spine, idx) => {
              const x = 400 + idx * 400
              const y = 200
              return (
                <g key={spine.id} style={{ cursor: "pointer" }}>
                  {/* Switch Container - Theme-aware background */}
                  <rect
                    x={x - 60}
                    y={y - 50}
                    width="120"
                    height="100"
                    rx="12"
                    fill={nodesBgColor}
                    stroke={spine.status === "active" ? "#ea580c" : "#9ca3af"}
                    strokeWidth="3"
                    filter="url(#glow)"
                  />
                  {/* Icon Background Circle */}
                  <circle
                    cx={x}
                    cy={y - 10}
                    r="20"
                    fill={spine.status === "active" ? "#ea580c" : "#9ca3af"}
                    opacity="0.15"
                  />
                  {/* Network Icon - Outer Ring */}
                  <circle
                    cx={x}
                    cy={y - 10}
                    r="14"
                    fill="none"
                    stroke={spine.status === "active" ? "#ea580c" : "#9ca3af"}
                    strokeWidth="2.5"
                  />
                  {/* Network Icon - Dots */}
                  <circle cx={x - 7} cy={y - 10} r="2.5" fill={spine.status === "active" ? "#ea580c" : "#9ca3af"} />
                  <circle cx={x + 7} cy={y - 10} r="2.5" fill={spine.status === "active" ? "#ea580c" : "#9ca3af"} />
                  <circle cx={x} cy={y - 3} r="2.5" fill={spine.status === "active" ? "#ea580c" : "#9ca3af"} />
                  <circle cx={x} cy={y - 17} r="2.5" fill={spine.status === "active" ? "#ea580c" : "#9ca3af"} />
                  
                  {/* Switch Name - Theme-aware text */}
                  <text x={x} y={y + 28} textAnchor="middle" fill={textPrimaryColor} fontSize="15" fontWeight="700">
                    {spine.displayName}
                  </text>
                  {/* Status Badge */}
                  <rect
                    x={x - 28}
                    y={y + 35}
                    width="56"
                    height="18"
                    rx="9"
                    fill={spine.status === "active" ? "#ea580c" : "#9ca3af"}
                    opacity="0.2"
                  />
                  <text x={x} y={y + 47} textAnchor="middle" fill={spine.status === "active" ? "#ea580c" : textSecondaryColor} fontSize="11" fontWeight="600">
                    {spine.status}
                  </text>
                </g>
              )
            })}

            {/* Leaf Layer Switches */}
            {leafLayer.map((leaf, idx) => {
              const x = 250 + idx * 230
              const y = 410
              return (
                <g key={leaf.id} style={{ cursor: "pointer" }}>
                  {/* Switch Container - Theme-aware background */}
                  <rect
                    x={x - 50}
                    y={y - 40}
                    width="100"
                    height="80"
                    rx="10"
                    fill={nodesBgColor}
                    stroke={leaf.status === "active" ? "#14b8a6" : "#9ca3af"}
                    strokeWidth="2.5"
                    filter="url(#glow)"
                  />
                  {/* Icon Background Circle */}
                  <circle
                    cx={x}
                    cy={y - 8}
                    r="16"
                    fill={leaf.status === "active" ? "#14b8a6" : "#9ca3af"}
                    opacity="0.15"
                  />
                  {/* Network Icon - Outer Ring */}
                  <circle
                    cx={x}
                    cy={y - 8}
                    r="11"
                    fill="none"
                    stroke={leaf.status === "active" ? "#14b8a6" : "#9ca3af"}
                    strokeWidth="2"
                  />
                  {/* Network Icon - Dots */}
                  <circle cx={x - 5} cy={y - 8} r="2" fill={leaf.status === "active" ? "#14b8a6" : "#9ca3af"} />
                  <circle cx={x + 5} cy={y - 8} r="2" fill={leaf.status === "active" ? "#14b8a6" : "#9ca3af"} />
                  <circle cx={x} cy={y - 2} r="2" fill={leaf.status === "active" ? "#14b8a6" : "#9ca3af"} />
                  <circle cx={x} cy={y - 14} r="2" fill={leaf.status === "active" ? "#14b8a6" : "#9ca3af"} />
                  
                  {/* Switch Name - Theme-aware text */}
                  <text x={x} y={y + 20} textAnchor="middle" fill={textPrimaryColor} fontSize="14" fontWeight="700">
                    {leaf.displayName}
                  </text>
                  {/* Status Badge */}
                  <rect
                    x={x - 24}
                    y={y + 26}
                    width="48"
                    height="16"
                    rx="8"
                    fill={leaf.status === "active" ? "#14b8a6" : "#9ca3af"}
                    opacity="0.2"
                  />
                  <text x={x} y={y + 37} textAnchor="middle" fill={leaf.status === "active" ? "#14b8a6" : textSecondaryColor} fontSize="10" fontWeight="600">
                    {leaf.status}
                  </text>
                </g>
              )
            })}

            {/* Host Layer */}
            {leafLayer.map((leaf, leafIdx) => {
              const leafX = 250 + leafIdx * 230
              const connectedHosts = hosts.filter((h) => h.connectedTo === leaf.id)
              return connectedHosts.map((host, hostIdx) => {
                const x = leafX
                const y = 650
                return (
                  <g key={host.id} style={{ cursor: "pointer" }}>
                    {/* Host Container - Theme-aware background */}
                    <rect
                      x={x - 45}
                      y={y - 35}
                      width="90"
                      height="75"
                      rx="8"
                      fill={nodesBgColor}
                      stroke="#3b82f6"
                      strokeWidth="2.5"
                      filter="url(#glow)"
                    />
                    {/* Icon Background Rectangle */}
                    <rect
                      x={x - 18}
                      y={y - 18}
                      width="36"
                      height="24"
                      rx="3"
                      fill="#3b82f6"
                      opacity="0.15"
                    />
                    {/* Server Icon - 3 horizontal bars */}
                    <rect x={x - 14} y={y - 14} width="28" height="5" rx="1.5" fill="#3b82f6" />
                    <rect x={x - 14} y={y - 6} width="28" height="5" rx="1.5" fill="#3b82f6" />
                    <rect x={x - 14} y={y + 2} width="28" height="5" rx="1.5" fill="#3b82f6" />
                    
                    {/* Host Name - Theme-aware text */}
                    <text x={x} y={y + 20} textAnchor="middle" fill={textPrimaryColor} fontSize="12" fontWeight="700">
                      {host.name}
                    </text>
                    {/* IP Address - Theme-aware text */}
                    <text x={x} y={y + 34} textAnchor="middle" fill={textSecondaryColor} fontSize="10" fontWeight="500">
                      {host.ip}
                    </text>
                  </g>
                )
              })
            })}
          </svg>
        </div>

        {/* Legend */}
        <div className="mt-6 flex flex-wrap items-center justify-center gap-6 rounded-lg border border-border bg-card p-4 shadow-sm">
          <div className="flex items-center gap-2">
            <div className="h-4 w-4 rounded border-2 border-[#ea580c] bg-[#ea580c]/10" />
            <span className="text-sm font-medium text-muted-foreground">Spine Switch</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-4 w-4 rounded border-2 border-[#14b8a6] bg-[#14b8a6]/10" />
            <span className="text-sm font-medium text-muted-foreground">Leaf Switch</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-4 w-4 rounded border-2 border-[#3b82f6] bg-[#3b82f6]/10" />
            <span className="text-sm font-medium text-muted-foreground">Host/Server</span>
          </div>
        </div>

        {/* Topology Info */}
        {topology && (
          <div className="mt-4 text-center text-xs text-muted-foreground">
            Last updated: {new Date(topology.timestamp).toLocaleTimeString()}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
