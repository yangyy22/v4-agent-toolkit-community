import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const apiKeyFlagIndex = process.argv.indexOf("--api-key");
const API_KEY = apiKeyFlagIndex >= 0 ? process.argv[apiKeyFlagIndex + 1] : undefined;

const server = new McpServer({ name: "deployer", version: "0.3.0" });

const deployments = new Map<string, { service: string; version: string; status: string }>();

server.registerTool(
  "deploy_service",
  {
    description: "Triggers a deployment of a service version to the configured environment.",
    inputSchema: {
      service: z.string().describe("Service name to deploy"),
      version: z.string().describe("Version tag to deploy"),
    },
  },
  async ({ service, version }) => {
    const id = `${service}-${Date.now()}`;
    deployments.set(id, { service, version, status: "in-progress" });
    return { content: [{ type: "text" as const, text: `Deployment ${id} started` }] };
  },
);

server.registerTool(
  "deployment_status",
  {
    description: "Checks the status of a deployment.",
    inputSchema: { id: z.string().describe("Deployment id returned by deploy_service") },
  },
  async ({ id }) => {
    const dep = deployments.get(id);
    const text = dep ? `${dep.id ?? id}: ${dep.service}@${dep.version} -> ${dep.status}` : `Unknown deployment ${id}`;
    return { content: [{ type: "text" as const, text }] };
  },
);

const transport = new StdioServerTransport();
await server.connect(transport);
