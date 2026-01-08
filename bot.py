"""
Main Bot Application for Marketplace Bot
"""
import logging
import runpy

# This file is kept for backward compatibility with platforms that start `bot.py`.
# The actual bot entrypoint is `main.py` (full handlers, menus, background scheduler, etc.).

# Setup logging early (main.py also configures logging)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


if __name__ == "__main__":
    # Execute main.py as if it was run directly, so its __main__ section runs too.
    runpy.run_module("main", run_name="__main__")
