from dataclasses import dataclass
from datetime import datetime
from typing import Optional


class Message:
    def __init__(self, username: str, content=None, timestamp: datetime | None = None):
        self.username = username
        if isinstance(content, list):
            self.content = content
        elif isinstance(content, str):
            self.content = [{"type": "text", "content": content}]
        else:
            self.content = []
        self.timestamp = timestamp or datetime.now()

    def add_part(self, part_type: str, part_content: str):
        self.content.append({"type": part_type, "content": part_content})

    def __str__(self):
        # time_str = self.timestamp.strftime("%H:%M:%S")
        return " ".join(
            part["content"]
            if part["type"] == "text"
            else f"[{part['type']}]{part['content']}[/{part['type']}]"
            for part in self.content
        )
        # return f"[{time_str}] {self.username}: {content_str}"


@dataclass
class Session:
    id: int
    name: str
    start_time: datetime
    end_time: Optional[datetime] = None
