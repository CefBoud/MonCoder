import asyncio
import aiohttp
import os
import platform
import shutil
import subprocess
import tarfile
import zipfile
from typing import Any, Dict, Optional

from moncoder.config import Path
from .tool import Tool

DESCRIPTION = r"""- Fast content search tool that works with any codebase size
- Searches file contents using regular expressions
- Supports full regex syntax (eg. "log.*Error", "function\s+\w+", etc.)
- Filter files by pattern with the include parameter (eg. "*.js", "*.{ts,tsx}")
- Returns file paths with at least one match sorted by modification time
- Use this tool when you need to find files containing specific patterns
- If you need to identify/count the number of matches within files, use the Bash tool with `rg` (ripgrep) directly. Do NOT use `grep`.
"""

# Platform configurations for ripgrep binaries
PLATFORM = {
    "x64-darwin": {"platform": "apple-darwin", "extension": "tar.gz"},
    "arm64-darwin": {"platform": "aarch64-apple-darwin", "extension": "tar.gz"},
    "x64-linux": {"platform": "x86_64-unknown-linux-musl", "extension": "tar.gz"},
    "arm64-linux": {"platform": "aarch64-unknown-linux-gnu", "extension": "tar.gz"},
    "x64-win32": {"platform": "x86_64-pc-windows-msvc", "extension": "zip"},
    "arm64-win32": {"platform": "aarch64-pc-windows-msvc", "extension": "zip"},
}


async def install_ripgrep() -> str:
    """
    Install ripgrep if not available.
    Returns the path to the ripgrep binary.
    """
    # Check if rg is in PATH
    rg_path = shutil.which("rg")
    if rg_path:
        return rg_path

    # Use a default bin path or from config if available
    # For simplicity, use ~/.local/bin
    bin_path = Path.bin
    bin_path.mkdir(parents=True, exist_ok=True)

    rg_filepath = bin_path / ("rg.exe" if platform.system() == "Windows" else "rg")

    if rg_filepath.exists():
        return str(rg_filepath)

    # Determine platform
    arch = platform.machine()
    if arch == "x86_64":
        arch = "x64"
    elif arch != "arm64":
        raise ValueError(f"Unsupported architecture: {arch}")

    os_name = platform.system().lower()
    platform_key = f"{arch}-{os_name}"

    if platform_key not in PLATFORM:
        raise ValueError(f"Unsupported platform: {platform_key}")

    config = PLATFORM[platform_key]
    version = "14.1.1"
    filename = f"ripgrep-{version}-{config['platform']}.{config['extension']}"
    url = (
        f"https://github.com/BurntSushi/ripgrep/releases/download/{version}/{filename}"
    )

    # Download the binary
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise RuntimeError(f"Failed to download ripgrep: {response.status}")
            buffer = await response.read()

    # Write to archive path
    archive_path = bin_path / filename
    with open(archive_path, "wb") as f:
        f.write(buffer)

    # Extract
    if config["extension"] == "tar.gz":
        with tarfile.open(archive_path, "r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith("rg"):
                    tar.extract(member, bin_path)
                    extracted_path = bin_path / member.name
                    if extracted_path.exists():
                        shutil.move(extracted_path, rg_filepath)
                    break
    elif config["extension"] == "zip":
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            for file in zip_ref.namelist():
                if file.endswith("rg.exe"):
                    zip_ref.extract(file, bin_path)
                    extracted_path = bin_path / file
                    if extracted_path.exists():
                        shutil.move(extracted_path, rg_filepath)
                    break

    # Clean up archive
    if archive_path.exists():
        archive_path.unlink()

    # Set executable permissions
    if os_name != "windows":
        rg_filepath.chmod(0o755)

    return str(rg_filepath)


async def execute_grep(
    pattern: str, path: Optional[str] = None, include: Optional[str] = None
) -> Dict[str, Any]:
    if not pattern:
        raise ValueError("pattern is required")

    search_path = path or os.getcwd()

    # Find or install ripgrep
    rg_path = await install_ripgrep()

    args = ["-n", pattern]
    if include:
        args.extend(["--glob", include])
    args.append(search_path)

    def run_rg():
        result = subprocess.run(
            [rg_path] + args, capture_output=True, text=True, cwd=os.getcwd()
        )
        return result

    result = await asyncio.get_event_loop().run_in_executor(None, run_rg)

    if result.returncode == 1:
        return {
            "title": pattern,
            "metadata": {"matches": 0, "truncated": False},
            "output": "No files found",
        }

    if result.returncode != 0:
        raise ValueError(f"ripgrep failed: {result.stderr}")

    lines = result.stdout.strip().split("\n")
    matches = []

    for line in lines:
        if not line:
            continue
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        file_path, line_num_str, line_text = parts
        line_num = int(line_num_str)

        try:
            stat = os.stat(file_path)
            mod_time = stat.st_mtime
        except Exception:
            continue

        matches.append(
            {
                "path": file_path,
                "modTime": mod_time,
                "lineNum": line_num,
                "lineText": line_text,
            }
        )

    matches.sort(key=lambda x: x["modTime"], reverse=True)

    limit = 100
    truncated = len(matches) > limit
    final_matches = matches[:limit] if truncated else matches

    if not final_matches:
        return {
            "title": pattern,
            "metadata": {"matches": 0, "truncated": False},
            "output": "No files found",
        }

    output_lines = [f"Found {len(final_matches)} matches"]

    current_file = ""
    for match in final_matches:
        if current_file != match["path"]:
            if current_file:
                output_lines.append("")
            current_file = match["path"]
            output_lines.append(f"{match['path']}:")
        output_lines.append(f"  Line {match['lineNum']}: {match['lineText']}")

    if truncated:
        output_lines.append("")
        output_lines.append(
            "(Results are truncated. Consider using a more specific path or pattern.)"
        )

    return {
        "title": pattern,
        "metadata": {"matches": len(final_matches), "truncated": truncated},
        "output": "\n".join(output_lines),
    }


GREP_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "grep",
        "description": DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The regex pattern to search for",
                },
                "path": {"type": "string", "description": "The directory to search in"},
                "include": {"type": "string", "description": "File pattern to include"},
            },
            "required": ["pattern"],
        },
    },
}

grep_tool = Tool(definition=GREP_TOOL_DEFINITION, function=execute_grep)
