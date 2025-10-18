from typing import Any, Dict, Optional
import aiohttp
from bs4 import BeautifulSoup
import html2text

from .tool import Tool

DESCRIPTION = """- Fetches content from a specified URL
- Takes a URL and a prompt as input
- Fetches the URL content, converts HTML to markdown
- Returns the model's response about the content
- Use this tool when you need to retrieve and analyze web content

Usage notes:
  - IMPORTANT: if another tool is present that offers better web fetching capabilities, is more targeted to the task, or has fewer restrictions, prefer using that tool instead of this one.
  - The URL must be a fully-formed valid URL
  - HTTP URLs will be automatically upgraded to HTTPS
  - The prompt should describe what information you want to extract from the page
  - This tool is read-only and does not modify any files
  - Results may be summarized if the content is very large
"""

MAX_RESPONSE_SIZE = 5 * 1024 * 1024  # 5MB
DEFAULT_TIMEOUT = 30  # seconds
MAX_TIMEOUT = 120  # 2 minutes


def extract_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    # Get text
    text = soup.get_text()
    # Clean up whitespace
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = " ".join(chunk for chunk in chunks if chunk)
    return text


def convert_html_to_markdown(html: str) -> str:
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False
    h.ignore_tables = False
    return h.handle(html)


async def execute_webfetch(
    url: str,
    format: str,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    # Validate URL
    if not url.startswith("http://") and not url.startswith("https://"):
        raise ValueError("URL must start with http:// or https://")

    # Upgrade HTTP to HTTPS
    if url.startswith("http://"):
        url = url.replace("http://", "https://", 1)

    timeout = min(timeout or DEFAULT_TIMEOUT, MAX_TIMEOUT)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Adjust Accept header based on format
    if format == "markdown":
        headers["Accept"] = (
            "text/markdown;q=1.0, text/x-markdown;q=0.9, text/plain;q=0.8, text/html;q=0.7, */*;q=0.1"
        )
    elif format == "text":
        headers["Accept"] = (
            "text/plain;q=1.0, text/markdown;q=0.9, text/html;q=0.8, */*;q=0.1"
        )
    elif format == "html":
        headers["Accept"] = (
            "text/html;q=1.0, application/xhtml+xml;q=0.9, text/plain;q=0.8, text/markdown;q=0.7, */*;q=0.1"
        )

    try:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=timeout_obj) as session:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()

                # Check content length
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > MAX_RESPONSE_SIZE:
                    raise ValueError("Response too large (exceeds 5MB limit)")

                content = await response.text()
                if len(content.encode("utf-8")) > MAX_RESPONSE_SIZE:
                    raise ValueError("Response too large (exceeds 5MB limit)")

                content_type = response.headers.get("content-type", "").lower()

        # Handle based on format
        if format == "markdown" and "text/html" in content_type:
            output = convert_html_to_markdown(content)
        elif format == "text" and "text/html" in content_type:
            output = extract_text_from_html(content)
        else:
            output = content

        return {
            "title": f"{url} ({content_type})",
            "output": output,
            "metadata": {},
        }

    except aiohttp.ClientError as e:
        raise ValueError(f"Request failed: {str(e)}")


WEBFETCH_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "webfetch",
        "description": DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch content from",
                },
                "format": {
                    "type": "string",
                    "enum": ["text", "markdown", "html"],
                    "description": "The format to return the content in (text, markdown, or html)",
                },
                "timeout": {
                    "type": "number",
                    "description": "Optional timeout in seconds (max 120)",
                },
            },
            "required": ["url", "format"],
        },
    },
}

webfetch_tool = Tool(definition=WEBFETCH_TOOL_DEFINITION, function=execute_webfetch)
