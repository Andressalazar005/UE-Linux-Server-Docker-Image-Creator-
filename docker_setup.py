import os
import subprocess
import webbrowser
import json
import sys
import shutil
from file_selector import select_server_build_directory, select_output_directory

def selection_hint():
    return "Docker Setup: creates a docker image based off of the linux dedicated server to test locally in a Ubuntu VM using docker"
   
def log_message(message):
    print(f"[INFO] {message}")

def check_docker_installed():
    try:
        subprocess.run(["docker", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError:
        return False

def handle_docker_installation():
    log_message("Checking if Docker is installed.")
    if not check_docker_installed():
        log_message("Docker is not installed. Launching Docker download page...")
        webbrowser.open("https://www.docker.com/products/docker-desktop")

def create_dockerfile(output_dir, server_build_dir):
    # Validate directories
    if not os.path.exists(server_build_dir):
        log_message("Invalid server build directory. Running file selection.")
        server_build_dir = select_server_build_directory()

    if not os.path.exists(output_dir):
        log_message("Invalid output directory. Running file selection.")
        output_dir = select_output_directory()

    # Copy ProjectStaminaServer.sh to the output directory if needed
    # Assumes server_build_dir contains the script file
    script_source_path = os.path.join(server_build_dir, "ProjectStaminaServer.sh")
    if not os.path.exists(script_source_path):
        raise FileNotFoundError(f"Expected script not found at {script_source_path}")

    # Copy script to Docker build context if it doesn't exist there
    output_script_path = os.path.join(output_dir, "docker", "ProjectStaminaServer.sh")
    os.makedirs(os.path.dirname(output_script_path), exist_ok=True)
    if not os.path.exists(output_script_path):
        log_message("Copying ProjectStaminaServer.sh to Docker context.")
        shutil.copy(script_source_path, output_script_path)

    # Create Dockerfile content
    # Create Dockerfile content
    dockerfile_content = f'''
    FROM ubuntu:22.04

    RUN apt-get update && \
        apt-get install -y sudo net-tools iproute2 iptables curl unzip libstdc++6 && \
        useradd -rm -d /home/ubuntu -s /bin/bash -g root -G sudo -u 1000 m && \
        echo "m ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

    WORKDIR /game
    COPY . /game
    RUN chmod +x /game/ProjectStaminaServer.sh
    USER m
    ENTRYPOINT ["/bin/bash", "-c", "/game/ProjectStaminaServer.sh -log -PORT=7777"]
    '''


    docker_path = os.path.join(output_dir, "docker")
    dockerfile_path = os.path.join(docker_path, "Dockerfile")

    with open(dockerfile_path, 'w') as dockerfile:
        dockerfile.write(dockerfile_content.strip())

    log_message(f"Dockerfile created at: {dockerfile_path}")
    return dockerfile_path


def build_docker_image(image_name, build_dir):
    log_message(f"Building Docker image: {image_name}")
    try:
        subprocess.run(["docker", "build", "-t", image_name, build_dir], check=True)
        log_message(f"Docker image '{image_name}' built successfully.")
    except subprocess.CalledProcessError as e:
        log_message(f"Error building Docker image: {e}")


def create_docker_run_script(output_dir, image_name, container_name, server_build_dir):
    # Validate the server build directory
    if not os.path.exists(server_build_dir):
        log_message("Invalid server build directory. Running file selection.")
        server_build_dir = select_server_build_directory()

    # Validate the output directory
    if not os.path.exists(output_dir):
        log_message("Invalid output directory. Running file selection.")
        output_dir = select_output_directory()

    # Ensure all bat scripts are placed inside ServerTools_bin directory
    tools_bin_dir = os.path.join(output_dir, "ServerTools_bin")
    os.makedirs(tools_bin_dir, exist_ok=True)

    # Content for Docker run script
    docker_run_content = f'''
@echo off
Setlocal EnableDelayedExpansion

REM Check if the container exists
docker ps -a --filter "name={container_name}" --format "{{{{.Names}}}}" | findstr /I "{container_name}" >nul
if %ERRORLEVEL%==0 (
    set "container_exists=1"
) else (
    set "container_exists=0"
)

REM Check if the container is running
docker inspect -f "{{{{.State.Running}}}}" {container_name} 2>nul | findstr "true" >nul
if %ERRORLEVEL%==0 (
    set "container_running=1"
) else (
    set "container_running=0"
)

echo.
echo Container '{container_name}' status:
if "!container_exists!"=="0" (
    echo - Does not exist.
) else if "!container_running!"=="1" (
    echo - Running.
) else (
    echo - Exists but not running.
)
echo.

REM Collect user inputs upfront

if "!container_exists!"=="0" (
    set /P "create_choice=Container does not exist. Do you want to create and start a new container? (y/n): "
    if /I "!create_choice!"=="y" (
        set "action_sequence=create_new"
    ) else (
        echo Exiting script.
        goto end
    )
) else if "!container_running!"=="1" (
    set /P "action_choice=Container is running. Do you want to [S]top it, [A]ttach to it, or [D]elete it? (s/a/d): "
    if /I "!action_choice!"=="s" (
        set "action_sequence=stop"
        set /P "delete_after_stop=Do you want to delete the container after stopping it? (y/n): "
        if /I "!delete_after_stop!"=="y" (
            set "action_sequence=!action_sequence! delete"
            set /P "create_after_delete=Do you want to create and start a new container? (y/n): "
            if /I "!create_after_delete!"=="y" (
                set "action_sequence=!action_sequence! create_new"
            )
        )
    ) else if /I "!action_choice!"=="a" (
        set "action_sequence=attach"
    ) else if /I "!action_choice!"=="d" (
        set "action_sequence=stop delete"
        set /P "create_after_delete=Do you want to create and start a new container? (y/n): "
        if /I "!create_after_delete!"=="y" (
            set "action_sequence=!action_sequence! create_new"
        )
    ) else (
        echo Invalid choice. Exiting.
        goto end
    )
) else (
    REM Container exists but is not running
    set /P "action_choice=Container exists but is not running. Do you want to [S]tart it, [D]elete it, or [E]xit? (s/d/e): "
    if /I "!action_choice!"=="s" (
        set "action_sequence=start attach"
    ) else if /I "!action_choice!"=="d" (
        set "action_sequence=delete"
        set /P "create_after_delete=Do you want to create and start a new container? (y/n): "
        if /I "!create_after_delete!"=="y" (
            set "action_sequence=!action_sequence! create_new"
        )
    ) else if /I "!action_choice!"=="e" (
        echo Exiting script.
        goto end
    ) else (
        echo Invalid choice. Exiting.
        goto end
    )
)

echo.

REM Execute actions based on user inputs

echo Executing actions...
echo.

set "attach_needed=0"

for %%A in (!action_sequence!) do (
    if "%%A"=="stop" (
        echo Stopping the container...
        docker stop {container_name}
    ) else if "%%A"=="delete" (
        echo Deleting the container...
        docker rm {container_name}
    ) else if "%%A"=="create_new" (
        echo Creating and starting a new container '{container_name}'...
        docker run --name {container_name} -p 7777:7777 --mount type=bind,source="{server_build_dir}",target=/game -d {image_name} /bin/bash -c "apt-get update && apt-get install -y sudo && (id -u m || useradd -rm -d /home/ubuntu -s /bin/bash -g root -G sudo -u 1000 m) && sudo -u m /game/ProjectStaminaServer.sh -log -PORT=7777"
        set "attach_needed=1"
    ) else if "%%A"=="start" (
        echo Starting the container...
        docker start {container_name}
    ) else if "%%A"=="attach" (
        set "attach_needed=1"
    )
)

if "!attach_needed!"=="1" (
    echo Attaching to the container...
    docker attach {container_name}
)

echo.
echo All actions completed. Press any key to exit.
pause >nul

:end
'''

    run_script_path = os.path.join(tools_bin_dir, "RunLinuxServer.bat")

    # Write Docker run script
    with open(run_script_path, 'w') as run_script:
        run_script.write(docker_run_content.strip())

    log_message(f"Docker run script created at: {run_script_path}")

def Run_Docker_Setup(output_dir=None, server_build_dir=None, docker_image_name=None):
    log_message("Starting Docker setup process.")
    handle_docker_installation()

    if not docker_image_name:
        log_message("Prompting for Docker image name.")
        docker_image_name = input("\nEnter the Docker image name and tag or press enter if default is okay (default: stamina-dedicated-server-env): ").strip().lower() or "stamina-dedicated-server-env"

    if not output_dir:
        output_dir = select_output_directory()
    if not server_build_dir:
        server_build_dir = select_server_build_directory()

    # Add a container name, either default or prompted
    container_name = "stamina_dedicated_container"  # Default container name
    log_message(f"Using container name: {container_name}")

    dockerfile_path = create_dockerfile(output_dir, server_build_dir)
    build_dir = os.path.dirname(dockerfile_path)
    build_docker_image(docker_image_name, build_dir)
    create_docker_run_script(output_dir, docker_image_name, container_name, server_build_dir)  # Add container_name here
    log_message("Docker setup process completed.")


def get_script_inputs():
    return {
        "inputs": [
            {
                "type": "text",
                "label": "Docker Image Name",
                "description": "Enter the Docker image name and tag (default: stamina-dedicated-server-env).",
                "default": "stamina-dedicated-server-env"
            }
        ]
    }

if __name__ == "__main__":
    # Read input data from stdin
    input_data = sys.stdin.read().strip()
    if input_data:
        inputs = json.loads(input_data)
        # Extract the docker_image_name from inputs
        docker_image_name = inputs[0] if len(inputs) > 0 else None
    else:
        docker_image_name = None

    Run_Docker_Setup(docker_image_name=docker_image_name)
