import subprocess
import sys
import ipaddress

# --- Configuration ---
# These should match the names of your Ansible files.
INVENTORY_FILE = "inventory.ini"
PLAYBOOK_FILE = "update_nat_rules.yaml"

def is_valid_ip(ip_string):
    """Checks if the provided string is a valid IP address."""
    try:
        ipaddress.ip_address(ip_string)
        return True
    except ValueError:
        return False

def run_ansible_playbook(target_ip, nat_script_path):
    """
    Constructs and executes the ansible-playbook command to update the NAT rule.

    Args:
        target_ip (str): The private IP address of the server to forward traffic to.
        nat_script_path (str): The absolute path to the nat_controller.py script.
    
    Returns:
        bool: True if the command was successful, False otherwise.
    """
    playbook_dir = "dynamic_load_balancing"
    inventory_path = f"{playbook_dir}/{INVENTORY_FILE}"
    playbook_path = f"{playbook_dir}/{PLAYBOOK_FILE}"

    print(f"\n[*] Preparing to run Ansible playbook...")
    print(f"    - Target Server IP: {target_ip}")
    print(f"    - Inventory File:   {inventory_path}")
    print(f"    - Playbook File:    {playbook_path}")
    
    # This command now passes two variables to Ansible.
    command = [
        "ansible-playbook",
        "-i", inventory_path,
        playbook_path,
        "--extra-vars",
        f"target_ip={target_ip}",
        "--extra-vars",
        f"nat_script_path={nat_script_path}"
    ]
    
    try:
        print("\n[*] Executing command:", " ".join(command))
        print("-" * 40)
        
        process = subprocess.run(
            command, 
            check=True, 
            text=True
        )
        
        print("-" * 40)
        print("[SUCCESS] Ansible playbook completed successfully.")
        return True
        
    except FileNotFoundError:
        print("\n[ERROR] 'ansible-playbook' command not found.")
        print("        Please ensure Ansible is installed and in your system's PATH.")
        return False
    except subprocess.CalledProcessError as e:
        print("-" * 40)
        print(f"\n[ERROR] Ansible playbook failed with return code {e.returncode}.")
        return False
