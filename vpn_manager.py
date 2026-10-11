import asyncio
import base64
import csv
import io
import os
import subprocess
import urllib.request

VPNGATE_API = "https://www.vpngate.net/api/iphone/"
PARALLEL_TUNNELS = 10
TUNNEL_COOLDOWN = 120
ALL_DEAD_SLEEP = 600


class VpnTunnel:
    def __init__(self, index, ovpn_config_b64, exit_ip=None):
        self.index = index
        self.ns_name = f"vpnns{index}"
        self.tun_iface = "tun0"
        self.config_b64 = ovpn_config_b64
        self.exit_ip = exit_ip
        self.dead_until = 0
        self.ready = False
        self.tun_ip = None

    def _ovpn_path(self):
        return f"/tmp/vpngate_{self.index}.ovpn"

    def _write_config(self):
        raw = base64.b64decode(self.config_b64)
        with open(self._ovpn_path(), "wb") as f:
            f.write(raw)
        return self._ovpn_path()

    async def start(self):
        ovpn = self._ovpn_path()
        if not os.path.exists(ovpn):
            self._write_config()

        subprocess.run(["ip", "netns", "del", self.ns_name], stderr=subprocess.DEVNULL)
        subprocess.run(["ip", "netns", "add", self.ns_name], check=True)
        subprocess.run(["ip", "netns", "exec", self.ns_name,
                        "ip", "link", "set", "lo", "up"], check=True)

        # ホストの /etc/resolv.conf を netns 内にコピー（DNS解決用）
        subprocess.run(["mkdir", "-p", f"/etc/netns/{self.ns_name}"], check=False)
        try:
            with open("/etc/resolv.conf") as src:
                content = src.read()
            with open(f"/etc/netns/{self.ns_name}/resolv.conf", "w") as dst:
                dst.write("nameserver 8.8.8.8\nnameserver 1.1.1.1\n")
        except Exception:
            pass

        cmd = [
            "ip", "netns", "exec", self.ns_name,
            "openvpn",
            "--config", ovpn,
            "--dev", self.tun_iface,
            "--route-nopull",        # ルートは触らない。netns内のデフォルトGWを使う
            "--daemon",
            "--log", f"/tmp/openvpn_{self.index}.log",
            "--writepid", f"/tmp/openvpn_{self.index}.pid",
        ]
        subprocess.run(cmd, check=True)

        self.ready = await self._wait_for_tun()
        return self.ready

    async def _wait_for_tun(self, timeout=30):
        for _ in range(timeout * 2):
            try:
                r = subprocess.run(
                    ["ip", "netns", "exec", self.ns_name,
                     "ip", "-4", "-o", "addr", "show", self.tun_iface],
                    capture_output=True, text=True, timeout=2,
                )
                for line in r.stdout.splitlines():
                    parts = line.split()
                    for i, p in enumerate(parts):
                        if p == "inet" and i + 1 < len(parts):
                            self.tun_ip = parts[i + 1].split("/")[0]
                            self.exit_ip = self._parse_exit_ip()
                            return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
        return False

    def _parse_exit_ip(self):
        try:
            r = subprocess.run(
                ["ip", "netns", "exec", self.ns_name,
                 "curl", "-s", "--max-time", "8", "https://api.ipify.org"],
                capture_output=True, text=True, timeout=12,
            )
            return r.stdout.strip() or self.tun_ip
        except Exception:
            return self.tun_ip

    def is_alive(self):
        now = asyncio.get_event_loop().time()
        if now < self.dead_until:
            return False
        if not self.ready:
            return False
        pid_file = f"/tmp/openvpn_{self.index}.pid"
        if not os.path.exists(pid_file):
            return False
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return True
        except (OSError, ValueError):
            return False

    def mark_bad(self):
        self.dead_until = asyncio.get_event_loop().time() + TUNNEL_COOLDOWN

    async def stop(self):
        subprocess.run(["ip", "netns", "del", self.ns_name], stderr=subprocess.DEVNULL)


class VpnManager:
    def __init__(self, parallel=PARALLEL_TUNNELS):
        self.parallel = parallel
        self.tunnels: list[VpnTunnel] = []
        self.rr_index = 0

    def fetch_vpngate_configs(self, limit=None):
        print("[vpn] fetching VPN Gate server list...")
        raw = urllib.request.urlopen(VPNGATE_API, timeout=30).read()
        text = raw.decode("utf-8", errors="ignore")
        lines = [l for l in text.splitlines() if not l.startswith("*")]
        lines = [l for l in lines if l and not l.startswith("#")]
        reader = csv.reader(io.StringIO("\n".join(lines)))
        headers = next(reader)
        try:
            idx_b64 = headers.index("OpenVPN_ConfigData_Base64")
            idx_ip = headers.index("IP")
            idx_score = headers.index("Score")
        except ValueError:
            print("[vpn] unexpected CSV format")
            return []

        rows = []
        for row in reader:
            if len(row) <= max(idx_b64, idx_ip, idx_score):
                continue
            b64 = row[idx_b64].strip()
            if not b64:
                continue
            score = int(row[idx_score].strip() or "0")
            rows.append((score, row[idx_ip].strip(), b64))

        rows.sort(key=lambda x: x[0], reverse=True)
        if limit:
            rows = rows[:limit]
        print(f"[vpn] got {len(rows)} configs")
        return rows

    async def boot(self):
        configs = self.fetch_vpngate_configs()
        for t in self.tunnels:
            await t.stop()
        self.tunnels.clear()

        selected = configs[:self.parallel * 2]
        print(f"[vpn] starting up to {self.parallel} tunnels...")
        tasks = []
        for i in range(self.parallel):
            if i >= len(selected):
                break
            _, ip, b64 = selected[i]
            t = VpnTunnel(i, b64, exit_ip=ip)
            tasks.append(asyncio.create_task(self._boot_one(t)))

        await asyncio.gather(*tasks, return_exceptions=True)
        alive = [t for t in self.tunnels if t.is_alive()]
        print(f"[vpn] {len(alive)}/{self.parallel} tunnels alive")
        return alive

    async def _boot_one(self, tunnel):
        try:
            ok = await tunnel.start()
            if ok:
                self.tunnels.append(tunnel)
                print(f"[vpn] tunnel {tunnel.index} up (tun={tunnel.tun_ip} exit={tunnel.exit_ip})")
            else:
                print(f"[vpn] tunnel {tunnel.index} failed")
            return ok
        except Exception as e:
            print(f"[vpn] tunnel {tunnel.index} error: {e}")
            return False

    def pick(self):
        alive = [t for t in self.tunnels if t.is_alive()]
        if not alive:
            return None
        t = alive[self.rr_index % len(alive)]
        self.rr_index += 1
        return t

    def mark_bad(self, tunnel):
        tunnel.mark_bad()
        print(f"[vpn] tunnel {tunnel.index} marked bad for {TUNNEL_COOLDOWN}s")


vpn_manager = VpnManager()
