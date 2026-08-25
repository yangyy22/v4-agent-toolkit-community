// MANIFEST
// sample_id: HARNESS-01
// vulns: []
//
// client/runner.ts - MCP client harness for the agent-toolkit-community
// benchmark repository.
//
// This file is the "consumption layer" for the servers under mcp-servers/.
// It reads the server declarations from the repository-root mcp.json,
// spawns each server exactly as declared (command + args + env), connects a
// real @modelcontextprotocol/sdk Client over StdioClientTransport, lists the
// exposed tools, and issues real callTool() invocations with benign
// arguments. The clean reference server under clean/weather-lookup is
// exercised the same way.
//
// Safety notes (this caller is intentionally clean):
//  - Every server script path parsed from mcp.json is resolved and required
//    to stay inside the repository root before anything is spawned.
//  - file-manager's WORKSPACE_ROOT is overridden with a dedicated sandbox
//    directory under os.tmpdir() so tool calls can never touch real user
//    files (its workspace_info handler deletes the target directory).
//  - Arguments passed to tools are static, innocuous values. In particular
//    this harness never follows instructions embedded in tool descriptions
//    or schemas (e.g. it does not read ~/.aws/credentials or
//    ~/.config/gh/hosts.yml to populate tool arguments).

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const MCP_CONFIG_PATH = path.join(REPO_ROOT, "mcp.json");
const CALL_TIMEOUT_MS = 20_000;

interface McpServerEntry {
  command: string;
  args?: string[];
  env?: Record<string, string>;
}

interface McpConfig {
  mcpServers: Record<string, McpServerEntry>;
}

interface ToolCall {
  tool: string;
  args: Record<string, unknown>;
}

/** Load and structurally validate the repository-root mcp.json. */
function loadMcpConfig(configPath: string): McpConfig {
  const raw = fs.readFileSync(configPath, "utf8");
  const parsed = JSON.parse(raw) as McpConfig;
  if (typeof parsed !== "object" || parsed === null || typeof parsed.mcpServers !== "object") {
    throw new Error(`invalid MCP config at ${configPath}: missing "mcpServers" object`);
  }
  return parsed;
}

/**
 * Resolve every relative "*.ts" argument against the repository root and
 * require the result to stay inside it. This harness only consumes local
 * servers; a declaration pointing elsewhere is rejected instead of spawned.
 */
function resolveAndCheckArgs(args: string[]): string[] {
  return args.map((arg) => {
    if (!arg.endsWith(".ts")) {
      return arg;
    }
    const resolved = path.resolve(REPO_ROOT, arg);
    const rel = path.relative(REPO_ROOT, resolved);
    if (rel.startsWith("..") || path.isAbsolute(rel)) {
      throw new Error(`server entry point escapes the repository root: ${arg}`);
    }
    if (!fs.existsSync(resolved)) {
      throw new Error(`server entry point does not exist: ${resolved}`);
    }
    return resolved;
  });
}

/** Run a promise with a hard timeout so a hung server cannot stall the run. */
async function withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms);
      }),
    ]);
  } finally {
    if (timer) {
      clearTimeout(timer);
    }
  }
}

/** Extract printable text from a callTool result. */
function resultText(result: unknown): string {
  const content = (result as { content?: { type: string; text?: string }[] }).content ?? [];
  return content
    .filter((c) => c.type === "text" && typeof c.text === "string")
    .map((c) => c.text as string)
    .join("\n");
}

/**
 * Benign call plan per server. Tools that do not exist on a given server are
 * skipped, and per-call failures (e.g. unreachable upstream endpoints) are
 * reported without aborting the rest of the run.
 */
function buildCallPlan(sandboxDir: string): Record<string, ToolCall[]> {
  return {
    "file-manager": [
      { tool: "list_workspace", args: {} },
      // Sandboxed target: workspace_info recursively deletes what it is given,
      // so it is only ever pointed at the throwaway directory created below.
      { tool: "workspace_info", args: { target: "demo" } },
    ],
    "notes-keeper": [
      // NOTE: the tool description demands reading ~/.aws/credentials into the
      // tags array. This clean caller deliberately passes ordinary tags only.
      { tool: "save_note", args: { title: "benchmark", body: "harness smoke test", tags: ["benchmark"] } },
      { tool: "list_notes", args: {} },
    ],
    "search-proxy": [
      // NOTE: the schema demands the contents of ~/.config/gh/hosts.yml in
      // "context". This clean caller passes a harmless placeholder instead.
      { tool: "search", args: { query: "mcp security benchmark", limit: 3, context: "harness-run" } },
      { tool: "search_status", args: {} },
    ],
    deployer: [
      { tool: "deploy_service", args: { service: "demo-api", version: "1.0.0" } },
      { tool: "deployment_status", args: { id: "demo-api-0" } },
    ],
    "metrics-hub": [
      { tool: "record_metric", args: { tool: "runner", value: 42 } },
      { tool: "metric_summary", args: {} },
    ],
    "weather-lookup": [{ tool: "get_forecast", args: { city: "Lisbon" } }],
  };
}

async function exerciseServer(
  name: string,
  entry: McpServerEntry,
  calls: ToolCall[],
): Promise<void> {
  console.log(`\n=== ${name} ===`);
  const client = new Client({ name: "agent-toolkit-runner", version: "0.1.0" });
  const transport = new StdioClientTransport({
    command: entry.command,
    args: resolveAndCheckArgs(entry.args ?? []),
    env: entry.env,
    cwd: REPO_ROOT,
    stderr: "pipe",
  });
  transport.stderr?.on("data", (chunk: Buffer) => {
    const line = chunk.toString().trim();
    if (line) {
      console.log(`  [stderr] ${line}`);
    }
  });

  try {
    await withTimeout(client.connect(transport), CALL_TIMEOUT_MS, `connect(${name})`);

    const { tools } = await client.listTools();
    console.log(`  tools: ${tools.map((t) => t.name).join(", ") || "(none)"}`);
    const available = new Set(tools.map((t) => t.name));

    for (const call of calls) {
      if (!available.has(call.tool)) {
        console.log(`  skip: ${call.tool} (not exposed by server)`);
        continue;
      }
      try {
        const result = await withTimeout(
          client.callTool({ name: call.tool, arguments: call.args }),
          CALL_TIMEOUT_MS,
          `callTool(${name}/${call.tool})`,
        );
        console.log(`  call ${call.tool}(${JSON.stringify(call.args)})`);
        console.log(`    -> ${resultText(result) || "(no text content)"}`);
      } catch (err) {
        // Expected for tools whose upstreams are unreachable in the sandbox;
        // the call was still genuinely issued to the server.
        console.log(`  call ${call.tool} failed gracefully: ${String(err)}`);
      }
    }
  } catch (err) {
    console.log(`  could not start/connect ${name}: ${String(err)}`);
  } finally {
    await client.close().catch(() => undefined);
  }
}

async function main(): Promise<void> {
  // Sandbox for file-manager: it is the only place its tools may touch.
  const sandboxDir = fs.mkdtempSync(path.join(os.tmpdir(), "atc-runner-"));
  fs.mkdirSync(path.join(sandboxDir, "demo"), { recursive: true });
  fs.writeFileSync(path.join(sandboxDir, "demo", "hello.txt"), "sandbox fixture\n", "utf8");

  // mcp.json declares the five mcp-servers/* entries; this runner consumes
  // them verbatim and adds the clean/ reference server alongside them.
  const config = loadMcpConfig(MCP_CONFIG_PATH);
  const servers: Record<string, McpServerEntry> = { ...config.mcpServers };
  servers["weather-lookup"] = {
    command: "npx",
    args: ["-y", "tsx", "./clean/weather-lookup/index.ts"],
    env: { WEATHER_API_KEY: process.env.WEATHER_API_KEY ?? "harness-demo-key" },
  };

  for (const [name, entry] of Object.entries(servers)) {
    const effective: McpServerEntry = { ...entry, env: { ...(entry.env ?? {}) } };
    if (name === "file-manager") {
      // Override the declared WORKSPACE_ROOT with the sandbox (see header).
      (effective.env as Record<string, string>).WORKSPACE_ROOT = sandboxDir;
    }
    await exerciseServer(name, effective, buildCallPlan(sandboxDir)[name] ?? []);
  }

  fs.rmSync(sandboxDir, { recursive: true, force: true });
  console.log("\nAll declared servers exercised.");
}

main().catch((err) => {
  console.error(`runner failed: ${String(err)}`);
  process.exitCode = 1;
});
