import { NextResponse } from "next/server"
import fs from "fs"

export async function GET() {
  try {
    const filePath = "/home/huazheng/DSLB_EESM/forecast_cache.json"

    console.log("[v0] Reading forecast cache from:", filePath)

    // Check if file exists
    if (!fs.existsSync(filePath)) {
      console.error("[v0] Forecast cache file not found:", filePath)
      return NextResponse.json({ error: "Forecast cache file not found", path: filePath }, { status: 404 })
    }

    // Read and parse the JSON file
    const fileContent = fs.readFileSync(filePath, "utf-8")
    const forecastData = JSON.parse(fileContent)

    console.log("[v0] Forecast data loaded successfully:", forecastData)

    return NextResponse.json(forecastData)
  } catch (error) {
    console.error("[v0] Error reading forecast cache:", error)
    return NextResponse.json(
      {
        error: "Failed to read forecast cache",
        details: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 500 },
    )
  }
}