import subprocess
import sys
import os
import argparse
import re

PUBLIC_IP = "203.80.21.39" 

PUBLIC_INTERFACE = "eno3"

class NatController:
    """
    A controller to manage iptables rules for forwarding HTTP traffic.
    It accepts a target IP as a command-line argument, allowing it to be
    controlled by an external system like Ansible.
    """
    def __init__(self, public_ip, public_interface):
        """
        Initializes the controller with your network configuration.
        """
        if "YOUR_PUBLIC_IP" in public_ip:
            print("ERROR: Please update the PUBLIC_IP variable in the script before running.")
            sys.exit(1)
            
        self.public_ip = public_ip
        self.public_interface = public_interface

    def _run_command(self, command, check=True, capture_output=True):
        """
        Helper function to execute shell commands. It assumes the script is run with sudo.
        """
        try:
            print(f"[*] Executing: {' '.join(command)}")
            result = subprocess.run(command, check=check, capture_output=capture_output, text=True)
            if check:
                print("[+] Command executed successfully.")
            return result
        except subprocess.CalledProcessError as e:
            print(f"[!] Error executing command: {e}")
            print(f"[!] Stderr: {e.stderr}")
            return None
        except FileNotFoundError:
            print("[!] Error: 'iptables' command not found. Is it in your PATH?")
            return None
        
    def _find_prerouting_rule_num(self, port):
        """
        Finds the rule number for our specific DNAT rule in the PREROUTING chain.
        Returns the rule number (as a string) or None if not found.
        """
        print(f"[*] Searching for existing PREROUTING rule for port {port}...")
        command = ['iptables', '-t', 'nat', '-L', 'PREROUTING', '-n', '--line-numbers']
        result = self._run_command(command, check=True)
        if not result:
            return None
        
        rule_regex = re.compile(
            r"^\s*(\d+)\s+.*" + re.escape(self.public_ip) + r".*dpt:" + str(port)
        )
        
        for line in result.stdout.splitlines():
            match = rule_regex.match(line)
            if match:
                rule_num = match.group(1)
                # We found the first rule that matches. Return its number.
                print(f"[+] Found existing rule at line number: {rule_num}")
                return rule_num
        
        print(f"[-] No existing rule found for IP {self.public_ip} and port {port}.")
        return None

    def enable_ip_forwarding(self):
        """
        Enables IP forwarding in the kernel, allowing the server to act as a router.
        """
        print("\n[*] Enabling Kernel IP Forwarding...")
        self._run_command(['sysctl', '-w', 'net.ipv4.ip_forward=1'])

    def setup_forwarding_rules(self, target_ip, port=80):
        """
        Intelligently applies DNAT and MASQUERADE rules.
        - Replaces/Adds the DNAT rule without flushing the PREROUTING chain.
        - Checks for the MASQUERADE rule before adding it.
        """
        print(f"\n[*] Applying NAT forwarding rules for port {port}...")
        
        # --- 1. Destination NAT (DNAT) Rule ---
        # This rule redirects incoming traffic to the target server IP.
        # We build the rule specification first.
        dnat_rule_spec = [
            '-i', self.public_interface,
            '-p', 'tcp',
            '--dport', str(port),
            '-d', self.public_ip,
            '-j', 'DNAT',
            '--to-destination', target_ip
        ]
        
        rule_num = self._find_prerouting_rule_num(port)
        
        if rule_num:
            # If the rule exists, we REPLACE it.
            print(f"[*] Replacing existing DNAT rule to forward traffic to {target_ip}.")
            command = ['iptables', '-t', 'nat', '-R', 'PREROUTING', rule_num] + dnat_rule_spec
        else:
            # If the rule does not exist, we APPEND it.
            print(f"[*] Adding new DNAT rule to forward traffic to {target_ip}.")
            command = ['iptables', '-t', 'nat', '-A', 'PREROUTING'] + dnat_rule_spec

        self._run_command(command)

        # --- 2. Source NAT (SNAT / Masquerading) Rule ---
        # This rule handles the return traffic. We check if it exists before adding it.
        print("\n[*] Checking for MASQUERADE rule...")
        masquerade_rule_spec = [
            '-o', self.public_interface,
            '-j', 'MASQUERADE'
        ]
        
        # The '-C' or '--check' command returns 0 if the rule exists, 1 otherwise.
        check_command = ['iptables', '-t', 'nat', '-C', 'POSTROUTING'] + masquerade_rule_spec
        result = self._run_command(check_command, check=False, capture_output=False)
        
        if result.returncode != 0:
            print("[+] MASQUERADE rule not found. Adding it now.")
            add_command = ['iptables', '-t', 'nat', '-A', 'POSTROUTING'] + masquerade_rule_spec
            self._run_command(add_command)
        else:
            print("[+] MASQUERADE rule already exists. No action needed.")

if __name__ == '__main__':
    # --- Argument Parsing ---
    # This is the new section that allows the script to be controlled externally.
    parser = argparse.ArgumentParser(description="Configure NAT forwarding to a specific backend server.")
    parser.add_argument("target_ip", help="The private IP address of the virtual server to forward traffic to.")
    args = parser.parse_args()

    # Ensure the script is run with root privileges
    if os.geteuid() != 0:
        print("[!] This script requires root privileges (use 'sudo') to manage iptables.")
        sys.exit(1)

    # Create an instance of the controller
    controller = NatController(PUBLIC_IP, PUBLIC_INTERFACE)
    
    # --- Execution Flow ---
    controller.enable_ip_forwarding()
    controller.setup_forwarding_rules(target_ip=args.target_ip, port=80)
    
    print("\n[SUCCESS] NAT forwarding rules have been applied.")
    print(f"Traffic to {PUBLIC_IP}:80 will now be forwarded to {args.target_ip}.")