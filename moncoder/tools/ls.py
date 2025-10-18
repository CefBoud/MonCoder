import os
from typing import Any, Dict, List, Optional

from .tool import Tool

DESCRIPTION = """Lists files and directories in a given path. The path parameter must be an absolute path, not a relative path. You can optionally provide an array of glob patterns to ignore with the ignore parameter. You should generally prefer the Glob and Grep tools, if you know which directories to search.
"""

IGNORE_PATTERNS = [
    "node_modules/",
    "__pycache__/",
    ".git/",
    "dist/",
    "build/",
    "target/",
    "vendor/",
    "bin/",
    "obj/",
    ".idea/",
    ".vscode/",
    ".zig-cache/",
    "zig-out",
    ".coverage",
    "coverage/",
    "vendor/",
    "tmp/",
    "temp/",
    ".cache/",
    "cache/",
    "logs/",
    ".venv/",
    "venv/",
    "env/",
]

LIMIT = 100


async def execute_ls(
    path: Optional[str] = None, ignore: Optional[List[str]] = None
) -> Dict[str, Any]:
    search_path = os.path.abspath(path or os.getcwd())

    ignore_globs = [f"!{p}*" for p in IGNORE_PATTERNS]
    if ignore:
        ignore_globs.extend([f"!{p}" for p in ignore])

    # Simple file listing instead of Ripgrep
    files = []
    for root, dirs, filenames in os.walk(search_path):
        for filename in filenames:
            file_path = os.path.join(root, filename)
            rel_path = os.path.relpath(file_path, search_path)
            # Simple ignore check
            skip = False
            for pattern in ignore_globs:
                if pattern.startswith("!"):
                    pattern = pattern[1:]
                    if rel_path.startswith(pattern):
                        skip = True
                        break
            if not skip:
                files.append(rel_path)
        if len(files) >= LIMIT:
            break

    # Build directory structure
    dirs = set()
    files_by_dir = {}

    for file in files:
        dir_path = os.path.dirname(file)
        if dir_path not in files_by_dir:
            files_by_dir[dir_path] = []
        files_by_dir[dir_path].append(os.path.basename(file))

        # Add parent dirs
        parts = dir_path.split(os.sep) if dir_path != "." else []
        for i in range(len(parts) + 1):
            d = os.sep.join(parts[:i]) if i > 0 else "."
            dirs.add(d)

    def render_dir(dir_path: str, depth: int) -> str:
        indent = "  " * depth
        output = ""

        if depth > 0:
            output += f"{indent}{os.path.basename(dir_path)}/\n"

        child_indent = "  " * (depth + 1)
        children = [d for d in dirs if os.path.dirname(d) == dir_path and d != dir_path]
        children.sort()

        for child in children:
            output += render_dir(child, depth + 1)

        dir_files = files_by_dir.get(dir_path, [])
        for file in sorted(dir_files):
            output += f"{child_indent}{file}\n"

        return output

    output = f"{search_path}/\n" + render_dir(".", 0)

    return {
        "title": os.path.relpath(search_path, os.getcwd()),
        "metadata": {"count": len(files), "truncated": len(files) >= LIMIT},
        "output": output,
    }


LS_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "list",
        "description": DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The absolute path to the directory",
                },
                "ignore": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of glob patterns to ignore",
                },
            },
            "required": ["path"],
        },
    },
}

ls_tool = Tool(definition=LS_TOOL_DEFINITION, function=execute_ls)
