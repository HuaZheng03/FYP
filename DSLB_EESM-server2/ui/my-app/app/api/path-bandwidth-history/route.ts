import { NextResponse } from "next/server"
import fs from "fs"
import path from "path"

// Path to the history JSON file
const HISTORY_FILE_PATH = "/home/huazheng/DSLB_EESM/predict_network_link_bandwidth_usage/path_bandwidth_history.json"

// Also check the current predictions from onos_path_selection.json
const ONOS_PATH_SELECTION_FILE = "/home/huazheng/DSLB_EESM/dynamic_load_balancing/onos_path_selection.json"

interface PathBandwidthEntry {
  timestamp: string
  time: string  // HH:MM format for display
  paths: {
    [pathName: string]: {
      predicted_mb: number
      actual_mb: number | null
    }
  }
}

interface NextPredictions {
  timestamp: string
  time: string
  iteration: number
  mode: string
  paths: {
    [pathName: string]: {
      predicted_mb: number
      actual_mb: null  // Always null for next predictions
    }
  }
}

interface PathBandwidthHistory {
  last_updated: string | null
  iteration?: number
  using_predictions?: boolean
  history_window_minutes: number
  max_entries: number
  paths: string[]
  next_predictions?: NextPredictions | null
  history: PathBandwidthEntry[]
}

interface PathSelectionData {
  metadata: {
    timestamp_utc8: string
    iteration: number
    using_predictions: boolean
  }
  path_selection_weights: {
    [routeKey: string]: {
      path_details: {
        [pathKey: string]: {
          via_spine: string
          selection_ratio: number
          bandwidth_cost: {
            bytes: number
            megabytes: number
            source: string
          }
        }
      }
    }
  }
}

export async function GET() {
  try {
    let historyData: PathBandwidthHistory | null = null
    let currentPredictions: PathSelectionData | null = null

    // Try to read history file
    if (fs.existsSync(HISTORY_FILE_PATH)) {
      try {
        const historyContent = fs.readFileSync(HISTORY_FILE_PATH, "utf-8")
        historyData = JSON.parse(historyContent)
      } catch (e) {
        console.error("[PathBandwidthHistory] Error reading history file:", e)
      }
    }

    // Try to read current predictions from onos_path_selection.json
    if (fs.existsSync(ONOS_PATH_SELECTION_FILE)) {
      try {
        const predContent = fs.readFileSync(ONOS_PATH_SELECTION_FILE, "utf-8")
        currentPredictions = JSON.parse(predContent)
      } catch (e) {
        console.error("[PathBandwidthHistory] Error reading predictions file:", e)
      }
    }

    // Build current state - prefer history file (has actual values) over onos_path_selection
    const currentState: { [pathName: string]: { predicted_mb: number; actual_mb: number | null; source?: string } } = {}
    
    // First, get values from history file (this has both predicted and actual)
    if (historyData?.history && historyData.history.length > 0) {
      const lastEntry = historyData.history[historyData.history.length - 1]
      for (const [pathName, pathData] of Object.entries(lastEntry.paths)) {
        currentState[pathName] = {
          predicted_mb: pathData.predicted_mb,
          actual_mb: pathData.actual_mb,
          source: (pathData as any).source || "unknown"
        }
      }
    }
    
    // If history is empty, fall back to onos_path_selection.json (but won't have actuals in prediction mode)
    if (Object.keys(currentState).length === 0 && currentPredictions?.path_selection_weights) {
      for (const [routeKey, routeData] of Object.entries(currentPredictions.path_selection_weights)) {
        // Parse route key like "leaf1->leaf6"
        const [src, dst] = routeKey.split("->")
        
        for (const [pathKey, pathData] of Object.entries(routeData.path_details)) {
          const spine = pathData.via_spine
          
          // Create path name in canonical format (smaller leaf first)
          let pathName: string
          if (src < dst) {
            pathName = `${src}-${spine}-${dst}`
          } else {
            pathName = `${dst}-${spine}-${src}`
          }
          
          // Only add if not already present (avoid duplicates from bidirectional routes)
          if (!currentState[pathName]) {
            currentState[pathName] = {
              predicted_mb: pathData.bandwidth_cost.megabytes,
              actual_mb: pathData.bandwidth_cost.source === "realtime" 
                ? pathData.bandwidth_cost.megabytes 
                : null,  // We don't have actual in prediction mode from this file
              source: pathData.bandwidth_cost.source
            }
          }
        }
      }
    }

    // Format response
    const response = {
      last_updated: currentPredictions?.metadata?.timestamp_utc8 || historyData?.last_updated || null,
      iteration: currentPredictions?.metadata?.iteration || historyData?.iteration || null,
      using_predictions: currentPredictions?.metadata?.using_predictions || historyData?.using_predictions || false,
      history_window_minutes: historyData?.history_window_minutes || 15,
      paths: historyData?.paths || [
        "leaf1-spine1-leaf2",
        "leaf1-spine2-leaf2",
        "leaf1-spine1-leaf3",
        "leaf1-spine2-leaf3",
        "leaf1-spine1-leaf6",
        "leaf1-spine2-leaf6",
        "leaf2-spine1-leaf3",
        "leaf2-spine2-leaf3",
        "leaf2-spine1-leaf6",
        "leaf2-spine2-leaf6",
        "leaf3-spine1-leaf6",
        "leaf3-spine2-leaf6"
      ],
      current_state: currentState,
      next_predictions: historyData?.next_predictions || null,
      history: historyData?.history || []
    }

    return NextResponse.json(response)
  } catch (error) {
    console.error("[PathBandwidthHistory] Error:", error)
    return NextResponse.json(
      { error: "Failed to read path bandwidth history", details: String(error) },
      { status: 500 }
    )
  }
}
