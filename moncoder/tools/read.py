import os
from typing import Any, Dict, Optional

from .tool import Tool

DESCRIPTION = """Reads a file from the local filesystem. The filePath parameter must be an absolute path, not a relative path. By default, it reads up to 2000 lines starting from the beginning of the file. You can optionally specify a line offset and limit. Any lines longer than 2000 characters will be truncated. This tool cannot read binary files, including images.
"""

DEFAULT_READ_LIMIT = 2000
MAX_LINE_LENGTH = 2000


async def execute_read(
    filePath: str,
    offset: Optional[int] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    if not os.path.isabs(filePath):
        filePath = os.path.abspath(filePath)

    # Assume Instance.directory is current dir for simplicity
    if not filePath.startswith(os.getcwd()):
        raise ValueError(f"File {filePath} is not in the current working directory")

    if not os.path.exists(filePath):
        # Simple suggestion
        dir_path = os.path.dirname(filePath)
        base = os.path.basename(filePath)
        entries = os.listdir(dir_path)
        suggestions = [
            os.path.join(dir_path, e)
            for e in entries
            if base.lower() in e.lower() or e.lower() in base.lower()
        ][:3]
        if suggestions:
            raise ValueError(
                f"File not found: {filePath}\n\nDid you mean one of these?\n"
                + "\n".join(suggestions)
            )
        raise ValueError(f"File not found: {filePath}")

    limit = limit or DEFAULT_READ_LIMIT
    offset = offset or 0

    # Check if image
    ext = os.path.splitext(filePath)[1].lower()
    if ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"]:
        raise ValueError(
            f"This is an image file of type: {ext[1:].upper()}\nUse a different tool to process images"
        )

    # Check if binary
    with open(filePath, "rb") as f:
        chunk = f.read(4096)
        if b"\0" in chunk:
            raise ValueError(f"Cannot read binary file: {filePath}")

    with open(filePath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    start = offset
    end = min(offset + limit, len(lines))
    raw = [line.rstrip("\n\r") for line in lines[start:end]]
    content = [
        f"{(i + start + 1):5d}| {line[:MAX_LINE_LENGTH] + '...' if len(line) > MAX_LINE_LENGTH else line}"
        for i, line in enumerate(raw)
    ]

    output = "<file>\n" + "\n".join(content)
    if len(lines) > end:
        output += f"\n\n(File has more lines. Use 'offset' parameter to read beyond line {end})"
    output += "\n</file>"

    preview = "\n".join(raw[:20])

    return {
        "title": os.path.relpath(filePath, os.getcwd()),
        "output": output,
        "metadata": {"preview": preview},
    }


READ_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "read",
        "description": DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "filePath": {
                    "type": "string",
                    "description": "The path to the file to read",
                },
                "offset": {
                    "type": "number",
                    "description": "The line number to start reading from",
                },
                "limit": {
                    "type": "number",
                    "description": "The number of lines to read",
                },
            },
            "required": ["filePath"],
        },
    },
}


read_tool = Tool(definition=READ_TOOL_DEFINITION, function=execute_read)
