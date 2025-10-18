import json
import os
import sqlite3
import logging
from datetime import datetime
from typing import List, Optional

from .type_defs import Message, Session
from moncoder import config


class SessionManager:
    def __init__(self, db_path=config.Path.data / "moncoder.db"):
        self.db_conn = sqlite3.connect(db_path)
        self.db_conn.execute(
            """CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY, name TEXT, start_time DATETIME, end_time DATETIME, project TEXT)"""
        )
        self.db_conn.execute(
            """CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, session_id INTEGER, username TEXT, timestamp DATETIME, content TEXT, FOREIGN KEY(session_id) REFERENCES sessions(id))"""
        )
        self.db_conn.commit()
        self.current_session_id = None

    def start_session(self, name: Optional[str] = None) -> Session:
        if name is None:
            name = f"session {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        start_time = datetime.now()
        project_path = os.path.abspath(os.getcwd())
        cursor = self.db_conn.execute(
            "INSERT INTO sessions (name, start_time, project) VALUES (?, ?, ?)",
            (name, start_time, project_path),
        )
        self.db_conn.commit()
        session_id = cursor.lastrowid
        if session_id is None:
            raise ValueError("Failed to create session")
        self.current_session_id = session_id
        return Session(id=session_id, name=name, start_time=start_time)

    def end_session(self) -> None:
        if self.current_session_id:
            self.db_conn.execute(
                "UPDATE sessions SET end_time = ? WHERE id = ?",
                (datetime.now(), self.current_session_id),
            )
            self.db_conn.commit()

    def update_session_name(self, name: str, session_id: Optional[int] = None) -> None:
        if not session_id:
            if not self.current_session_id:
                logging.error(
                    "update_session_name called but there is no current_session_id"
                )
                return
            session_id = self.current_session_id
        self.db_conn.execute(
            "UPDATE sessions SET name = ? WHERE id = ?",
            (name, session_id),
        )
        self.db_conn.commit()

    def get_message_count(self, session_id: int) -> int:
        cursor = self.db_conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?",
            (session_id,),
        )
        return cursor.fetchone()[0]

    def save_message(
        self, message
    ) -> None:  # Assuming message has username, timestamp, content
        if not self.current_session_id:
            raise ValueError("current_session_id is undefined")
        self.db_conn.execute(
            "INSERT INTO messages (session_id, username, timestamp, content) VALUES (?, ?, ?, ?)",
            (
                self.current_session_id,
                message.username,
                message.timestamp,
                json.dumps(message.content),
            ),
        )
        self.db_conn.commit()

    def update_message(self, content: str) -> None:
        if not self.current_session_id:
            raise ValueError("current_session_id is undefined")
        # Update the most recent message in the current session
        self.db_conn.execute(
            "UPDATE messages SET content = ? WHERE id = (SELECT MAX(id) FROM messages WHERE session_id = ?)",
            (json.dumps(content), self.current_session_id),
        )
        self.db_conn.commit()

    def load_session(self, session_id: int) -> List[Message]:
        cursor = self.db_conn.execute(
            "SELECT username, timestamp, content FROM messages WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        )
        self.current_session_id = session_id
        rows = cursor.fetchall()
        messages = []
        for row in rows:
            username, timestamp_str, content_str = row
            timestamp = datetime.fromisoformat(timestamp_str)
            content = json.loads(content_str)
            msg = Message(username=username, content=content, timestamp=timestamp)
            messages.append(msg)
        return messages

    def list_sessions(self) -> List[Session]:
        project_path = os.path.abspath(os.getcwd())
        cursor = self.db_conn.execute(
            "SELECT id, name, start_time, end_time FROM sessions WHERE project = ? ORDER BY start_time DESC",
            (project_path,),
        )
        rows = cursor.fetchall()
        sessions = []
        for row in rows:
            sessions.append(
                Session(
                    id=row[0],
                    name=row[1],
                    start_time=datetime.fromisoformat(row[2]),
                    end_time=datetime.fromisoformat(row[3]) if row[3] else None,
                )
            )
        return sessions
