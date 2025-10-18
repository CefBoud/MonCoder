# Central registry
TOOL_REGISTRY = {}


class Tool:
    def __init__(self, definition, function):
        self.definition = definition
        self.function = function
        TOOL_REGISTRY[self.definition["function"]["name"]] = self


def register_tool(tool: Tool):
    TOOL_REGISTRY[tool.definition["function"]["name"]] = tool
