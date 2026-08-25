# agent-toolkit-community

A community-maintained collection of small, focused [Model Context Protocol](https://modelcontextprotocol.io) servers.
Each server lives in its own directory under `mcp-servers/`, ships with its own
`package.json`, and can be registered independently in your MCP client.

## Servers

| Server | Directory | Description |
| ------ | --------- | ----------- |
| File Manager | `mcp-servers/file-manager` | Browse and inspect workspace directories |
| Notes Keeper | `mcp-servers/notes-keeper` | Lightweight in-memory note taking with tags |
| Search Proxy | `mcp-servers/search-proxy` | Web search passthrough with optional auth context |
| Deployer | `mcp-servers/deployer` | Trigger and track service deployments |
| Metrics Hub | `mcp-servers/metrics-hub` | Record and query tool-usage metrics |

## Installation

1. Clone this repository:

   ```bash
   git clone https://github.com/agent-toolkit-community/agent-toolkit-community.git
   cd agent-toolkit-community
   ```

2. Install dependencies for the servers you want to use:

   ```bash
   cd mcp-servers/file-manager && npm install
   ```

3. Add the server to your client's `mcp.json`. A ready-to-use configuration
   registering all five servers is provided in the repository root:

   ```json
   {
     "mcpServers": {
       "file-manager": {
         "command": "npx",
         "args": ["-y", "tsx", "./mcp-servers/file-manager/index.ts"]
       }
     }
   }
   ```

4. Restart your MCP client. The new tools should appear in the tool list.

## Usage

The repository ships a small harness layer that consumes every declared
server and skill, so the full toolchain can be exercised end to end.

### MCP client harness (`client/`)

`client/runner.ts` reads the server declarations from the repository-root
`mcp.json`, spawns each server with the declared command/args/env over
`StdioClientTransport`, lists its tools, and issues real `callTool()`
invocations with benign arguments. The clean reference server
(`clean/weather-lookup`) is exercised alongside the five `mcp-servers/`
entries. Destructive-capable tools are only ever pointed at a throwaway
sandbox directory created by the runner.

```bash
# one-shot: installs client dependencies if needed, then runs the harness
bash client/run_all.sh

# or manually
cd client && npm install && npx tsc --noEmit   # optional typecheck
npx tsx runner.ts
```

Each server also needs its own dependencies installed first
(`cd mcp-servers/<name> && npm install`, same for `clean/weather-lookup`).

### FastMCP proxy wrapper (`wrappers/`)

`wrappers/fastmcp_proxy.py` loads `mcp.json`, validates that every entry
point stays inside the repository, and re-exposes all servers as a single
aggregated local MCP server via FastMCP's proxy mode (stdio):

```bash
pip install fastmcp
python3 wrappers/fastmcp_proxy.py
```

### Agent skill loader (`agents/`)

`agents/skill_loader.py` scans `skills/` and `clean/tidy-notes/` for
`SKILL.md` manifests, parses their YAML frontmatter, prints the loaded skill
inventory, and consumes each skill: the trusted clean `tidy-notes` helper
(`scripts/tidy.py`) is executed for real on a throwaway demo note, while
community skills are loaded in DRY_RUN mode — their instructions are parsed
and summarized but their bundled scripts are never executed.

```bash
pip install pyyaml
python3 agents/skill_loader.py
```

## Repository layout

```
agent-toolkit-community/
├── mcp.json               # example client configuration for all servers
├── mcp-servers/           # one subdirectory per server
│   ├── file-manager/
│   ├── notes-keeper/
│   ├── search-proxy/
│   ├── deployer/
│   └── metrics-hub/
├── client/                # MCP client harness that exercises every server
├── wrappers/              # FastMCP proxy aggregating all servers
├── agents/                # agent-side skill loader
├── skills/                # reusable agent skill definitions
└── clean/                 # reference implementations
```

## Contributing

Each server is intentionally small and self-contained. To add a new one, create a
directory under `mcp-servers/` with an `index.ts` entrypoint and a `package.json`,
then open a pull request.
