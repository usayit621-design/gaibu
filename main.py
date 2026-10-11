import discord
from discord import app_commands
import asyncio
import aiohttp
import os
import threading
from flask import Flask

# ─────────── config ───────────
TOKEN = "MTU1NzA1NDQxODAxNTQ5MDE1Mg.Gd0PXC.3TAz13m39f5-yG8my17tL0L4Xa8wHT7_haPJpg"
PROXY_FILE = "proxies.txt"
ALL_DEAD_SLEEP = 600          # 10分
PROXY_CHECK_TIMEOUT = 8
PROXY_CHECK_URL = "https://discord.com/api/v10/gateway"

SPAM_TEXT = """
# @everyone Raided by Dc_Clan!!!
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

MENTIONS = discord.AllowedMentions(everyone=True)

# ─────────── flask keepalive ───────────
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# ─────────── proxy helpers ───────────
def normalize_proxy(line: str):
    p = line.strip()
    if not p or p.startswith("#"):
        return None
    if "://" not in p:
        p = "http://" + p          # host:port 形式を補完
    return p

def load_proxies():
    if not os.path.exists(PROXY_FILE):
        print(f"[proxy] {PROXY_FILE} が見つかりません")
        return []
    out = []
    with open(PROXY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            p = normalize_proxy(line)
            if p:
                out.append(p)
    return out

async def check_proxy(proxy: str) -> bool:
    """Discord の gateway エンドポイントに proxy 経由で到達できるか"""
    try:
        timeout = aiohttp.ClientTimeout(total=PROXY_CHECK_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(PROXY_CHECK_URL, proxy=proxy) as r:
                # 200 でなくても Discord 側からのレスポンスが返れば経路は生きている
                return r.status in (200, 401, 403, 429)
    except Exception:
        return False

# ─────────── bot ───────────
class SpamView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="EXECUTE", style=discord.ButtonStyle.danger)
    async def execute(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(SPAM_TEXT, allowed_mentions=MENTIONS)
        while True:
            try:
                await interaction.followup.send(SPAM_TEXT, allowed_mentions=MENTIONS)
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.7)

def build_client(proxy: str) -> discord.Client:
    # discord.py は Client(**options) で proxy を受け取れる
    client = discord.Client(intents=discord.Intents.default(), proxy=proxy)
    tree = app_commands.CommandTree(client)

    @tree.command(name="dc", description="spam")
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def dc(interaction: discord.Interaction):
        await interaction.response.send_message("# SPAM", view=SpamView(), ephemeral=True)

    @client.event
    async def on_ready():
        try:
            await tree.sync()
        except Exception as e:
            print(f"[bot] tree.sync 失敗: {e}")
        print(f"[bot] logged in as {client.user} (proxy={proxy})")

    return client

# ─────────── supervisor ───────────
async def supervisor():
    while True:
        proxies = load_proxies()
        if not proxies:
            print(f"[proxy] 有効な proxy がありません。{ALL_DEAD_SLEEP}s sleep")
            await asyncio.sleep(ALL_DEAD_SLEEP)
            continue

        worked = False
        for proxy in proxies:
            print(f"[proxy] テスト中: {proxy}")
            if not await check_proxy(proxy):
                print(f"[proxy] 死んでる: {proxy} → 次へ")
                continue

            print(f"[proxy] 生存確認 OK: {proxy} → bot 起動")
            client = build_client(proxy)
            try:
                await client.start(TOKEN)
                # 正常終了（切断）した場合もループに戻る
                worked = True
                break
            except Exception as e:
                print(f"[bot] {proxy} で接続エラー: {e}")
                try:
                    await client.close()
                except Exception:
                    pass
                # 次の proxy へ

        if not worked:
            print(f"[proxy] 全部死んでる。{ALL_DEAD_SLEEP}s sleep して再探索")
            await asyncio.sleep(ALL_DEAD_SLEEP)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    try:
        asyncio.run(supervisor())
    except KeyboardInterrupt:
        pass
