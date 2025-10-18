from moncoder.tools.tool import Tool, TOOL_REGISTRY

# Brief descriptions of each tool for the loader
TOOL_BRIEFS = {
    "bash": "Executes bash commands with security checks and timeout.",
    "edit": "Performs exact string replacements in files.",
    "grep": "Searches file contents using regex patterns.",
    "list": "Lists files and directories in a given path.",
    "read": "Reads files from the local filesystem.",
    "webfetch": "Fetches and analyzes web content from URLs.",
    "glob": "Fast file pattern matching for finding files.",
    "write": "Writes content to files on the local filesystem.",
    "todowrite": "Creates and manages structured task lists.",
    "todoread": "Reads the current todo list.",
    "task": "Launches agents for complex multi-step tasks.",
}

DESCRIPTION = f"""Loader tool for managing available tools. Provides brief descriptions of each tool and allows activating multiple tools by name.

Available tools:
{chr(10).join(f"- {name}: {desc}" for name, desc in TOOL_BRIEFS.items())}

Choosing tools will make them available in the model context for the next interaction.

Usage: Provide a list of exact tool names you want to activate."""


async def loader_execute(tool_names: list) -> str:
    from moncoder.llm import active_tools
    if not isinstance(tool_names, list):
        return "Error: tool_names must be a list of strings."
    
    existing_tool_names = [tool["function"]["name"] for tool in active_tools]
    activated = []
    failed = []
    errors = []
    # Add the tools to active_tools in llm.py
    for name in tool_names:
        if name in existing_tool_names:
            errors.append(f"{name} already loaded.")
            continue
        if name not in TOOL_BRIEFS:
            failed.append(name)
            continue
        tool = TOOL_REGISTRY.get(name)
        if tool:
            active_tools.append(tool.definition)
            activated.append(name)
        else:
            failed.append(name)
    response = (
        f"Activated tools: {', '.join(activated)}."
        if activated
        else "No tools activated."
    )
    if failed:
        response += f" Failed to activate: {', '.join(failed)}. Available tools: {', '.join(TOOL_BRIEFS.keys())}"
    response += " They are now available for use in the next message. After this, they will be removed from context."
    if errors:
        response += f"Errors: {', '.join(errors)}"
    return response


LOADER_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "loader",
        "description": DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "tool_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of tool names to activate and add to context.",
                },
            },
            "required": ["tool_names"],
        },
    },
}

loader_tool = Tool(definition=LOADER_TOOL_DEFINITION, function=loader_execute)
