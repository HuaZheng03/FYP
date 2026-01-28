import { NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

// Path to the alerts JSON file
const ALERTS_FILE = path.join(process.cwd(), '..', '..', 'alerts', 'system_alerts.json')

// Helper to format relative time
function formatRelativeTime(timestamp: string): string {
  const now = new Date()
  const alertTime = new Date(timestamp)
  const diffMs = now.getTime() - alertTime.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins} min ago`
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`
  return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const limit = parseInt(searchParams.get('limit') || '50')
    const category = searchParams.get('category')
    const type = searchParams.get('type')
    const includeAcknowledged = searchParams.get('includeAcknowledged') !== 'false'

    // Check if file exists
    if (!fs.existsSync(ALERTS_FILE)) {
      return NextResponse.json({
        alerts: [],
        counts: {
          total: 0,
          critical: 0,
          warning: 0,
          success: 0,
          info: 0,
          unacknowledged: 0
        }
      })
    }

    // Read alerts file
    const fileContent = fs.readFileSync(ALERTS_FILE, 'utf-8')
    const data = JSON.parse(fileContent)
    let alerts = data.alerts || []

    // Apply filters
    if (category) {
      alerts = alerts.filter((a: any) => a.category === category)
    }
    if (type) {
      alerts = alerts.filter((a: any) => a.type === type)
    }
    if (!includeAcknowledged) {
      alerts = alerts.filter((a: any) => !a.acknowledged)
    }

    // Calculate counts before limiting
    const counts = {
      total: data.alerts?.length || 0,
      critical: (data.alerts || []).filter((a: any) => a.type === 'critical').length,
      warning: (data.alerts || []).filter((a: any) => a.type === 'warning').length,
      success: (data.alerts || []).filter((a: any) => a.type === 'success').length,
      info: (data.alerts || []).filter((a: any) => a.type === 'info').length,
      unacknowledged: (data.alerts || []).filter((a: any) => !a.acknowledged).length
    }

    // Apply limit
    alerts = alerts.slice(0, limit)

    // Add relative time to each alert
    alerts = alerts.map((alert: any) => ({
      ...alert,
      relativeTime: formatRelativeTime(alert.timestamp)
    }))

    return NextResponse.json({
      alerts,
      counts,
      lastCleanup: data.last_cleanup
    })
  } catch (error) {
    console.error('Error reading alerts:', error)
    return NextResponse.json(
      { error: 'Failed to read alerts', alerts: [], counts: {} },
      { status: 500 }
    )
  }
}

export async function DELETE(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const alertId = searchParams.get('id')
    const clearAll = searchParams.get('clearAll') === 'true'

    if (!fs.existsSync(ALERTS_FILE)) {
      return NextResponse.json({ success: false, message: 'No alerts file found' })
    }

    const fileContent = fs.readFileSync(ALERTS_FILE, 'utf-8')
    const data = JSON.parse(fileContent)

    if (clearAll) {
      const count = data.alerts?.length || 0
      data.alerts = []
      data.last_cleanup = new Date().toISOString()
      fs.writeFileSync(ALERTS_FILE, JSON.stringify(data, null, 2))
      return NextResponse.json({ success: true, message: `Cleared ${count} alerts` })
    }

    if (alertId) {
      const originalLength = data.alerts?.length || 0
      data.alerts = (data.alerts || []).filter((a: any) => a.id !== alertId)
      
      if (data.alerts.length < originalLength) {
        fs.writeFileSync(ALERTS_FILE, JSON.stringify(data, null, 2))
        return NextResponse.json({ success: true, message: 'Alert deleted' })
      }
      return NextResponse.json({ success: false, message: 'Alert not found' })
    }

    return NextResponse.json({ success: false, message: 'No alert ID or clearAll parameter provided' })
  } catch (error) {
    console.error('Error deleting alert:', error)
    return NextResponse.json(
      { success: false, error: 'Failed to delete alert' },
      { status: 500 }
    )
  }
}

export async function PATCH(request: Request) {
  try {
    const body = await request.json()
    const { alertId, acknowledged } = body

    if (!alertId) {
      return NextResponse.json({ success: false, message: 'Alert ID required' })
    }

    if (!fs.existsSync(ALERTS_FILE)) {
      return NextResponse.json({ success: false, message: 'No alerts file found' })
    }

    const fileContent = fs.readFileSync(ALERTS_FILE, 'utf-8')
    const data = JSON.parse(fileContent)

    let found = false
    data.alerts = (data.alerts || []).map((alert: any) => {
      if (alert.id === alertId) {
        found = true
        return {
          ...alert,
          acknowledged: acknowledged ?? true,
          acknowledged_at: acknowledged ? new Date().toISOString() : null
        }
      }
      return alert
    })

    if (found) {
      fs.writeFileSync(ALERTS_FILE, JSON.stringify(data, null, 2))
      return NextResponse.json({ success: true, message: 'Alert updated' })
    }

    return NextResponse.json({ success: false, message: 'Alert not found' })
  } catch (error) {
    console.error('Error updating alert:', error)
    return NextResponse.json(
      { success: false, error: 'Failed to update alert' },
      { status: 500 }
    )
  }
}
