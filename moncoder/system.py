import os
import platform
from datetime import date
from functools import lru_cache
from pathlib import Path
from moncoder.config import Path as ConfigPath  # Import Path from config


@lru_cache
def system_prompt() -> str:
    current_dir = Path(__file__).resolve().parent
    with open(current_dir / "assets/system_prompt.txt", "r") as f:
        prompt = f.read().strip()
    return prompt + environment() + custom()


def check_git() -> bool:
    """Check if there's a .git directory in the current project."""
    return os.path.exists(os.path.join(ConfigPath.project, ".git"))


def environment() -> str:
    env_info = [
        "Here is some useful information about the environment you are running in:",
        "<env>",
        f"  Working directory: {ConfigPath.project}",
        f"  Is directory a git repo: {'yes' if check_git() else 'no'}",
        f"  Platform: {platform.system()}",
        f"  Today's date: {date.today().strftime('%a %b %d %Y')}",
        "</env>\n",
    ]
    return "\n".join(env_info)


def custom() -> str:
    rules = []

    rule_filenames = ["AGENTS.md", "CLAUDE.md"]

    for location in [ConfigPath.project, ConfigPath.config]:
        for rule_filename in rule_filenames:
            if (location / rule_filename).is_file():
                with open(location / rule_filename, "r") as f:
                    rules.append(f.read().strip())
    return "\n".join(rules)
