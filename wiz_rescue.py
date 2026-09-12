#!/usr/bin/env python3
"""
WiZ-Rescue: 1-Click Auto-Discovery & Cloud Activation Engine for Philips WiZ Lights
Author: Devansh (@Ydeva1999)
License: MIT

Fixes the widespread Philips WiZ Connected v2 Flutter app onboarding bug:
"type 'SendingEncryptedCredential' is not a subtype of type 'ConnectingToDevice' in type cast"
which causes the WiZ app to crash out of onboarding before binding the light to the user's
Home ID, leaving brand-new lights stuck in 'Devices offline' state with homeId = 0.
"""

import sys
import time
import json
import socket
import re
import subprocess
import platform
import argparse

# Ensure UTF-8 output on Windows consoles without crashing
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

WIZ_PORT = 38899
BROADCAST_IP = "255.255.255.255"

class Colors:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    @classmethod
    def disable(cls):
        cls.CYAN = cls.GREEN = cls.YELLOW = cls.RED = cls.BOLD = cls.DIM = cls.RESET = ""

if platform.system() == "Windows":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        Colors.disable()

def get_local_ip():
    """Detects primary local IPv4 address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Does not actually connect, but determines the default routing interface
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def get_arp_ips(subnet_prefix):
    """Scans local ARP cache for active device IPs on the same subnet."""
    ips = set()
    try:
        if platform.system() == "Windows":
            out = subprocess.check_output(["arp", "-a"], stderr=subprocess.DEVNULL).decode("ascii", errors="ignore")
        else:
            out = subprocess.check_output(["arp", "-n"], stderr=subprocess.DEVNULL).decode("ascii", errors="ignore")
        matches = re.findall(rf"({re.escape(subnet_prefix)}\.\d+)", out)
        for m in matches:
            ips.add(m)
    except Exception:
        pass
    return list(ips)

def send_udp_command(ip, payload_dict, sock=None):
    """Sends a JSON-RPC UDP packet to a WiZ device."""
    data = json.dumps(payload_dict).encode("utf-8")
    close_sock = False
    if sock is None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.0)
        close_sock = True
    try:
        sock.sendto(data, (ip, WIZ_PORT))
    finally:
        if close_sock:
            sock.close()

def discover_wiz_lights(timeout=3.0, target_ip=None):
    """Broadcasts getSystemConfig and collects responses from all WiZ lights."""
    devices = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(0.5)

    probe = json.dumps({"method": "getSystemConfig", "params": {}}).encode("utf-8")

    local_ip = get_local_ip()
    subnet_prefix = ".".join(local_ip.split(".")[:3])
    subnet_broadcast = f"{subnet_prefix}.255"

    print(f"{Colors.DIM}[*] Local IP: {local_ip} | Subnet: {subnet_prefix}.0/24{Colors.RESET}")
    print(f"{Colors.CYAN}[*] Scanning network for Philips WiZ lights (timeout: {timeout}s)...{Colors.RESET}")

    if target_ip:
        # Direct unicast probe
        try:
            sock.sendto(probe, (target_ip, WIZ_PORT))
        except Exception:
            pass
    else:
        # Broadcast probe
        for bcast in [BROADCAST_IP, subnet_broadcast]:
            try:
                sock.sendto(probe, (bcast, WIZ_PORT))
            except Exception:
                pass

        # Also unicast probe ARP entries (in case AP isolation or broadcast filtering is on)
        arp_ips = get_arp_ips(subnet_prefix)
        for a_ip in arp_ips:
            try:
                sock.sendto(probe, (a_ip, WIZ_PORT))
            except Exception:
                pass

    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            data, addr = sock.recvfrom(4096)
            resp = json.loads(data.decode("utf-8", errors="ignore"))
            if "result" in resp and "mac" in resp["result"]:
                res = resp["result"]
                ip = addr[0]
                devices[ip] = {
                    "ip": ip,
                    "mac": res.get("mac", "unknown"),
                    "homeId": res.get("homeId", 0),
                    "roomId": res.get("roomId", 0),
                    "fwVersion": res.get("fwVersion", "unknown"),
                    "moduleName": res.get("moduleName", "WiZ Device")
                }
        except socket.timeout:
            continue
        except Exception:
            pass

    sock.close()
    return list(devices.values())

def rescue_light(ip, home_id, room_id=0):
    """Injects homeId & roomId into an orphaned light and triggers a visual handshake."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)

    payloads = [
        {"method": "setSystemConfig", "params": {"homeId": home_id}}
    ]
    if room_id and room_id > 0:
        payloads.append({"method": "setSystemConfig", "params": {"homeId": home_id, "roomId": room_id}})
    
    # Visual acknowledgment blink: Warm White -> Daylight
    payloads.extend([
        {"method": "setPilot", "params": {"state": True, "temp": 2700, "dimming": 100}},
        {"method": "setPilot", "params": {"state": True, "temp": 6500, "dimming": 100}}
    ])

    for p in payloads:
        data = json.dumps(p).encode("utf-8")
        for _ in range(3):  # Blast 3x UDP packets for reliable delivery
            try:
                sock.sendto(data, (ip, WIZ_PORT))
                time.sleep(0.05)
            except Exception:
                pass
        time.sleep(0.15)

    sock.close()

def main():
    parser = argparse.ArgumentParser(description="WiZ-Rescue: Philips WiZ 1-Click Auto-Fix & Cloud Activation Engine")
    parser.add_argument("--ip", help="Direct target IP of the orphaned light (optional, skips scan)", type=str)
    parser.add_argument("--home-id", help="Override Home ID to inject (optional)", type=int)
    parser.add_argument("--room-id", help="Override Room ID to inject (optional)", type=int)
    parser.add_argument("--scan-only", help="Only scan and display network WiZ lights without modifying", action="store_true")
    args = parser.parse_args()

    print(f"{Colors.CYAN}{'='*64}{Colors.RESET}")
    print(f"{Colors.YELLOW}{Colors.BOLD}     ⚡ Philips Smart Light (WiZ) 1-Click Auto-Fix Engine{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*64}{Colors.RESET}\n")

    devices = discover_wiz_lights(timeout=3.0, target_ip=args.ip)

    print(f"\n{Colors.GREEN}[*] Discovery Complete. Found {len(devices)} WiZ device(s):{Colors.RESET}")
    if devices:
        print(f"{'IP Address':<18} {'MAC Address':<18} {'Home ID':<12} {'Room ID':<10} {'Model'}")
        print("-" * 72)
        for d in devices:
            status = f"{Colors.GREEN}ONLINE{Colors.RESET}" if d['homeId'] > 0 else f"{Colors.RED}ORPHANED{Colors.RESET}"
            print(f"{d['ip']:<18} {d['mac']:<18} {str(d['homeId']):<12} {str(d['roomId']):<10} {d['moduleName']} [{status}]")
        print()

    if args.scan_only:
        print(f"{Colors.YELLOW}[*] Scan-only mode complete. Exiting.{Colors.RESET}")
        return

    # Determine credentials
    healthy_lights = [d for d in devices if d['homeId'] > 0]
    orphaned_lights = [d for d in devices if d['homeId'] == 0]

    target_home_id = args.home_id
    target_room_id = args.room_id or 0

    if not target_home_id:
        if healthy_lights:
            target_home_id = healthy_lights[0]['homeId']
            target_room_id = healthy_lights[0]['roomId'] if not target_room_id else target_room_id
            print(f"{Colors.GREEN}[+] Auto-Cloned credentials from healthy light ({healthy_lights[0]['ip']}):{Colors.RESET}")
            print(f"    -> Target Home ID : {Colors.YELLOW}{target_home_id}{Colors.RESET}")
            if target_room_id:
                print(f"    -> Target Room ID : {Colors.YELLOW}{target_room_id}{Colors.RESET}")
        else:
            print(f"{Colors.YELLOW}[!] No active WiZ lights detected to auto-clone from.{Colors.RESET}")
            print(f"{Colors.DIM}    (To find your Home ID: Open WiZ App > Settings > Home Settings){Colors.RESET}")
            try:
                user_input = input(f"{Colors.BOLD}Enter your numeric WiZ Home ID: {Colors.RESET}").strip()
                if user_input.isdigit():
                    target_home_id = int(user_input)
                else:
                    print(f"{Colors.RED}[X] Invalid Home ID provided. Exiting.{Colors.RESET}")
                    return
            except (KeyboardInterrupt, EOFError):
                print(f"\n{Colors.RED}[X] Operation cancelled.{Colors.RESET}")
                return

    if args.ip:
        orphaned_lights = [{"ip": args.ip, "mac": "Direct-Target"}]

    if not orphaned_lights:
        print(f"{Colors.GREEN}[OK] All detected WiZ lights already have valid Home IDs!{Colors.RESET}")
        print(f"{Colors.DIM}     If you just plugged in a new light, ensure it is connected to your Wi-Fi router first.{Colors.RESET}")
    else:
        print(f"{Colors.RED}[!] Rescuing {len(orphaned_lights)} orphaned light(s)...{Colors.RESET}")
        for orphan in orphaned_lights:
            ip = orphan['ip']
            mac = orphan.get('mac', 'unknown')
            print(f"    -> Injected Home ID {target_home_id} into {ip} (MAC: {mac})...", end="", flush=True)
            rescue_light(ip, target_home_id, target_room_id)
            print(f" {Colors.GREEN}[DONE]{Colors.RESET}")

    print(f"\n{Colors.CYAN}{'='*64}{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD} All done! Open your WiZ Connected app to verify your lights.{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*64}{Colors.RESET}")

if __name__ == "__main__":
    main()
