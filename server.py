import httpx
import json
import logging
import sys

from argparse import ArgumentParser
from mcp.server.fastmcp import FastMCP
from time import sleep

mcp = FastMCP("Clixon MCP Server")
logger = logging.getLogger(__name__)

_config_cache: dict = {}
_config_url: str = ""


def parse_args():
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


@mcp.tool()
def fetch_config() -> str:
    """
    Fetch network device configuration via RESTCONF.
    """

    global _config_cache, _config_url

    args = parse_args()
    headers = {"Accept": "application/yang-data+json"}

    try:
        auth = (
            (args.restconf_username, args.restconf_password)
            if args.restconf_username
            else None
        )
        response = httpx.get(
            args.restconf_url,
            headers=headers,
            auth=auth,
            verify=args.restconf_verify_ssl,
            timeout=30,
        )
        response.raise_for_status()
        _config_cache = response.json()
        _config_url = args.restconf_url

        logger.info(f"Configuration fetched successfully from {_config_url}")

        return json.dumps(_config_cache, indent=2)
    except Exception as e:
        logger.error(f"Error fetching config from {args.restconf_url}: {e}")
        return f"Error fetching config: {e}"


@mcp.tool()
def write_config():
    """
    Write network device configuration back to the device via RESTCONF.

    The RESTCONF URL from the last fetch_config call will be used. Make sure
    to set the URL with set_config_url if you want to write to a different
    device or endpoint.

    Config should be written using HTTP PUT to the same URL used to fetch,
    with the config as JSON body. This is a simple implementation and may need
    to be adjusted based on the specific RESTCONF API of the device, including
    handling of authentication, headers, and response parsing.
    """

    global _config_cache, _config_url

    if not _config_cache or not _config_url:
        return "No configuration cached. Use fetch_config to load from a device."

    logger.info(f"Attempting to write configuration back to {_config_url}")

    return _config_cache, _config_url


@mcp.tool()
def get_config() -> str:
    """
    Return the currently cached RESTCONF configuration.

    Call fetch_config first to load configuration from a device.
    """

    if not _config_cache:
        return "No configuration cached. Use fetch_config to load from a device."

    logger.info("Returning cached configuration")

    return json.dumps(_config_cache, indent=2)


@mcp.tool()
def get_config_path(path: str) -> str:
    """
    Extract a specific section from the cached configuration by dot-separated path.

    Args:
        path: Dot-separated path into the config, e.g.
              "ietf-interfaces:interfaces" or
              "ietf-interfaces:interfaces.interface"
    """

    if not _config_cache:
        return "No configuration cached. Use fetch_config to load from a device."

    current = _config_cache

    for key in path.split("."):
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return f"Path '{path}' not found in configuration."

    logger.info(f"Extracted config path '{path}' successfully")

    return json.dumps(current, indent=2) if not isinstance(current, str) else current


@mcp.tool()
def get_config_url() -> str:
    """
    Return the RESTCONF URL used to fetch the configuration.
    """

    logger.info("Returning RESTCONF URL used for fetching configuration")

    return (
        _config_url
        if _config_url
        else "No RESTCONF URL set. Use fetch_config to load from a device."
    )


@mcp.tool()
def set_config_url(url: str) -> str:
    """
    Set the RESTCONF URL to be used for fetching configuration.
    """

    global _config_url

    _config_url = url

    logger.info(f"RESTCONF URL set to: {_config_url}")

    return f"RESTCONF URL set to: {_config_url}"


@mcp.tool()
def get_schema():
    """
    Get the YANG schema from the RESTCONF API.

    After this tool is called, use poll_transaction with the returned transaction ID to
    fetch the result once the transaction is complete.

    Use the schemas to learn which RPC calls are supported by the device and
    how to structure the RPC input for get_rpc.
    """

    return get_rpc("", "get-schema", {"schema-name": "all"})


@mcp.tool()
def get_rpc(device_name: str, rpc_name: str, rpc_args: dict = None):
    """
    Run get_config as a first step.

    Get device information using an RPC call to the RESTCONF API.

    After this tool is called, use poll_transaction with the returned transaction ID to
    fetch the result once the transaction is complete.

    This function will return the tid (transaction ID) of the initiated RPC
    call, which can be used to poll for the result.

    Parameters:
    - device_name: The name of the device to run the RPC on.
    - rpc_name: The name of the RPC to run, e.g. "get-bgp-neighbor-information".
    - rpc_args: A dictionary of arguments to pass to the RPC, structured according to the device's YANG model for the RPC input.
    """

    try:
        auth = (
            (args.restconf_username, args.restconf_password)
            if args.restconf_username
            else None
        )

        rpc_json = {
                "clixon-controller:input": {
                    "device": device_name,
                    "config": {
                        rpc_name: rpc_args
                    },
                }
            }

        logger.info(device_name)
        logger.info(args.restconf_url)
        logger.info(rpc_json)

        rpc_response = httpx.post(
            f"{args.restconf_url}/operations/clixon-controller:device-rpc",
            headers={"Content-Type": "application/yang-data+json"},
            json=rpc_json,
            auth=auth,
            verify=args.restconf_verify_ssl,
            timeout=30,
        )

        rpc_response.raise_for_status()

        tid = rpc_response.json().get("clixon-controller:output", {}).get("tid")

        if not tid:
            logger.error("RPC response did not contain transaction ID")
            return "Error: RPC response did not contain transaction ID"

        logger.info(f"RPC initiated successfully, transaction ID: {tid}")

        return tid

    except Exception as e:
        logger.error(f"Error during RPC call to fetch BGP neighbor information: {e}")
        return f"Error during RPC call: {e}"


@mcp.tool()
def get_state(device_name: str):
    """
    Run get_config as a first step.

    Get device state information using an RPC call to the RESTCONF API.

    After this tool is called, use poll_transaction with the returned
    transaction ID to fetch the result once the transaction is complete.

    This function will return the tid (transaction ID) of the initiated RPC
    call, which can be used to poll for the result.
    """

    try:
        auth = (
            (args.restconf_username, args.restconf_password)
            if args.restconf_username
            else None
        )

        rpc_json = {
                "clixon-controller:input": {
                    "device": device_name,
                    "config": {
                        "get": {}
                    }
                },
            }

        logger.info(device_name)
        logger.info(args.restconf_url)
        logger.info(rpc_json)

        rpc_response = httpx.post(
            f"{args.restconf_url}/operations/clixon-controller:device-rpc",
            headers={"Content-Type": "application/yang-data+json"},
            json=rpc_json,
            auth=auth,
            verify=args.restconf_verify_ssl,
            timeout=30,
        )

        rpc_response.raise_for_status()

        tid = rpc_response.json().get("clixon-controller:output", {}).get("tid")

        if not tid:
            logger.error("RPC response did not contain transaction ID")
            return "Error: RPC response did not contain transaction ID"

        logger.info(f"RPC initiated successfully, transaction ID: {tid}")

        return tid

    except Exception as e:
        logger.error(f"Error during RPC call to fetch BGP neighbor information: {e}")
        return f"Error during RPC call: {e}"


@mcp.tool()
def poll_transaction(tid: int):
    """
    Poll for the transaction to finish and fetch the result.

    Example where 5 is the transaction ID returned from the RPC call:
        GET /restconf/data/clixon-controller:transactions/transaction=5 HTTP/1.1

    If this function fails, don't try again but let the user know that the
    transaction result couldn't be fetched. This is to avoid infinite loops in
    case of errors.
    """

    auth = (
        (args.restconf_username, args.restconf_password)
        if args.restconf_username
        else None
    )

    try:
        transaction_response = httpx.get(
            f"{args.restconf_url}/data/clixon-controller:transactions/transaction={tid}",
            headers={"Accept": "application/yang-data+json"},
            auth=auth,
            verify=args.restconf_verify_ssl,
            timeout=30,
        )

        transaction_response.raise_for_status()

        if "clixon-controller:transaction" not in transaction_response.json():
            return f"Error: Unexpected response format, missing 'clixon-controller:transaction' key: {transaction_response.text}"

        if "result" not in transaction_response.json()["clixon-controller:transaction"][0]:
            return f"Error: Unexpected response format, missing 'result' key in transaction: {transaction_response.text}"

        if "SUCCESS" in transaction_response.json()["clixon-controller:transaction"][0]["result"]:
            return json.dumps(transaction_response.json(), indent=2)

    except Exception as e:
        logger.error(f"Error polling transaction {tid}: {e}")
        return f"Error polling transaction: {e}"

    logger.info(
        f"Transaction completed successfully, fetching result for transaction ID: {tid}"
    )

    return json.dumps(transaction_response.json(), indent=2)


@mcp.tool()
def clear_config_cache() -> str:
    """
    Clear the cached configuration.
    """

    global _config_cache, _config_url

    _config_cache = {}
    _config_url = ""

    logger.info("Configuration cache cleared")

    return "Configuration cache cleared."


@mcp.tool()
def list_tools() -> str:
    """
    List available tools.
    """

    logger.info("Listing available tools")

    return json.dumps(
        {
            "fetch_config": "Fetch network device configuration via RESTCONF.",
            "write_config": "Write the cached configuration back to the device via RESTCONF.",
            "get_config": "Return the currently cached RESTCONF configuration.",
            "get_config_path": "Extract a specific section from the cached configuration by dot-separated path.",
            "get_config_url": "Return the RESTCONF URL used to fetch the configuration.",
            "set_config_url": "Set the RESTCONF URL to be used for fetching configuration.",
            "clear_config_cache": "Clear the cached configuration.",
        },
        indent=2,
    )


@mcp.tool()
def help() -> str:
    """
    Return a help message describing the server and available tools.
    """

    logger.info("Returning help message")

    return (
        "This is the Clixon MCP Server, designed to fetch and analyze network device configurations via RESTCONF.\n"
        "Available tools:\n"
        "1. fetch_config: Fetch network device configuration via RESTCONF.\n"
        "2. get_config: Return the currently cached RESTCONF configuration.\n"
        "3. get_config_path: Extract a specific section from the cached configuration by dot-separated path.\n"
        "4. get_config_url: Return the RESTCONF URL used to fetch the configuration.\n"
        "5. clear_config_cache: Clear the cached configuration.\n"
        "Use these tools to load and analyze device configurations."
    )


@mcp.resource("config://server-info")
def server_info() -> str:
    """
    Return server metadata as JSON.
    """

    logger.info("Returning server metadata")

    return json.dumps(
        {
            "name": "Clixon MCP Server",
            "version": "0.1.0",
            "python_version": f"{__import__('sys').version}",
            "tools": ["fetch_config", "get_config", "get_config_path"],
        },
        indent=2,
    )


@mcp.prompt()
def analyze_config() -> str:
    """
    Create a prompt to fetch and analyze device configuration.
    """

    logger.info("Creating prompt for configuration analysis")

    return (
        "Fetch the RESTCONF configuration', "
        "then provide an overview of the device configuration including:\n"
        "1. Configured interfaces and their status\n"
        "2. Routing configuration\n"
        "3. Any security-related settings\n"
        "4. Any anomalies or potential issues you can identify\n"
        "Use the get_config_path tool to extract specific sections of the config as needed.\n"
        "Any other notable settings"
    )


if __name__ == "__main__":
    args = parse_args()

    if not args.restconf_url:
        print(
            "Warning: No RESTCONF URL provided. Use --restconf-url to specify a device to fetch configuration from."
        )
        sys.exit(0)

    mcp.run(transport="streamable-http")
