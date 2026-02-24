# Clixon MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io/) server for fetching and querying network device configuration via RESTCONF. Connects to Clixon-based (or any RESTCONF-capable) devices and makes the configuration available to AI coding agents like OpenCode.

## Setup

```bash
uv sync
```

## Run

```bash
uv run server.py --restconf-url https://localhost:8443/restconf/
```

### CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--restconf-url` | `https://localhost:8443/restconf/` | RESTCONF URL to fetch config from |
| `--restconf-username` | _(empty)_ | HTTP basic auth username for RESTCONF (optional) |
| `--restconf-password` | _(empty)_ | HTTP basic auth password for RESTCONF (optional) |
| `--restconf-verify-ssl` | `False` | Verify SSL certificates when fetching RESTCONF config |

## Tools

| Tool | Description |
|------|-------------|
| `fetch_config` | Fetch device configuration via RESTCONF (supports basic auth and TLS) |
| `write_config` | Write cached configuration back to the device via RESTCONF |
| `get_config` | Return the currently cached configuration |
| `get_config_path` | Extract a specific section by dot-separated path (e.g. `ietf-interfaces:interfaces.interface`) |
| `get_config_url` | Return the RESTCONF URL used to fetch the configuration |
| `set_config_url` | Set the RESTCONF URL for fetching configuration |
| `clear_config_cache` | Clear the cached configuration |
| `list_tools` | List available tools |
| `help` | Return a help message describing the server and available tools |

## Resources

- `config://server-info` — Server metadata (name, version, available tools)

## Prompts

- `analyze_config` — Fetch and analyze device configuration (interfaces, routing, etc.)


## Connect to OpenCode

Add to your `opencode.json` (`~/.config/opencode.json`):

```json
{
    "$schema": "https://opencode.ai/config.json",
    "mcp": {
      "clixon": {
        "type": "remote",
        "url": "http://localhost:8000/mcp",
        "enabled": true
      }
    }
}
```

## Example Usage in OpenCode

Once connected, ask questions like:

- `Fetch the config and summarize it.`
- `What interfaces are configured?`
- `Show me the routing configuration`
- `Are there any interfaces that are down?`

The AI agent will call `fetch_config` to pull the RESTCONF data, cache it in memory, and then use `get_config` / `get_config_path` to answer follow-up questions about the device configuration.
