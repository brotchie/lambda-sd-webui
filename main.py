import re
import sys
import os
import time
import pprint

from typing import Any, Dict, List, Optional, Tuple

from lambda_labs import LambdaAPI, InstanceTypeName, RegionName, InstanceID


# 1. Check if any VMs already running,
# 2. It not, start a new VM and store the starting time.
# 3. Wait for VM to be available,
# 4. SSH into VM and install:
#   a) Automatic 1111,
#   b) text2video extension,
#   c) Modelscope,
#   d) Zeroscape a and b,
# 5. SSH into VM and create a tmux session running the webui and ssh with port forwarding.
# 6. When existing this python executable, ask if the user wants to terminate the VM.
#
# While rnuning, keep calculating the cost by multipling current time - start time by cents per hour.

# Install command: bash <(wget -qO- https://raw.githubusercontent.com/AUTOMATIC1111/stable-diffusion-webui/master/webui.sh)
# Extensions path: /home/ubuntu/stable-diffusion-webui/extensions
# Model scope Hugging Face: https://huggingface.co/damo-vilab/modelscope-damo-text-to-video-synthesis/tree/main
# model scope path: /home/ubuntu/stable-diffusion-webui/models/ModelScope/t2v/.
# text2video extension: https://github.com/kabachuha/sd-webui-text2video

# wget -i




def get_ssh_private_key_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".ssh", "id_rsa")


def build_connect_kwargs() -> Dict[str, str]:
    return {"key_filename": get_ssh_private_key_path()}


import fabric
import subprocess


def main():
    from webui import StateMachine
    state_machine = StateMachine()
    state_machine.run()
    return
#    api = LambdaAPI()
#    from instances import prompt_user_for_instance_type
#    print(prompt_user_for_instance_type(api))
#    return
    # instance_type, region = ask_user_for_instance(api)
    # ssh_keys = api.get_ssh_keys()
    # print(f"Launching {instance_type} in {region}...")
    # instance_id = api.launch_instance("stable-diffusion", instance_type, region, ssh_keys)
    instance_id = InstanceID("72cf481ab6ae422c89b3addf90436d1e")
    instance = api.get_instance_details(instance_id)
    assert instance.is_active
    api.terminate_instances([instance_id])

    return

    print(f"ssh ubuntu@{instance.ip}")

    c = fabric.Connection(
        instance.ip,
        user="ubuntu",
        connect_kwargs=build_connect_kwargs(),
    )
    with c.forward_local(7860):
        tmux = Tmux(c)
        host = RemoteHost(c)

        webui = StableDiffusionWebUI(c)

        if webui.is_installed():
            print("WebUI already installed")
        else:
            print("Installing webui")
            webui.install()
            while True:
                if webui.is_accessible():
                    break
                time.sleep(5)

        # if webui.is_running():
        #    print("Is running")
        #    webui.kill()
        # webui.run()

        while True:
            print(webui.is_running(), webui.is_installed())
            time.sleep(4)

    # print(webui.is_webui_running())
    # print(webui.is_webui_accessible())

    # if webui.is_webui_running():
    #    webui.kill()

    # print(host.directory_exists("/home/ubuntu"))
    # print(host.directory_exists("/home/ubuntu2"))
    # session.open_terminal()
    # session.select_window(0)
    # session.run_command_in_window(0, "git")
    # result = c.run("test -d /home/ubuntu")
    # print(result.exited)
    # result = c.run("test -d /home/ubuntu2", warn=True)
    # print(result.exited)
    # print(tmux.list_sessions())
    # print(tmux.new_session("stable-diffusion"))
    # print(tmux.list_sessions())
    # c.run("tmux attach -r -t 0")
    # c.run("ls -lha")

    # while True:
    #    pprint.pprint(api.get_instance_details(instance_id))
    #    time.sleep(5)
    # print(api.get_instances())
    # pprint.pprint(api.get_instances())
    # print("\n".join(MODEL_SCOPE_FILES))
    # api.terminate_all_instances()
    # print(api.get_instances())
    # api.terminate_all_instances()


if __name__ == "__main__":
    main()
