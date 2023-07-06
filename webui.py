from typing import Dict, Optional
import sys
import time
import os
import enum
import fabric

from dataclasses import dataclass
from dataclasses_json import DataClassJsonMixin

from lambda_labs import InstanceID

from tmux import Tmux, TmuxSession
from remote import RemoteHost

from lambda_labs import LambdaAPI, STATUS_ACTIVE

from instances import prompt_user_for_instance_type


WEBUI_INSTALL_COMMAND = "bash <(wget -qO- https://raw.githubusercontent.com/AUTOMATIC1111/stable-diffusion-webui/master/webui.sh)"
WEBUI_DIRECTORY = "/home/ubuntu/stable-diffusion-webui"
WEBUI_SCRIPT = os.path.join(WEBUI_DIRECTORY, "webui.sh")

# Installed
# Started but not accessible
# HTTP accessible


class WebUIStatus(str, enum.Enum):
    UNKNOWN = "unknown"
    # Starting the LambdaLabs VM.
    CREATING_INSTANCE = "creating_instance"
    # Installing WebUI, extensions, and downloading models.
    INSTALLING = "installing_webui"
    # Waiting for the WebUI to start.
    STARTING = "starting_webui"
    # WebUI is running and ready for traffic.
    RUNNING = "running"
    # Currently killing the WebUI and waiting for the process to die.
    STOPPING = "stopping"
    # WebUI is stopped, but instance is still running.
    STOPPED = "stopped"
    # Terminating the LambdaLabs instance.
    TERMINATING = "terminating"
    # LambdaLabs instance is terminated.
    TERMINATED = "terminated"


@dataclass
class WebUIState(DataClassJsonMixin):
    status: WebUIStatus = WebUIStatus.UNKNOWN
    current_instance: Optional[InstanceID] = None
    creation_time: Optional[float] = None


def save_state(state: WebUIState) -> None:
    with open("state.json", "w+") as f:
        f.write(state.to_json())


def load_state(filename="state.json") -> WebUIState:
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return WebUIState.from_json(f.read())
    else:
        return WebUIState()


def get_ssh_private_key_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".ssh", "id_rsa")

def get_ssh_public_key_path() -> str:
    return get_ssh_private_key_path() + ".pub"

def get_ssh_public_key() -> str:
    with open(get_ssh_public_key_path(), "r") as f:
        return f.read().strip()

def build_connect_kwargs() -> Dict[str, str]:
    return {"key_filename": get_ssh_private_key_path()}


class WebUIError(Exception):
    pass


MODEL_SCOPE_URLS = [
    "https://huggingface.co/damo-vilab/modelscope-damo-text-to-video-synthesis/resolve/main/VQGAN_autoencoder.pth",
    "https://huggingface.co/damo-vilab/modelscope-damo-text-to-video-synthesis/resolve/main/configuration.json",
    "https://huggingface.co/damo-vilab/modelscope-damo-text-to-video-synthesis/resolve/main/open_clip_pytorch_model.bin",
    "https://huggingface.co/damo-vilab/modelscope-damo-text-to-video-synthesis/resolve/main/text2video_pytorch_model.pth",
]


class WebUI:
    conn: fabric.Connection

    tmux: Tmux
    session: TmuxSession

    TMUX_SESSION_NAME = "stable-diffusion"
    TMUX_WEBUI_WINDOW_INDEX = 0
    WEBUI_PORT = 7860
    WEBUI_PROCESS_NAME = "python3 launch.py"
    WEBUI_INSTANCE_NAME = "stable-diffusion-webui"

    MODELSCOPE_MODEL_PATH = (
        "/home/ubuntu/stable-diffusion-webui/models/text2video/modelscope"
    )

    def __init__(self, conn: fabric.Connection):
        self.conn = conn
        self.host = RemoteHost(conn)
        self.tmux = Tmux(conn)
        self.session = self.tmux.find_or_create_sesssion(self.TMUX_SESSION_NAME)
        self.session.select_window(self.TMUX_WEBUI_WINDOW_INDEX)

    def forward_port(self):
        return self.conn.forward_local(self.WEBUI_PORT)

    def open_terminal(self):
        self.session.open_terminal()

    def install_webui(self):
        if self.is_webui_installed():
            raise WebUIError("WebUI is already installed")
        self.session.run_command_in_window(0, WEBUI_INSTALL_COMMAND)

    def install_text2video_extension(self):
        self.conn.run(
            "git clone https://github.com/kabachuha/sd-webui-text2video.git /home/ubuntu/stable-diffusion-webui/extensions/sd-webui-text2video"
        )
        self.conn.run(
            "/home/ubuntu/stable-diffusion-webui/venv/bin/pip install imageio_ffmpeg av moviepy numexpr"
        )
        self.conn.run(f"mkdir -p {self.MODELSCOPE_MODEL_PATH}")
        for url in MODEL_SCOPE_URLS:
            self.conn.run(f"cd {self.MODELSCOPE_MODEL_PATH} && wget -nc --progress=dot:giga {url}")

    def is_text2video_extension_installed(self) -> bool:
        return self.host.directory_exists(
            "/home/ubuntu/stable-diffusion-webui/extensions/sd-webui-text2video/.git"
        ) and self.host.directory_exists(self.MODELSCOPE_MODEL_PATH)

    def is_webui_installed(self) -> bool:
        """Returns True if WebUI has been cloned into the expected directory."""
        return self.host.directory_exists(os.path.join(WEBUI_DIRECTORY, ".git"))

    def is_webui_accessible(self) -> bool:
        """Returns True if WebUI is serving on its expected port."""
        return self.host.localhost_port_serving_http(self.WEBUI_PORT)

    def is_webui_running(self) -> bool:
        """Returns True if the main WebUI process is currently running."""
        return self.host.is_process_running(self.WEBUI_PROCESS_NAME)

    def run(self):
        """Starts the WebUI in the first tmux window."""
        self.session.run_command_in_window(0, WEBUI_SCRIPT)

    def kill(self):
        """Terminates any running WebUI"""
        self.conn.run("pkill -f launch.py", warn=True, hide=True)


class StateMachine:
    lapi: LambdaAPI = LambdaAPI()
    _webui: Optional[WebUI] = None
    instance_name: str = "stable-diffusion-webui"
    running: bool = False
    new_instance_poll_interval_seconds: int = 5
    installing_poll_interval_seconds: int = 5
    state: WebUIState
    ssh_username: str = "ubuntu"
    terminal_opened: bool = False

    def __init__(self, state: Optional[WebUIState] = None):
        if state is None:
            state = load_state()
        self.state = state

    @property
    def webui(self) -> WebUI:
        if not self.state.current_instance:
            raise WebUIError("No instance available yet!")
        if self._webui is None:
            details = self.lapi.get_instance_details(self.state.current_instance)
            connection = fabric.Connection(
                details.ip,
                user=self.ssh_username,
                connect_kwargs=build_connect_kwargs(),
            )
            self._webui = WebUI(connection)
        return self._webui

    def reset_state(self):
        self.state = WebUIState()
        save_state(self.state)

    def _transition_status(self, new_status: WebUIStatus):
        self.info(f"Transitioned from {self.state.status} to {new_status}.")
        self.state.status = new_status
        save_state(self.state)

    def run(self):
        if self.running:
            raise WebUIError("StateMachine is already running.")

        self.running = True
        while self.running:
            if self.state.status == WebUIStatus.UNKNOWN:
                self._status_unknown()
            elif self.state.status == WebUIStatus.CREATING_INSTANCE:
                self._status_creating_instance()
            elif self.state.status == WebUIStatus.INSTALLING:
                self._status_installing()
            elif self.state.status == WebUIStatus.STARTING:
                self._status_starting()
            elif self.state.status == WebUIStatus.RUNNING:
                self._status_running()
            elif self.state.status == WebUIStatus.TERMINATING:
                self._status_terminating()
            else:
                break

    def _status_unknown(self):
        instances = self.lapi.get_instances()
        instance_exists = any(
            instance.status == STATUS_ACTIVE and instance.name == self.instance_name
            for instance in instances
        )
        if instance_exists:
            raise WebUIError("Instance exists and is already running.")

        chosen_offer = prompt_user_for_instance_type(self.lapi)

        ssh_keys = self.lapi.get_ssh_keys()
        if not ssh_keys:
            raise WebUIError(
                "No SSH keys found. Please create an SSH key and try again."
            )

        pub_key = get_ssh_public_key()
        local_ssh_keys = [key for key in ssh_keys if key.public_key == pub_key]

        if not local_ssh_keys:
            raise WebUIError(f"Local SSH key {pub_key} doesn't match any LambdaLabs keys.")

        region_name = chosen_offer.regions_with_capacity_available[0].name
        self.info(
            f"Launching LambdaLabs instance named {self.instance_name} of type {chosen_offer.instance_type.name} in {region_name}"
        )
        instance_id = self.lapi.launch_instance(
            name=self.instance_name,
            instance_type_name=chosen_offer.instance_type.name,
            region_name=region_name,
            ssh_keys=local_ssh_keys,
        )
        self.info(f"Launched LambdaLabs instance with id {instance_id}")
        self.state.current_instance = instance_id
        self._transition_status(WebUIStatus.CREATING_INSTANCE)

    def _status_creating_instance(self):
        assert self.state.current_instance
        while True:
            details = self.lapi.get_instance_details(self.state.current_instance)
            if details.is_active:
                self.info(f"Instance {self.state.current_instance} is active!")
                self._transition_status(WebUIStatus.INSTALLING)
                time.sleep(5)
                return
            elif details.is_terminated:
                self.info(
                    f"Instance {self.state.current_instance} is terminated, restarting from scratch."
                )
                self.reset_state()
                return
            else:
                self.info(
                    f"Instance {self.state.current_instance} is {details.status} and not active yet, checking again in {self.new_instance_poll_interval_seconds} seconds..."
                )
                time.sleep(self.new_instance_poll_interval_seconds)

    def _status_installing(self):
        self.webui.open_terminal()
        self.terminal_opened = True
        if not self.webui.is_webui_installed():
            self.info("Installing WebUI.")
            self.webui.install_webui()

        if not self.webui.is_webui_accessible():
            while True:
                self.info("Waiting for WebUI to be accessible...")
                is_installed = self.webui.is_webui_installed()
                is_running = self.webui.is_webui_running()
                is_accessible = self.webui.is_webui_accessible()
                self.info(
                    f"Installed: {is_installed} Running: {is_running} Accessible: {is_accessible}"
                )
                if is_accessible:
                    break
                time.sleep(self.installing_poll_interval_seconds)

        if not self.webui.is_text2video_extension_installed():
            self.webui.install_text2video_extension()

        self._transition_status(WebUIStatus.STARTING)

    def _status_starting(self):
        if not self.terminal_opened:
            self.webui.open_terminal()
            self.terminal_opened = True
        self.webui.kill()
        time.sleep(5)
        self.webui.run()
        time.sleep(5)
        self._transition_status(WebUIStatus.RUNNING)

    def _status_running(self):
        if not self.terminal_opened:
            self.webui.open_terminal()
            self.terminal_opened = True
        with self.webui.forward_port():
            try:
                self.info("Ready! Open the WebUI at http://localhost:7860/")
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                response = input("Do you want to terminate the instance? y/n:")
                if response.strip().lower()[0] == "y":
                    self.lapi.terminate_instances([self.state.current_instance])
                    self._transition_status(WebUIStatus.TERMINATING)
                    return
                else:
                    print("Not terminating")
                    sys.exit(0)

    def _status_terminating(self):
        while True:
            details = self.lapi.get_instance_details(self.state.current_instance)
            if details.is_active:
                print("Still active...")
                time.sleep(5)
            if details.is_terminated:
                print("Terminated")
                self.reset_state()
                sys.exit(0)

    def info(self, text) -> None:
        print(text)
