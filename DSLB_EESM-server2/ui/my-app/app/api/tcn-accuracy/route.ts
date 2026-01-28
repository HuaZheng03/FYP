import { NextResponse } from "next/server"
import fs from "fs"

export async function GET() {
  try {
    const filePath = "/home/huazheng/DSLB_EESM/predict_network_link_bandwidth_usage/tcn_model_accuracy.json"

    console.log("[v0] Reading TCN model accuracy from:", filePath)

    if (!fs.existsSync(filePath)) {
      console.error("[v0] TCN model accuracy file not found:", filePath)
      return NextResponse.json({ error: "TCN model accuracy file not found" }, { status: 404 })
    }

    const fileContent = fs.readFileSync(filePath, "utf-8")
    const data = JSON.parse(fileContent)

    console.log("[v0] TCN model accuracy data loaded successfully:", data)

    return NextResponse.json(data)
  } catch (error) {
    console.error("[v0] Error reading TCN model accuracy file:", error)
    return NextResponse.json({ error: "Failed to read TCN model accuracy data" }, { status: 500 })
  }
}
