"""Command line interface entrypoint for running the MCP server over STDIO.

Usage:
    python -m app.mcp.cli
"""

import asyncio
import logging
import sys

from app.mcp.server import mcp_server

# Suppress standard logging to stdout/stderr in STDIO mode so it does not corrupt JSON-RPC stream
logging.basicConfig(level=logging.ERROR, stream=sys.stderr)


def main() -> None:
    """Runs the MCP server over standard input/output."""
    try:
        asyncio.run(mcp_server.run_stdio_async())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)


if __name__ == "__main__":
    main()
