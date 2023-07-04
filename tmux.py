from typing import List, Optional

import re
import sys
import subprocess

import fabric


class TmuxError(Exception):
    pass


class TmuxSession:
    """A Tmux session.

    Note, don't instantiate this directly, instead get a session using
    methods on the Tmux class.
    """
    name: str
    conn: fabric.Connection

    def __init__(self, name: str, connection: fabric.Connection):
        self.name = name
        self.conn = connection

    def run_command_in_window(self, window_index: int, command: str):
        """Executes a command in a tmux window."""
        self.conn.run(
            f"tmux send-keys -t {self.name}:{window_index} C-u '{command}' Enter",
            hide=True,
        )

    def open_terminal(self, detatch_others=True, readonly=False):
        """Opens a terminal on the local host.

        This will SSH into the destination connection and attach to
        the existing tmux session.

        """
        destination = f"{self.conn.user}@{self.conn.host}"
        args = [
            "gnome-terminal",
            "--",
            "ssh",
            "-t",
            destination,
            "tmux",
            "attach",
            "-t",
            self.name,
        ]
        if readonly:
            args.append("r")
        if detatch_others:
            args.append("-d")
        subprocess.run(args)

    def list_windows(self) -> List[str]:
        window_list = (
            self.conn.run(f"tmux list-windows -t {self.name}", hide=True)
            .stdout.strip()
            .split("\n")
        )
        return [window.split(":")[0] for window in window_list]

    def select_window(self, index: int):
        self.conn.run(f"tmux select-window -t {self.name}:{index}")

    def _get_os_specific_terminal(self) -> str:
        if sys.platform == "linux":
            return "gnome-terminal"
        else:
            raise Exception(f"Unsupported platform: {sys.platform}")


class Tmux:
    conn: fabric.Connection

    def __init__(self, connection: fabric.Connection):
        self.conn = connection

    def list_sessions(self) -> List[str]:
        """Returns a list of all tmux sessions on the remote host."""
        result = self.conn.run("tmux list-sessions", hide=True, warn=True)
        if result.exited != 0:
            return []
        session_list = (
            result.stdout.strip().split("\n")
        )
        return [session.split(":")[0] for session in session_list]

    def create_session(self, name: str) -> TmuxSession:
        """Creates a new named session on the remote host."""

        # If session already exists, we don't want to create another one.
        session = self.find_session(name)
        if session is not None:
            raise TmuxError(f"Session {name} already exists")

        # Actually create the session.
        self.conn.run(f"tmux new-session -d -t {name}")

        # Tmux appends an integer to the end of the specific session name,
        # here we look up the session we've just created to find out
        # the auto-assigned integer suffix.
        session = self.find_session(name)
        if session is None:
            raise Exception("Failed to create session")

        return session

    def find_or_create_sesssion(self, name: str) -> TmuxSession:
        """Returns a given session, creating it if it doesn't exist."""
        session = self.find_session(name)
        if session:
            return session
        else:
            return self.create_session(name)

    def find_session(self, name: str) -> Optional[TmuxSession]:
        for session in self.list_sessions():
            if re.match(re.escape(name) + r"\-\d+", session):
                return TmuxSession(session, self.conn)
        return None