import difflib
import json
import logging
from typing import List

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Collapsible, LoadingIndicator, Markdown, Static, TextArea

from .type_defs import Message


class TextAreaInput(TextArea):
    """A subclass of TextArea with parenthesis-closing functionality."""

    def __init__(self, *args, submit: callable = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._submit_callback = submit

    def _on_key(self, event: events.Key) -> None:
        if event.character == "(":
            self.insert("()")
            self.move_cursor_relative(columns=-1)
            event.prevent_default()
        elif event.key == "shift+enter":
            self.insert(self.document.newline)
        elif event.key == "enter":
            self._submit_callback(self.text.strip())
            self.clear()
            self.cursor_location = (0, 0)
            event.prevent_default()


class AnimatedWelcome(Static):
    def __init__(self) -> None:
        super().__init__("", markup=False)
        self.full_text = "Welcome to MonCoder!\nYour AI-powered coding assistant."
        self.current_text = ""
        self.index = 0

    def on_mount(self) -> None:
        """Start the typewriter animation."""
        self.animate_text()

    def animate_text(self) -> None:
        """Add one character and schedule the next."""
        if self.index < len(self.full_text):
            self.current_text += self.full_text[self.index]
            self.update(self.current_text)
            self.index += 1
            self.set_timer(0.02, self.animate_text)  # Schedule next character


class ToolCallWidget(Static):
    def __init__(self, part: dict):
        super().__init__()
        self.part = part

    def compose(self) -> ComposeResult:
        title = f"{self.part['type']} {': ' + self.part['name'] if self.part.get('name') else ''}"
        if self.part.get("name") == "edit":
            # For edit tool calls, show the diff
            try:
                params = json.loads(self.part["content"])
                old_string = params.get("oldString", "")
                new_string = params.get("newString", "")
                file_path = params.get("filePath", "")
                yield DiffViewer(old_string, new_string, file_path)
            except (json.JSONDecodeError, KeyError):
                yield Collapsible(
                    Markdown(self.part["content"]),
                    title=title,
                    classes="tool-call-content",
                )
        else:
            yield Collapsible(
                Markdown(self.part["content"]),
                title=title,
                classes="tool-call-content",
            )


class DiffViewer(Static):
    def __init__(self, old_string: str, new_string: str, file_path: str):
        super().__init__()
        self.old_string = old_string
        self.new_string = new_string
        self.file_path = file_path

    def compose(self) -> ComposeResult:
        with Collapsible(
            title="Edit Diff",
            classes="diff-viewer",
            collapsed=False,
        ):
            yield Markdown(f"**File:** {self.file_path}")
            with ScrollableContainer(classes="diff-viewer-scroll"):
                with Vertical():
                    for line in self.compute_diff_lines():
                        yield Static(line["text"], classes=f"diff-line {line['type']}")

    def compute_diff_lines(self) -> list:
        old_lines = self.old_string.splitlines(keepends=True)
        new_lines = self.new_string.splitlines(keepends=True)
        diff_lines = list(
            difflib.unified_diff(old_lines, new_lines, fromfile="old", tofile="new")
        )

        if not diff_lines:
            return [{"text": "No differences found.", "type": "none"}]

        line_info = []
        for line in diff_lines:
            if line.startswith("+") and not line.startswith("+++"):
                line_info.append({"text": line, "type": "addition"})
            elif line.startswith("-") and not line.startswith("---"):
                line_info.append({"text": line, "type": "deletion"})
            elif line.startswith("@@"):
                line_info.append({"text": line, "type": "context"})
            else:
                line_info.append({"text": line, "type": "header"})

        return line_info


class MessageWidget(Static):
    def __init__(self, message: Message, is_own_message: bool = False):
        self.message = message
        self.is_own_message = is_own_message
        super().__init__()

    def compose(self) -> ComposeResult:
        time_str = self.message.timestamp.strftime("%H:%M")
        # Parse content to handle tool calls separately
        for index, part in enumerate(self.message.content):
            part_type = part.get("type", "text")
            part_content = part.get("content", "")
            css_class = (
                "text-content " + "assistant"
                if self.message.username == "assistant"
                else "user"
            )
            if part_type == "text":
                yield Collapsible(
                    Markdown(part_content),
                    title=f"{self.message.username} ({time_str})" if index == 0 else "",
                    classes=css_class,
                    collapsed=False,
                )
            # yield Markdown(part_content)
            elif part_type in ["tool_call", "tool_result"]:
                yield ToolCallWidget(part)
            else:
                logging.error(f"Unknown part type {part_type}")


class ChatRoom(ScrollableContainer):
    def __init__(self):
        super().__init__()
        self.messages: List[Message] = []
        self.last_message_widget = None
        self.spinner: Horizontal | None = None

    def add_message(self, message: Message, is_own_message: bool = False):
        self.messages.append(message)
        message_widget = MessageWidget(message, is_own_message)
        self.last_message_widget = message_widget
        # self.mount(message_widget)
        if self.spinner and self.spinner.parent:
            self.mount(message_widget, before=self.spinner)
        else:
            self.mount(message_widget)
        self.scroll_end()

    def refresh_last_message(self):
        last_message = self.messages[-1]
        # Remove the old widget
        if self.last_message_widget:
            is_own_message = self.last_message_widget.is_own_message
            self.last_message_widget.remove()
            # Add the updated widget
            new_widget = MessageWidget(last_message, is_own_message=is_own_message)
            self.last_message_widget = new_widget
            self.mount(new_widget, before=self.spinner)
            self.scroll_end(animate=True, duration=0)

    async def show_spinner(self, text: str = "Thinking..."):
        """Add a loading spinner to the end of the chatroom."""
        if not self.spinner:
            self.spinner = Horizontal(
                LoadingIndicator(id="chat-spinner"),
                Static(text, id="spinner-text"),
                id="spinner-row",
            )
        if not self.spinner.parent:
            self.mount(self.spinner)
            self.scroll_end()

        self.spinner.display = True

    async def hide_spinner(self):
        """Remove the spinner if it's currently displayed."""
        if self.spinner:
            self.spinner.display = False
