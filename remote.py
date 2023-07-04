import fabric


class RemoteHost:
    """Filesystem action to take against a remote host."""

    def __init__(self, conn: fabric.Connection):
        self.conn = conn

    def touch(self, path: str):
        """Create a file or updates its last updated time."""
        self.conn.run(f"touch {path}")

    def directory_exists(self, path: str) -> bool:
        """Returns True if a directory exists, False otherwise."""
        return self.conn.run(f"test -d {path}", warn=True, hide=True).exited == 0

    def file_exists(self, path: str) -> bool:
        """Returns True if a file exists, False otherwise."""
        return self.conn.run(f"test -f {path}", warn=True, hide=True).exited == 0

    def localhost_port_serving_http(self, port: int) -> bool:
        """Returns True if localhost:port is responding to HTTP requests."""
        return (
            self.conn.run(
                f"curl localhost:{port} > /dev/null", warn=True, hide=True
            ).exited
            == 0
        )

    def is_process_running(self, process_name: str) -> bool:
        """Returns True if given process is currently running."""
        result = self.conn.run(
            f"ps aux | grep '{process_name}' | grep -v grep",
            warn=True,
            hide=True,
        )
        return result.exited == 0 and process_name in result.stdout
