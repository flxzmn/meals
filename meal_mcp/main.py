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
    mcp.run()


if __name__ == "__main__":
    main()
