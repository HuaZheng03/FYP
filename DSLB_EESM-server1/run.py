import time
import os
import sys

# --- Import from local files ---
try:
    # We import directly from the local files
    from dynamic_load_balancing.DWRS import update_server_weights, select_target_server
    from dynamic_load_balancing.nat_controller import NatController, PUBLIC_IP, PUBLIC_INTERFACE
except ImportError as e:
    print(f"Error: {e}.")
    print("Please make sure 'DWRS.py' and 'nat_controller.py' are in the same directory.")
    sys.exit(1)

# --- SCRIPT CONFIGURATION ---
# A 2-second loop is fast, effective, and won't spam Prometheus
LOOP_INTERVAL = 1

def clear_screen():
    """Clears the console screen for cleaner output."""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_telemetry_tables(servers):
    """
    Displays the collected server telemetry in clean, formatted tables.
    """
    print("\n[Current Server Status]")

    # --- CPU Table ---
    print("\n--- CPU Telemetry ---")
    print(f"{'Server IP':<18} | {'Usage (%)':<10} | {'Total Cores':<12}")
    print("-" * 44)
    for server in servers:
        ip = server['ip']; metrics = server['metrics']
        print(f"{ip:<18} | {metrics['cpu']:<10.2f} | {metrics['total_cpu_cores']:<12}")

    # --- Memory Table ---
    print("\n--- Memory Telemetry ---")
    print(f"{'Server IP':<18} | {'Usage (%)':<10} | {'Total Memory (GB)':<18}")
    print("-" * 50)
    for server in servers:
        ip = server['ip']
        metrics = server['metrics']
        print(f"{ip:<18} | {metrics['mem']:<10.2f} | {metrics['total_mem_gb']:<18.1f}")
    
    # --- Load Table ---
    print("\n--- DWRS Load & Weight ---")
    print(f"{'Server IP':<18} | {'Combined Load (%)':<18} | {'Dynamic Weight (1-100)':<22}")
    print("-" * 62)
    for server in servers:
        ip = server['ip']
        load = server['comprehensive_load']
        weight = server['dynamic_weight']
        print(f"{ip:<18} | {load:<18.2f} | {weight:<22}")


def main_loop():
    """
    The main execution loop (Direct Control Mode).
    Monitors servers and applies NAT rules directly.
    """
    print("--- Dynamic Load Balancer (Direct Control Mode) ---")

    # This is critical: the script must be run as root
    if os.geteuid() != 0:
        print("\n[ERROR] This script must be run with 'sudo' to manage iptables.")
        sys.exit(1)
        
    print("[*] Initializing NAT Controller...")
    try:
        # Create one instance of the controller
        nat = NatController(public_ip=PUBLIC_IP, public_interface=PUBLIC_INTERFACE)
        nat.enable_ip_forwarding()
    except Exception as e:
        print(f"[!] Failed to initialize NatController: {e}")
        sys.exit(1)
        
    print("[+] NAT Controller is ready.")
    current_target_ip = None
    print(f"Starting loop (Interval: {LOOP_INTERVAL}s). Press Ctrl+C to stop.")
    time.sleep(3)

    while True:
        try:
            clear_screen()
            print(f"--- Running New Check at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
            
            # 1. MONITOR
            active_servers = update_server_weights()
            if not active_servers:
                print("No active servers detected. Waiting...")
                time.sleep(LOOP_INTERVAL)
                continue
            if len(active_servers) == 1 and current_target_ip == active_servers[0]['ip']:
                print("Only one active server detected. Skipping DWRS calculation.")
                print(f"\n--- Waiting for 10 seconds ---")
                time.sleep(10)
                continue
            # 2. DISPLAY
            print_telemetry_tables(active_servers)

            # 3. DECIDE
            print("\n\n[DECIDE] Running DWRS algorithm to select target server...")
            selected_server = select_target_server(active_servers)
            if not selected_server:
                print("Could not select a target server. Waiting...")
                time.sleep(LOOP_INTERVAL)
                continue
            
            new_target_ip = selected_server['ip']
            print(f"✅ DWRS algorithm selected server: {new_target_ip}")

            # 4. ACT (This is now < 1 second and reliable)
            if new_target_ip == current_target_ip:
                print(f"\n[ACT] Target server is unchanged ({current_target_ip}).")
            else:
                print(f"🔄 Target has changed from '{current_target_ip}' to '{new_target_ip}'.")
                try:
                    # This is a direct Python call, NOT Ansible
                    nat.setup_forwarding_rules(target_ip=new_target_ip, port=80)
                    print(f"✅ [SUCCESS] NAT rule updated to {new_target_ip}.")
                    current_target_ip = new_target_ip
                except Exception as e:
                    print(f"❌ [FAILURE] Failed to apply NAT rules: {e}")
            
            print(f"\n--- Waiting for {LOOP_INTERVAL} seconds ---")
            time.sleep(LOOP_INTERVAL)

        except KeyboardInterrupt:
            print("\n\nShutting down.")
            break
        except Exception as e:
            print(f"\nAn unexpected error occurred: {e}")
            time.sleep(LOOP_INTERVAL)

if __name__ == "__main__":
    main_loop()