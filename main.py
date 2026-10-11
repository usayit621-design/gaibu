import discord
from discord import app_commands
import asyncio
import os
import threading
import aiohttp
from flask import Flask

from vpn_manager import vpn_manager
from tunnel_http import api_request, session_pool

# ─────────── config ───────────
TOKEN = "MTU1NzA1NDQxODAxNTQ5MDE1Mg.Gd0PXC.3TAz13m39f5-yG8my17tL0L4Xa8wHT7_haPJpg"
API_BASE = "https://discord.com/api/v10"
SPAM_DELAY = 0.7
PORT = int(os.environ.get("PORT", 8080))

SPAM_TEXT = """
# @everyone
# Raided by Dc_Clan!!!
# Join now -> [Dc_Clan](https://ptb.discord.com/invite/dc-clan)
```
⠀⠀⠀⠀⣀⠤⠔⠒⠒⠒⠒⠒⠒⠒⠦⢄⣀⠀⠀⠀⠀
⠀⢀⡴⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠑⢄⠀⠀
⢀⠎⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⣣⠀
⢸⠀⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢢⠈⡇
⢸⠀⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡼⠀⡇
⠘⡆⢸⠀⢀⣀⣤⣄⡀⠀⠀⠀⢀⣤⣤⣄⡀⠀⡇⡸⠀
⠀⠘⣾⠀⣿⣿⣿⣿⣿⠀⠀⠀⣿⣿⣿⣿⣿⠀⡗⠁⠀
⠀⠀⣿⠀⠙⢿⣿⠿⠃⢠⢠⡀⠙⠿⣿⠿⠃⠀⡇⠀⠀
⠀⠀⠘⣄⡀⠀⠀⠀⢠⣿⢸⣿⠀⠀⠀⠀⠀⣠⠇⠀⠀
⠀⠀⠀⠀⡏⢷⡄⠀⠘⠟⠈⠿⠁⠀⢠⡞⡹⠁⠀⠀⠀
⠀⠀⠀⠀⢹⠸⠘⢢⢠⠤⠤⡤⡄⢰⢡⠁⡇⠀⠀⠀⠀
⠀⠀⠀⠀⢸⠀⠣⣹⢸⠒⠒⡗⡇⣩⠌⢀⡇⠀⠀⠀⠀
⠀⠀⠀⠀⠈⢧⡀⠀⠉⠉⠉⠉⠁⠀⣀⠜⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠉⠓⠢⠤⠤⠤⠔⠊⠁⠀⠀⠀⠀⠀⠀
```
-# https://ptb.discord.com/invite/dc-clan
-# https://dcshorts.dpdns.org/Dc_Clan
-# https://imgur.com/a/QuS0xJy"""

ALLOWED_MENTIONS = {"parse": ["everyone"]}

flask_app = Flask("spam")

# ─────────── discord client (gateway 用) ───────────
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# 起動時に tunnel 0 の IP にバインドしたコネクタで gateway を張る
_gateway_ready = asyncio.Event()


async def build_client_with_tunnel():
    """tunnel 0 にバインドした connector で Client を作り直す"""
    global client, tree
    tunnel = vpn_manager.pick()
    if not tunnel:
        raise RuntimeError("no tunnel available for gateway")

    connector = aiohttp.TCPConnector(
        limit=0,
        ttl_dns_cache=300,
        local_addr=(tunnel.tun_ip, 0),
    )
    client = discord.Client(intents=intents, connector=connector)
    tree = app_commands.CommandTree(client)

    @tree.command(name="dc", description="spam")
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def dc(interaction: discord.Interaction):
        # この response は discord.py 経由（gateway tunnel と同じ IP）
        await interaction.response.send_message(
            "# SPAM", view=SpamView(), ephemeral=True
        )

    @client.event
    async def on_ready():
        try:
            await tree.sync()
        except Exception as e:
            print(f"[bot] tree.sync failed: {e}")
        print(f"[bot] logged in as {client.user} (gateway tunnel={tunnel.index})")
        _gateway_ready.set()

    return client


# ─────────── spam view ───────────
class SpamView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="EXECUTE", style=discord.ButtonStyle.danger)
    async def execute(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ここから先は raw HTTP + tunnel rotation
        asyncio.create_task(spam_via_tunnels(interaction))


# ─────────── raw API spam (rotating tunnels) ───────────
async def spam_via_tunnels(interaction: discord.Interaction):
    app_id = interaction.application_id
    token = interaction.token
    interaction_id = interaction.id

    # 1発目: initial response (interaction callback)
    # type 4 = CHANNEL_MESSAGE_WITH_SOURCE
    cb_url = f"{API_BASE}/interactions/{interaction_id}/{token}/callback"
    status, _ = await api_request(
        "POST", cb_url,
        json_body={
            "type": 4,
            "data": {
                "content": SPAM_TEXT,
                "allowed_mentions": ALLOWED_MENTIONS,
            },
        },
    )
    print(f"[spam] initial response -> {status}")

    # 以降: followup webhook に無限投げ
    followup_url = f"{API_BASE}/webhooks/{app_id}/{token}"
    while True:
        await api_request(
            "POST", followup_url,
            json_body={
                "content": SPAM_TEXT,
                "allowed_mentions": ALLOWED_MENTIONS,
            },
        )
        await asyncio.sleep(SPAM_DELAY)


# ─────────── flask ───────────
@flask_app.route("/")
def health():
    return "spam alive", 200


def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)


# ─────────── supervisor ───────────
async def supervisor():
    while True:
        await vpn_manager.boot()
        if not vpn_manager.tunnels:
            print(f"[supervisor] no tunnels, sleep 600s")
            await asyncio.sleep(600)
            continue

        client = await build_client_with_tunnel()
        _gateway_ready.clear()

        try:
            await client.start(TOKEN)
        except Exception as e:
            print(f"[bot] client error: {e}")
            try:
                await client.close()
            except Exception:
                pass
            await asyncio.sleep(10)


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("[!] root 権限が必要 (netns + openvpn)")
        raise SystemExit(1)

    threading.Thread(target=run_flask, daemon=True).start()
    try:
        asyncio.run(supervisor())
    except KeyboardInterrupt:
        print("[!] shutdown")
        asyncio.run(session_pool.close_all())
        for t in vpn_manager.tunnels:
            asyncio.run(t.stop())
