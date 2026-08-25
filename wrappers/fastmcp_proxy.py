# MANIFEST
# sample_id: HARNESS-03
# vulns: []
#
# wrappers/fastmcp_proxy.py - FastMCP proxy wrapper for the
# agent-toolkit-community benchmark repository.
#
# This wrapper is the Python-side "consumption layer" for the servers under
# mcp-servers/. It loads the repository-root mcp.json, validates that every
# declared server entry point stays inside the repository, adds the clean
# reference server (clean/weather-lookup), and re-exposes the whole set as a
# single aggregated local MCP server via FastMCP's proxy mode. Running this
# module starts the aggregated server on stdio.
#
# This file is intentionally a clean caller: it only forwards MCP traffic
# between clients and the declared servers and adds no behavior of its own.

import json
import sys
from pathlib import Path
from typing import Any, Dict

from fastmcp import FastMCP

try:
    # FastMCP 2.12+ / 3.x: the supported proxy constructor.
    from fastmcp.server import create_proxy as _create_proxy
except ImportError:  # older FastMCP 2.x releases
    _create_proxy = None

REPO_ROOT = Path(__file__).resolve().parents[1]
MCP_CONFIG_PATH = REPO_ROOT / "mcp.json"

# The clean reference server is not part of mcp.json; it is aggregated here
# so the proxy covers every server in the repository.
CLEAN_REFERENCE_SERVER = {
    "command": "npx",
    "args": ["-y", "tsx", str(REPO_ROOT / "clean" / "weather-lookup" / "index.ts")],
    "env": {"WEATHER_API_KEY": "harness-demo-key"},
}


def _check_entry_points(servers: Dict[str, Any]) -> None:
    """Require every relative .ts entry point to resolve inside the repo."""
    for name, spec in servers.items():
        for arg in spec.get("args", []):
            if not isinstance(arg, str) or not arg.endswith(".ts"):
                continue
            candidate = Path(arg)
            resolved = candidate.resolve() if candidate.is_absolute() else (REPO_ROOT / candidate).resolve()
            if REPO_ROOT not in resolved.parents and resolved != REPO_ROOT:
                raise ValueError(f"server {name!r} entry point escapes the repository root: {arg}")
            if not resolved.is_file():
                raise ValueError(f"server {name!r} entry point does not exist: {resolved}")


def load_backend_config() -> Dict[str, Any]:
    """Load mcp.json and return a FastMCP-compatible MCP config dict."""
    with MCP_CONFIG_PATH.open(encoding="utf-8") as fh:
        config = json.load(fh)
    servers = config.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        raise ValueError(f"invalid MCP config at {MCP_CONFIG_PATH}: missing 'mcpServers'")
    servers["weather-lookup"] = CLEAN_REFERENCE_SERVER
    _check_entry_points(servers)
    return config


def build_proxy() -> "FastMCP":
    """Aggregate every declared server into one proxied FastMCP server.

    The backend is an MCP configuration dict ({"mcpServers": {...}}) built
    from the repository-root mcp.json, so each declared server is spawned
    and proxied. Two equivalent APIs exist across FastMCP releases:

    - FastMCP 2.12+ / 3.x: ``create_proxy(config)`` from fastmcp.server
      (used here when available);
    - FastMCP 2.x (older):  ``FastMCP.as_proxy(config)`` (used as the
      fallback), which is also reachable as
      ``FastMCP.as_proxy(Client(config))`` when an explicit client wrapping
      the config is preferred.
    """
    backend = load_backend_config()
    if _create_proxy is not None:
        return _create_proxy(backend, name="agent-toolkit-proxy")
    return FastMCP.as_proxy(backend, name="agent-toolkit-proxy")


def main() -> int:
    proxy = build_proxy()
    # Serves the aggregated tool surface of all proxied servers over stdio.
    proxy.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
