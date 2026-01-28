import subprocess
import os
import time

# --- Configuration ---
# The script now looks for the subdirectory relative to its own location.
INVENTORY_PATH = os.path.join("server_power_status_management", "inventory.ini")
PLAYBOOK_PATH = os.path.join("server_power_status_management", "playbook.yaml")

# Map user input to server names
SERVER_MAP = {
    "1": "ubuntu-guest",
    "2": "apache-vm-1",
    "3": "apache-vm-2",
}

# --- Ansible Functions ---

def run_ansible_playbook(vm_name: str, state: str) -> bool:
    """Runs the Ansible playbook to manage a VM's power state."""
    print(f"\n-> Running Ansible for '{vm_name}' to power {state}...")
    
    command = [
        "ansible-playbook", "-i", INVENTORY_PATH, PLAYBOOK_PATH,
        "-e", f"target_server={vm_name} power_state={state}", "-l", "kvm_host"
    ]

    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        print(f"-> Success: '{vm_name}' action '{state}' completed.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"-> Error: Ansible failed for '{vm_name}' (state: {state}).")
        print(e.stderr)
        return False

def power_on_server(vm_name: str) -> bool:
    return run_ansible_playbook(vm_name, 'on')

def power_off_server(vm_name: str) -> bool:
    return run_ansible_playbook(vm_name, 'off')

def restart_server(vm_name: str) -> bool:
    success_off = run_ansible_playbook(vm_name, 'off')
    time.sleep(20)
    success_on = run_ansible_playbook(vm_name, 'on')
    return success_off and success_on