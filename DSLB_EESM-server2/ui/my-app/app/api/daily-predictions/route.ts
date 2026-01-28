import { NextResponse } from "next/server";
import * as fs from "fs";
import * as path from "path";

export async function GET() {
  try {
    // Path to the daily predictions JSON file
    const dailyPredictionsPath = path.join(
      process.env.PROJECT_ROOT || "/home/huazheng/DSLB_EESM",
      "web_traffic_time_series_forecasting",
      "daily_predictions.json"
    );

    console.log(`[v0] Reading daily predictions from: ${dailyPredictionsPath}`);

    // Check if file exists
    if (!fs.existsSync(dailyPredictionsPath)) {
      console.log("[v0] Daily predictions file not found, returning empty data");
      return NextResponse.json({
        date: new Date().toISOString().split("T")[0],
        entries: [],
      });
    }

    // Read and parse the JSON file
    const fileContent = fs.readFileSync(dailyPredictionsPath, "utf-8");
    const data = JSON.parse(fileContent);

    console.log(`[v0] Daily predictions loaded successfully: ${data.entries?.length || 0} entries`);

    return NextResponse.json(data);
  } catch (error) {
    console.error("[v0] Error reading daily predictions:", error);
    return NextResponse.json(
      { 
        error: "Failed to read daily predictions",
        date: new Date().toISOString().split("T")[0],
        entries: []
      },
      { status: 500 }
    );
  }
}
