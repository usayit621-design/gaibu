import aiohttp
import asyncio
from vpn_manager import vpn_manager


class TunnelSession:
    """1トンネルにバインドされたaiohttpセッション"""
    def __init__(self, tunnel):
        self.tunnel = tunnel
        self.session = None

    async def start(self):
        if not self.tunnel.tun_ip:
            raise RuntimeError(f"tunnel {self.tunnel.index}: no tun IP")
        connector = aiohttp.TCPConnector(
            limit=0,
            ttl_dns_cache=300,
            local_addr=(self.tunnel.tun_ip, 0),
        )
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=15, sock_read=30)
        self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None


class SessionPool:
    """トンネル番号ごとにセッションを保持して再利用"""
    def __init__(self):
        self.sessions: dict[int, TunnelSession] = {}

    async def get(self, tunnel):
        s = self.sessions.get(tunnel.index)
        if s is None or s.session is None or s.session.closed:
            s = TunnelSession(tunnel)
            await s.start()
            self.sessions[tunnel.index] = s
        return s

    async def drop(self, tunnel):
        s = self.sessions.pop(tunnel.index, None)
        if s:
            await s.close()

    async def close_all(self):
        for s in self.sessions.values():
            await s.close()
        self.sessions.clear()


session_pool = SessionPool()


async def api_request(method, url, headers=None, json_body=None, max_retries=5):
    """トンネル経由でHTTPリクエスト。429/エラーで自動ローテート"""
    headers = headers or {}
    for attempt in range(max_retries):
        tunnel = vpn_manager.pick()
        if not tunnel:
            await asyncio.sleep(5)
            continue

        try:
            sess = await session_pool.get(tunnel)
        except Exception as e:
            print(f"[api] tunnel {tunnel.index} session error: {e}")
            vpn_manager.mark_bad(tunnel)
            continue

        try:
            async with sess.session.request(
                method, url, headers=headers, json=json_body
            ) as resp:
                if resp.status == 429:
                    data = await resp.json()
                    wait = float(data.get("retry_after", 1.0)) + 0.2
                    vpn_manager.mark_bad(tunnel)
                    await session_pool.drop(tunnel)
                    print(f"[api] 429 on tunnel {tunnel.index}, wait {wait}s")
                    await asyncio.sleep(wait)
                    continue
                try:
                    body = await resp.json()
                except Exception:
                    body = await resp.text()
                return resp.status, body
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
            vpn_manager.mark_bad(tunnel)
            await session_pool.drop(tunnel)
            print(f"[api] tunnel {tunnel.index} err: {e}")
            await asyncio.sleep(0.5)

    return 0, {"error": "all tunnels exhausted"}
