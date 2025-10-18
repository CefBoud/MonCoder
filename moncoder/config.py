import os
import logging
from typing import Dict, Optional
import pathlib
from xdg_base_dirs import xdg_data_home, xdg_cache_home, xdg_config_home, xdg_state_home

from dotenv import load_dotenv

load_dotenv()


app = "moncoder"

llm_config: Dict[str, Optional[str]] = {
    key: value
    for key, value in {
        "model": os.environ.get("MODEL"),
        "api_base": os.environ.get("API_BASE"),
        "api_key": os.environ.get("API_KEY"),
    }.items()
    if value is not None
}


class Path:
    data = pathlib.Path(xdg_data_home()) / app
    bin = pathlib.Path(xdg_data_home()) / app / "bin"
    log = pathlib.Path(xdg_data_home()) / app / "log"
    cache = pathlib.Path(xdg_cache_home()) / app
    config = pathlib.Path(xdg_config_home()) / app
    state = pathlib.Path(xdg_state_home()) / app
    project = pathlib.Path.cwd().resolve()  # Project's current dir


# Create directories
for path in [Path.data, Path.config, Path.state, Path.log, Path.bin]:
    path.mkdir(parents=True, exist_ok=True)


def init():
    logging.basicConfig(
        filename=Path.log / "app.log",  # Log file name
        level=logging.INFO,  # Log level
        format="%(asctime)s-  %(name)s - %(levelname)s - %(message)s",  # Log format
    )

    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("markdown_it.rules_block").setLevel(logging.ERROR)