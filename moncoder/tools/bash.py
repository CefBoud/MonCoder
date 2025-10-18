import asyncio
import os
import shlex
import subprocess
from typing import Any, Dict

from moncoder.tools.tool import Tool

DESCRIPTION = """Executes a given bash command in a persistent shell session with optional timeout, ensuring proper handling and security measures.

Before executing the command, please follow these steps:

1. Directory Verification:
   - If the command will create new directories or files, first use the List tool to verify the parent directory exists and is the correct location
   - For example, before running "mkdir foo/bar", first use List to check that "foo" exists and is the intended parent directory

2. Command Execution:
   - Always quote file paths that contain spaces with double quotes (e.g., cd "path with spaces/file.txt")
   - Examples of proper quoting:
     - cd "/Users/name/My Documents" (correct)
     - cd /Users/name/My Documents (incorrect - will fail)
     - python "/path/with spaces/script.py" (correct)
     - python /path/with spaces/script.py (incorrect - will fail)
   - After ensuring proper quoting, execute the command.
   - Capture the output of the command.

Usage notes:
  - The command argument is required.
  - You can specify an optional timeout in milliseconds (up to 600000ms / 10 minutes). If not specified, commands will timeout after 120000ms (2 minutes).
  - It is very helpful if you write a clear, concise description of what this command does in 5-10 words.
  - If the output exceeds 30000 characters, output will be truncated before being returned to you.
  - VERY IMPORTANT: You MUST avoid using search commands like `find` and `grep`. Instead use Grep, Glob, or Task to search. You MUST avoid read tools like `cat`, `head`, `tail`, and `ls`, and use Read and List to read files.
  - If you _still_ need to run `grep`, STOP. ALWAYS USE ripgrep at `rg` (or /usr/bin/rg) first, which all opencode users have pre-installed.
  - When issuing multiple commands, use the ';' or '&&' operator to separate them. DO NOT use newlines (newlines are ok in quoted strings).
  - Try to maintain your current working directory throughout the session by using absolute paths and avoiding usage of `cd`. You may use `cd` if the User explicitly requests it.
"""

MAX_OUTPUT_LENGTH = 30000
DEFAULT_TIMEOUT = 120  # seconds
MAX_TIMEOUT = 600  # 10 minutes


# Simplified permission check
def check_permissions(command: str) -> None:
    # Simple check for dangerous commands
    dangerous_commands = ["rm", "cp", "mv", "mkdir", "touch", "chmod", "chown"]
    parts = shlex.split(command)
    if parts and parts[0] in dangerous_commands:
        for arg in parts[1:]:
            if arg.startswith("-") or (parts[0] == "chmod" and arg.startswith("+")):
                continue
            # Check if path is absolute and within allowed directory
            if os.path.isabs(arg):
                # Assume Instance.directory is current dir for simplicity
                if not arg.startswith(os.getcwd()):
                    raise ValueError(f"Path {arg} is not allowed")


async def execute_command(command: str, timeout: int) -> Dict[str, Any]:
    # Basic permission check
    check_permissions(command)

    def run_subprocess():
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),  # Assume current dir
        )
        return result

    try:
        result = await asyncio.get_event_loop().run_in_executor(None, run_subprocess)
        output = result.stdout + result.stderr
        if len(output) > MAX_OUTPUT_LENGTH:
            output = (
                output[:MAX_OUTPUT_LENGTH]
                + "\n\n(Output was truncated due to length limit)"
            )
        return {
            "title": command,
            "metadata": {
                "output": output,
                "exit": result.returncode,
                "description": "Command execution",
            },
            "output": output,
        }
    except subprocess.TimeoutExpired:
        raise ValueError("Command timed out")
    except Exception as e:
        raise ValueError(f"Command failed: {str(e)}")


BASH_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute",
                },
                "timeout": {
                    "type": "number",
                    "description": "Optional timeout in milliseconds",
                },
            },
            "required": ["command"],
        },
    },
}


bash_tool = Tool(definition=BASH_TOOL_DEFINITION, function=execute_command)
