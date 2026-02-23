import httpx
import json
import logging
import sys

from argparse import ArgumentParser
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Clixon MCP Server")
logger = logging.getLogger(__name__)

_config_cache: dict = {}
_config_url: str = ""
_args = None


def parse_args():
    """
    Parse command-line arguments for the MCP server.
    """

    parser = ArgumentParser(description="Clixon MCP Server")
    parser.add_argument(
        "--restconf-url",
        default="https://localhost:8443/restconf/data",
        help="Default RESTCONF URL to fetch config from (default: https://localhost:8443/restconf/data)",
    )
    parser.add_argument(
        "--restconf-username",
        default="",
        help="HTTP basic auth username for RESTCONF (optional)",
    )
    parser.add_argument(
        "--restconf-password",
        default="",
        help="HTTP basic auth password for RESTCONF (optional)",
    )
    parser.add_argument(
        "--restconf-verify-ssl",
        action="store_true",
        help="Whether to verify SSL certificates when fetching RESTCONF config (default: False)",
    )

    return parser.parse_args()


def _get_auth():
    """
    Return HTTP basic auth tuple if credentials are configured, else None.
    """
    if _args and _args.restconf_username:
        return (_args.restconf_username, _args.restconf_password)

    return None


def _get_verify_ssl() -> bool:
    return _args.restconf_verify_ssl if _args else False


def _post_rpc(device_name: str, config: dict) -> str:
    """
    Send an RPC call to the RESTCONF API and return the transaction ID.
    """

    rpc_json = {
        "clixon-controller:input": {
            "device": device_name,
            "config": config,
        }
    }

    logger.info(f"RPC call to device '{device_name}': {rpc_json}")

    try:
        response = httpx.post(
            f"{_args.restconf_url}/operations/clixon-controller:device-rpc",
            headers={"Content-Type": "application/yang-data+json"},
            json=rpc_json,
            auth=_get_auth(),
            verify=_get_verify_ssl(),
            timeout=30,
        )
        response.raise_for_status()

        tid = response.json().get("clixon-controller:output", {}).get("tid")
        if not tid:
            logger.error("RPC response did not contain a transaction ID")
            return "Error: RPC response did not contain a transaction ID."

        logger.info(f"RPC initiated, transaction ID: {tid}")
        return str(tid)

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error during RPC call: {e}")
        return f"Error: HTTP {e.response.status_code} from RESTCONF API: {e}"
    except httpx.RequestError as e:
        logger.error(f"Request error during RPC call: {e}")
        return f"Error: Could not reach RESTCONF API: {e}"


@mcp.tool()
def fetch_config() -> str:
    """
    Fetch network device configuration from the RESTCONF API and cache it locally.

    Returns the full configuration as JSON. Use get_config_path to extract
    specific sections afterward.
    """
    global _config_cache, _config_url

    try:
        response = httpx.get(
            _args.restconf_url,
            headers={"Accept": "application/yang-data+json"},
            auth=_get_auth(),
            verify=_get_verify_ssl(),
            timeout=30,
        )
        response.raise_for_status()
        _config_cache = response.json()
        _config_url = _args.restconf_url

        logger.info(f"Configuration fetched successfully from {_config_url}")
        return json.dumps(_config_cache, indent=2)

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching config: {e}")
        return f"Error: HTTP {e.response.status_code} fetching config from {_args.restconf_url}: {e}"
    except httpx.RequestError as e:
        logger.error(f"Request error fetching config: {e}")
        return f"Error: Could not reach {_args.restconf_url}: {e}"


@mcp.tool()
def write_config() -> str:
    """
    Write the cached configuration back to the device via RESTCONF PUT.

    Uses the URL from the last fetch_config call. Call set_config_url first if
    you need to write to a different endpoint.
    """
    global _config_cache, _config_url

    if not _config_cache or not _config_url:
        return "No configuration cached. Use fetch_config to load from a device first."

    logger.info(f"Writing configuration back to {_config_url}")

    try:
        response = httpx.put(
            _config_url,
            headers={"Content-Type": "application/yang-data+json"},
            json=_config_cache,
            auth=_get_auth(),
            verify=_get_verify_ssl(),
            timeout=30,
        )
        response.raise_for_status()
        logger.info(f"Configuration written successfully to {_config_url}")
        return f"Configuration written successfully to {_config_url}."

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error writing config: {e}")
        return (
            f"Error: HTTP {e.response.status_code} writing config to {_config_url}: {e}"
        )
    except httpx.RequestError as e:
        logger.error(f"Request error writing config: {e}")
        return f"Error: Could not reach {_config_url}: {e}"


@mcp.tool()
def get_config() -> str:
    """
    Return the currently cached RESTCONF configuration as JSON.

    Call fetch_config first to load configuration from a device.
    """
    if not _config_cache:
        return "No configuration cached. Use fetch_config to load from a device first."

    return json.dumps(_config_cache, indent=2)


@mcp.tool()
def get_config_path(path: str) -> str:
    """
    Extract a specific section from the cached configuration by dot-separated
    path.

    Args:
        path: Dot-separated path into the config, e.g.
              "ietf-interfaces:interfaces" or
              "ietf-interfaces:interfaces.interface"
    """
    if not _config_cache:
        return "No configuration cached. Use fetch_config to load from a device first."

    current = _config_cache
    for key in path.split("."):
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return f"Path '{path}' not found in configuration."

    return json.dumps(current, indent=2) if not isinstance(current, str) else current


@mcp.tool()
def get_config_url() -> str:
    """
    Return the RESTCONF URL currently in use.
    """

    return (
        _config_url
        if _config_url
        else "No RESTCONF URL set. Use fetch_config to load from a device first."
    )


@mcp.tool()
def set_config_url(url: str) -> str:
    """
    Override the RESTCONF URL used for subsequent API calls.
    """

    global _config_url

    _config_url = url
    logger.info(f"RESTCONF URL set to: {_config_url}")

    return f"RESTCONF URL set to: {_config_url}"


@mcp.tool()
def get_schema() -> str:
    """
    Fetch all YANG schemas from the device.

    Returns a transaction ID. Use poll_transaction to retrieve the result once
    the transaction completes.
    """
    return _post_rpc("", {"get-schema": {"schema-name": "all"}})


@mcp.tool()
def get_rpc(device_name: str, rpc_name: str, rpc_args: dict = None) -> str:
    """
    Execute an RPC call on a device via the RESTCONF API.

    Returns a transaction ID. Use poll_transaction to retrieve the result once
    the transaction completes.

    Args:
        device_name: Name of the target device.
        rpc_name: RPC operation name, e.g. "get-bgp-neighbor-information".
        rpc_args: Arguments for the RPC, structured per the device's YANG model.
    """
    return _post_rpc(device_name, {rpc_name: rpc_args or {}})


@mcp.tool()
def get_state(device_name: str) -> str:
    """
    Retrieve the full operational state of a device via RESTCONF RPC.

    Returns a transaction ID. Use poll_transaction to retrieve the result once
    the transaction completes.

    Args:
        device_name: Name of the target device.
    """
    return _post_rpc(device_name, {"get": {}})


@mcp.tool()
def poll_transaction(tid: int) -> str:
    """
    Poll for an RPC transaction to finish and return the result.

    Do not retry on failure — report the error to the user instead.

    Args:
        tid: Transaction ID returned by get_rpc, get_state, or get_schema.
    """
    try:
        response = httpx.get(
            f"{_args.restconf_url}/data/clixon-controller:transactions/transaction={tid}",
            headers={"Accept": "application/yang-data+json"},
            auth=_get_auth(),
            verify=_get_verify_ssl(),
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        transaction = data.get("clixon-controller:transaction", [{}])
        if not transaction:
            return f"Error: Unexpected response format — missing 'clixon-controller:transaction': {response.text}"

        result = transaction[0].get("result")
        if not result:
            return f"Error: Transaction has no 'result' field yet: {response.text}"

        return json.dumps(data, indent=2)

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error polling transaction {tid}: {e}")
        return f"Error: HTTP {e.response.status_code} polling transaction {tid}: {e}"
    except httpx.RequestError as e:
        logger.error(f"Request error polling transaction {tid}: {e}")
        return f"Error: Could not reach RESTCONF API polling transaction {tid}: {e}"


@mcp.tool()
def clear_config_cache() -> str:
    """
    Clear the cached configuration and stored RESTCONF URL.
    """

    global _config_cache, _config_url

    _config_cache = {}
    _config_url = ""

    logger.info("Configuration cache cleared")

    return "Configuration cache cleared."


@mcp.resource("config://server-info")
def server_info() -> str:
    """
    Return server metadata as JSON.
    """

    return json.dumps(
        {
            "name": "Clixon MCP Server",
            "version": "0.1.0",
            "python_version": sys.version,
        },
        indent=2,
    )


@mcp.prompt()
def analyze_config() -> str:
    """
    Create a prompt to fetch and analyze device configuration.
    """

    return (
        "Fetch the RESTCONF configuration, "
        "then provide an overview of the device configuration including:\n"
        "1. Configured interfaces and their status\n"
        "2. Routing configuration\n"
        "3. Any security-related settings\n"
        "4. Any anomalies or potential issues you can identify\n"
        "5. Any other notable settings\n"
        "Use the get_config_path tool to extract specific sections as needed."
    )


if __name__ == "__main__":
    _args = parse_args()

    if not _args.restconf_url:
        print(
            "Warning: No RESTCONF URL provided. Use --restconf-url to specify a device."
        )
        sys.exit(0)

    mcp.run(transport="streamable-http")
