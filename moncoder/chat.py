import asyncio
import logging
from typing import Iterable
import getpass

from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import (
    Footer,
    Header,
)

from .llm import get_llm_completion, generate_session_title
from .session import SessionManager
from .type_defs import Message
from .widgets import AnimatedWelcome, ChatRoom, TextAreaInput

# Set to True when testing and wanting to skip LLM calls
SKIP_LLM = False


class ChatApp(App):
    """A Textual chat application."""

    CSS_PATH = "chat.tcss"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.username = getpass.getuser()
        self.chat_room = None
        self.user_list = None
        self.message_input = None
        self.session_manager = SessionManager()
        self.session_palette_mode = False
        self.moncoder_label = None
        self.first_message = True

        # Async event for message submissions
        self.submission_event = asyncio.Event()
        self.pending_message = None

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        if self.session_palette_mode:
            # Show session selection commands
            sessions = self.session_manager.list_sessions()
            for index, session in enumerate(sessions):
                # Use zero-width spaces (invisible) to preserve session order (Textual default to alphabetical)
                display_name = f"{'\u200b' * index}{session.name}"
                yield SystemCommand(
                    display_name,
                    f"Load session '{session.name}'",
                    lambda sid=session.id: self.load_session_and_reset(sid),
                )
        else:
            yield SystemCommand(
                "List Sessions", "List all chat sessions", self.list_sessions_command
            )
            # Show regular commands
            yield from super().get_system_commands(screen)

    def list_sessions_command(self):
        """Command to list all sessions and switch to session palette mode."""
        self.session_palette_mode = True
        self.action_command_palette()

    def load_session_command(self, session_id: int):
        """Command to load a specific session."""
        messages = self.session_manager.load_session(session_id)
        if messages:
            # Clear current chat
            for widget in list(self.chat_room.children):
                widget.remove()
            self.chat_room.messages.clear()
            # Load messages
            for msg in messages:
                self.chat_room.add_message(
                    msg, is_own_message=msg.username != "assistant"
                )
            # Set current session
            self.update_sub_title()
            if self.first_message:
                self.first_message = False
                self.moncoder_label.remove()

    def load_session_and_reset(self, session_id: int):
        """Load a session and reset the palette mode."""
        self.load_session_command(session_id)
        self.session_palette_mode = False

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()

        with Container(id="chat_container"):
            # yield Static("moncoder", id="moncoder_label")
            if self.first_message:
                self.moncoder_label = Container(AnimatedWelcome())
                self.moncoder_label.id = "moncoder_label"
                yield self.moncoder_label
            self.chat_room = ChatRoom()
            self.chat_room.id = "chat_room"
            yield self.chat_room

        with Container(id="input_container"):
            self.message_input = TextAreaInput(
                submit=self.on_input_submitted, placeholder="Dazzle yourself ..."
            )
            self.message_input.id = "message_input"
            yield self.message_input

        yield Footer()

    def on_mount(self) -> None:
        """Called when app starts."""
        self.title = "MonCoder"
        self.sub_title = f"User: {self.username}"

        # Focus on input
        self.message_input.focus()
        # Start the background task for handling LLM responses
        asyncio.create_task(self.handle_llm_responses())
        # Get reference to moncoder label

    def update_sub_title(self):
        """Update the sub-title to include current session info."""
        session_name = "New Session"
        if self.session_manager.current_session_id:
            sessions = self.session_manager.list_sessions()
            for session in sessions:
                if session.id == self.session_manager.current_session_id:
                    session_name = session.name
                    break
        self.sub_title = f"Logged in as: {self.username} | Session: {session_name}"

    def on_input_submitted(self, message_text: str) -> None:
        """Called when user submits a message."""
        logging.info("on_input_submitted")
        if self.first_message:
            self.first_message = False
            self.moncoder_label.remove()
        if message_text:
            # Handle special commands
            if message_text.startswith("/"):
                self.handle_command(message_text)
            else:
                if not SKIP_LLM and not self.session_manager.current_session_id:
                    self.session_manager.start_session()
                    asyncio.create_task(
                        generate_session_title(
                            message_text,
                            lambda title: self.session_manager.update_session_name(
                                title
                            ),
                            lambda e: self.notify(
                                str(e),
                                title="Session Title Generation Failed",
                                severity="error",
                            ),
                        )
                    )
                    self.update_sub_title()
                # Create and add the message
                message = Message(self.username, message_text)
                self.chat_room.add_message(message, is_own_message=True)
                if not SKIP_LLM:
                    self.session_manager.save_message(message)
                # Clear the input
                self.message_input.value = ""
                # Trigger the async task
                self.pending_message = message
                logging.info("submission_event.set()")
                if not SKIP_LLM:
                    self.submission_event.set()
                logging.info("submission_event.set() after")

    def handle_command(self, command: str):
        """Handle special chat commands."""
        parts = command.split(" ", 1)
        cmd = parts[0].lower()

        if cmd == "/help":
            help_msg = Message(
                "System",
                "Commands: /help, /clear",
            )
            self.chat_room.add_message(help_msg)

        elif cmd == "/clear":
            # Clear all messages (remove all children from chat room)
            for widget in list(self.chat_room.children):
                widget.remove()
            self.chat_room.messages.clear()

        else:
            error_msg = Message(
                "System", f"Unknown command: {cmd}. Type /help for available commands."
            )
            self.chat_room.add_message(error_msg)

    async def handle_llm_responses(self):
        while True:
            logging.info("handle_llm_responses")
            await self.submission_event.wait()
            message = self.pending_message
            self.submission_event.clear()
            if message:
                await self.chat_room.show_spinner()
                first = True
                parts = []
                async for chunk in get_llm_completion(
                    self.chat_room.messages,
                    lambda e: self.notify(
                        str(e), title="LLM Response Error", severity="error"
                    ),
                ):
                    await self.chat_room.hide_spinner()
                    logging.info(
                        f"chunk loop messages[-1]:{self.chat_room.messages[-1]} - chunk: {chunk}"
                    )
                    # self.refresh()
                    if chunk:
                        if first:
                            parts.append(chunk)
                            msg = Message("assistant", parts.copy())
                            self.chat_room.add_message(msg)
                            self.session_manager.save_message(msg)
                            first = False
                        else:
                            if parts[-1]["type"] == "text" and chunk["type"] == "text":
                                parts[-1]["content"] += chunk["content"]
                            else:
                                parts.append(chunk)
                            last_message = self.chat_room.messages[-1]
                            last_message.content = parts.copy()
                            self.session_manager.update_message(last_message.content)
                            self.chat_room.refresh_last_message()
                    await self.chat_room.show_spinner()
                await self.chat_room.hide_spinner()


def run():
    app = ChatApp()
    app.run()
