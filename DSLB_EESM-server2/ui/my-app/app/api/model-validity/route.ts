import { NextResponse } from "next/server"
import fs from "fs"

export async function GET() {
  try {
    const filePath = "/home/huazheng/DSLB_EESM/web_traffic_time_series_forecasting/model_validity.json"

    console.log("[v0] Reading model validity from:", filePath)

    if (!fs.existsSync(filePath)) {
      console.error("[v0] Model validity file not found:", filePath)
      return NextResponse.json({ error: "Model validity file not found" }, { status: 404 })
    }

    const fileContent = fs.readFileSync(filePath, "utf-8")
    const data = JSON.parse(fileContent)

    console.log("[v0] Model validity data loaded successfully:", data)

    return NextResponse.json(data)
  } catch (error) {
    console.error("[v0] Error reading model validity file:", error)
    return NextResponse.json({ error: "Failed to read model validity data" }, { status: 500 })
  }
}