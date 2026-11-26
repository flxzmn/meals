import sys

from config.settings import settings
from db.db import init_db
from mcp_tools.server import mcp

import mcp_tools.data_tools  # noqa: F401
import mcp_tools.instruction_tools  # noqa: F401
import mcp_tools.match_tools  # noqa: F401
import mcp_tools.nutrition_tools  # noqa: F401
import mcp_tools.recipe_tools  # noqa: F401
import mcp_tools.serving_tools  # noqa: F401
import mcp_tools.substitution_learning_tools  # noqa: F401
import mcp_tools.substitution_tools  # noqa: F401
import mcp_tools.variant_tools  # noqa: F401


def main():
    init_db()
    if settings.meal_transport == "http":
        allowed_hosts = [host.strip() for host in settings.meal_allowed_hosts.split(",") if host.strip()]
        print(f"HTTP on http://{settings.meal_http_host}:{settings.meal_http_port}{settings.meal_http_path}", file=sys.stderr)
        mcp.run(
            transport="http", host=settings.meal_http_host, port=settings.meal_http_port,
            path=settings.meal_http_path, show_banner=False,
            # Only localhost and the tunnel's host names: a web page cannot reach the port by DNS rebinding.
            host_origin_protection=True, allowed_hosts=allowed_hosts,
        )
    else:
        mcp.run()


if __name__ == "__main__":
    main()
