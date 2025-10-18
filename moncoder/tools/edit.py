import os
import re
from typing import Any, Dict, List

from .tool import Tool

DESCRIPTION = """
Performs exact string replacements in files. 
Usage:
- You must use your `Read` tool at least once in the conversation before editing. This tool will error if you attempt an edit without reading the file. 
- When editing text from Read tool output, ensure you preserve the exact indentation (tabs/spaces) as it appears AFTER the line number prefix. The line number prefix format is: spaces + line number + tab. Everything after that tab is the actual file content to match. Never include any part of the line number prefix in the oldString or newString.
- ALWAYS prefer editing existing files in the codebase. NEVER write new files unless explicitly required.
- Only use emojis if the user explicitly requests it. Avoid adding emojis to files unless asked.
- The edit will FAIL if `oldString` is not found in the file with an error "oldString not found in content".
- The edit will FAIL if `oldString` is found multiple times in the file with an error "oldString found multiple times and requires more code context to uniquely identify the intended match". Either provide a larger string with more surrounding context to make it unique or use `replaceAll` to change every instance of `oldString`. 
- Use `replaceAll` for replacing and renaming strings across the file. This parameter is useful if you want to rename a variable for instance.
- When including newlines in newString, use actual \n characters (not escaped double backslash \\n) to avoid inserting literal backslashes.
"""


async def execute_edit(
    filePath: str,
    oldString: str,
    newString: str,
    replaceAll: bool = False,
) -> Dict[str, Any]:
    if not filePath:
        raise ValueError("filePath is required")
    if oldString == newString:
        raise ValueError("oldString and newString must be different")
    if not os.path.isabs(filePath):
        filePath = os.path.abspath(filePath)

    # Assume Instance.directory is current dir for simplicity
    if not filePath.startswith(os.getcwd()):
        raise ValueError(f"File {filePath} is not in the current working directory")

    if not os.path.exists(filePath):
        raise FileNotFoundError(f"File {filePath} not found")
    if os.path.isdir(filePath):
        raise IsADirectoryError(f"Path is a directory, not a file: {filePath}")

    with open(filePath, "r", encoding="utf-8") as f:
        content = f.read()

    new_content = replace(content, oldString, newString, replaceAll)

    with open(filePath, "w", encoding="utf-8") as f:
        f.write(new_content)

    return {
        "title": os.path.relpath(filePath, os.getcwd()),
        "output": f"Edited {filePath}",
        "metadata": {},
    }


def simple_replacer(_: str, find: str) -> List[str]:
    return [find]


def line_trimmed_replacer(content: str, find: str) -> List[str]:
    original_lines = content.split("\n")
    search_lines = find.split("\n")
    if search_lines and search_lines[-1] == "":
        search_lines.pop()

    results = []
    for i in range(len(original_lines) - len(search_lines) + 1):
        matches = True
        for j in range(len(search_lines)):
            original_trimmed = original_lines[i + j].strip()
            search_trimmed = search_lines[j].strip()
            if original_trimmed != search_trimmed:
                matches = False
                break
        if matches:
            start_index = sum(len(original_lines[k]) + 1 for k in range(i))
            end_index = start_index + sum(
                len(original_lines[i + k]) + (1 if k < len(search_lines) - 1 else 0)
                for k in range(len(search_lines))
            )
            results.append(content[start_index:end_index])
    return results


def whitespace_normalized_replacer(content: str, find: str) -> List[str]:
    def normalize_whitespace(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    normalized_find = normalize_whitespace(find)
    lines = content.split("\n")
    results = []

    # Single line matches
    for line in lines:
        if normalize_whitespace(line) == normalized_find:
            results.append(line)
        else:
            normalized_line = normalize_whitespace(line)
            if normalized_find in normalized_line:
                words = find.strip().split()
                if words:
                    pattern = r"\s+".join(re.escape(word) for word in words)
                    match = re.search(pattern, line)
                    if match:
                        results.append(match.group(0))

    # Multi-line matches
    find_lines = find.split("\n")
    if len(find_lines) > 1:
        for i in range(len(lines) - len(find_lines) + 1):
            block = "\n".join(lines[i : i + len(find_lines)])
            if normalize_whitespace(block) == normalized_find:
                results.append(block)
    return results


def indentation_flexible_replacer(content: str, find: str) -> List[str]:
    def remove_indentation(text: str) -> str:
        lines = text.split("\n")
        non_empty_lines = [line for line in lines if line.strip()]
        if not non_empty_lines:
            return text
        min_indent = min(
            len(match.group(1)) if (match := re.match(r"^(\s*)", line)) else 0
            for line in non_empty_lines
        )
        return "\n".join(line[min_indent:] if line.strip() else line for line in lines)

    normalized_find = remove_indentation(find)
    content_lines = content.split("\n")
    find_lines = find.split("\n")
    results = []

    for i in range(len(content_lines) - len(find_lines) + 1):
        block = "\n".join(content_lines[i : i + len(find_lines)])
        if remove_indentation(block) == normalized_find:
            results.append(block)
    return results


def replace(
    content: str, old_string: str, new_string: str, replace_all: bool = False
) -> str:
    if old_string == new_string:
        raise ValueError("oldString and newString must be different")

    not_found = True
    replacers = [
        simple_replacer,
        line_trimmed_replacer,
        whitespace_normalized_replacer,
        indentation_flexible_replacer,
    ]

    for replacer in replacers:
        for search in replacer(content, old_string):
            index = content.find(search)
            if index == -1:
                continue
            not_found = False
            if replace_all:
                return content.replace(search, new_string)
            last_index = content.rfind(search)
            if index != last_index:
                continue
            return content[:index] + new_string + content[index + len(search) :]

    if not_found:
        raise ValueError("oldString not found in content")
    raise ValueError(
        "oldString found multiple times and requires more code context to uniquely identify the intended match"
    )


EDIT_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "edit",
        "description": DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "filePath": {
                    "type": "string",
                    "description": "The absolute path to the file to modify",
                },
                "oldString": {
                    "type": "string",
                    "description": "The text to replace",
                },
                "newString": {
                    "type": "string",
                    "description": "The text to replace it with (must be different from oldString)",
                },
                "replaceAll": {
                    "type": "boolean",
                    "description": "Replace all occurrences of oldString (default false)",
                },
            },
            "required": ["filePath", "oldString", "newString"],
        },
    },
}

edit_tool = Tool(EDIT_TOOL_DEFINITION, execute_edit)
