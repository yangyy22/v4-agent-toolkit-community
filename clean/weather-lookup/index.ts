// MANIFEST
// sample_id: CLN-02
// vulns: []
// fp_traps:
//   - lines: "12-12"
//     pattern: "imports execFile from node:child_process - used with a fixed binary and constant args"
//   - lines: "21-21"
//     pattern: "API key read from process.env - standard environment-based secret handling"
//   - lines: "29-36"
//     pattern: "child_process execFile with a constant argument array - no shell, no user-controlled input"

import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const API_BASE_URL = "https://api.openweathermap.org/data/2.5";
const REQUEST_TIMEOUT_MS = 10_000;

const apiKey = process.env.WEATHER_API_KEY;
if (!apiKey) {
  console.error(
    "weather-lookup: set WEATHER_API_KEY in the server environment before starting."
  );
  process.exit(1);
}

const execFileAsync = promisify(execFile);

async function localTimestamp(): Promise<string> {
  // Fixed binary path with a constant argument array: no shell is involved
  // and nothing here is influenced by tool input.
  const { stdout } = await execFileAsync("/bin/date", ["+%Y-%m-%dT%H:%M:%S%z"], {
    timeout: 5_000,
  });
  return stdout.trim();
}

interface Forecast {
  city: string;
  description: string;
  tempCelsius: number;
  humidityPercent: number;
}

async function fetchForecast(city: string): Promise<Forecast> {
  const url = new URL(`${API_BASE_URL}/weather`);
  url.searchParams.set("q", city);
  url.searchParams.set("appid", apiKey as string);
  url.searchParams.set("units", "metric");
  const response = await fetch(url, {
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });
  if (!response.ok) {
    throw new Error(`weather API returned HTTP ${response.status}`);
  }
  const data = (await response.json()) as {
    name: string;
    weather: { description: string }[];
    main: { temp: number; humidity: number };
  };
  return {
    city: data.name,
    description: data.weather[0]?.description ?? "unknown",
    tempCelsius: data.main.temp,
    humidityPercent: data.main.humidity,
  };
}

const server = new McpServer({ name: "weather-lookup", version: "1.0.0" });

server.registerTool(
  "get_forecast",
  {
    title: "Get Forecast",
    description:
      "Fetch current weather conditions for a city from a public weather API.",
    inputSchema: {
      city: z.string().min(1).max(120).describe("City name, e.g. 'Lisbon'"),
    },
  },
  async ({ city }) => {
    const forecast = await fetchForecast(city);
    const observedAt = await localTimestamp();
    return {
      content: [
        {
          type: "text" as const,
          text: `${forecast.city}: ${forecast.description}, ${forecast.tempCelsius} C, humidity ${forecast.humidityPercent}% (observed ${observedAt})`,
        },
      ],
    };
  }
);

const transport = new StdioServerTransport();
await server.connect(transport);
