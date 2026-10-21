import discord
from discord import app_commands
import asyncio
import os
import threading
from flask import Flask

app = Flask(__name__)

token = os.environ.get("TOKEN")
@app.route("/")
def home():
    return "Bot is alive!"


def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))


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

MENTIONS = discord.AllowedMentions(everyone=True)


class SpamView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="EXECUTE", style=discord.ButtonStyle.danger)
    async def execute(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1発目は interaction response
        await interaction.response.send_message(SPAM_TEXT, allowed_mentions=MENTIONS)

        # 以降は followup で無制限
        while True:
            try:
                await interaction.followup.send(SPAM_TEXT, allowed_mentions=MENTIONS)
            except discord.HTTPException:
                # 429 / その他は無視して回し続ける
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
    try:
        await tree.sync()
    except Exception as e:
        print(f"[bot] tree.sync failed: {e}")
    print(f"logged in as {client.user} ({client.user.id})")


if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    try:
        client.run(token)
    except KeyboardInterrupt:
        pass
