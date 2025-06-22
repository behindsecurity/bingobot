import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import os
import glob
import time

from utils import config, json_util, bingo

# Global lock to prevent concurrent file access
game_data_lock = asyncio.Lock()


class BingoView(discord.ui.View):
    """View for player interactions during a Bingo game."""

    def __init__(self, host_id: str, message: discord.Message):
        super().__init__(timeout=None)
        self.host_id = host_id
        self.message = message
        # Manual per-user cooldown tracker
        self._last_click: dict[int, float] = {}

    async def _check_cooldown(self, user: discord.User) -> float | None:
        now = time.time()
        last = self._last_click.get(user.id, 0)
        delay = config.BUTTON_COOLDOWN
        if now - last < delay:
            return delay - (now - last)
        self._last_click[user.id] = now
        return None

    @discord.ui.button(
        label="Claim Bingo",
        style=discord.ButtonStyle.success,
        custom_id="bingo_button",
        emoji="🎉",
    )
    async def bingo_check(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Player claims Bingo; checks card against drawn numbers."""
        retry = await self._check_cooldown(interaction.user)
        if retry:
            return await interaction.response.send_message(
                f"Slow down! Try again in {retry:.1f}s.", ephemeral=True
            )

        async with game_data_lock:
            data = json_util.load_game_data()
            players = data.get(self.host_id, {}).get("players", [])
            if str(interaction.user.id) not in players:
                return await interaction.response.send_message(
                    "You're not part of this game.", ephemeral=True
                )

            card_numbers = set(data[self.host_id][str(interaction.user.id)]["card"])
            drawn = set(data[self.host_id]["numbers_drawn"])

        if card_numbers.issubset(drawn):
            await interaction.response.send_message(
                "Congratulations! You got Bingo! 🎉", ephemeral=True
            )
            await interaction.channel.send(
                f":tada: {interaction.user.mention} has won the Bingo game! :tada:"
            )
            await self.end_game()
        else:
            await interaction.response.send_message(
                "Not quite yet. Keep trying!", ephemeral=True
            )

    @discord.ui.button(
        label="My Card", style=discord.ButtonStyle.primary, custom_id="card_button"
    )
    async def send_card(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Sends the player's Bingo card image."""
        retry = await self._check_cooldown(interaction.user)
        if retry:
            return await interaction.response.send_message(
                f"Slow down! Try again in {retry:.1f}s.", ephemeral=True
            )

        async with game_data_lock:
            data = json_util.load_game_data()
            players = data.get(self.host_id, {}).get("players", [])
            if str(interaction.user.id) not in players:
                return await interaction.response.send_message(
                    "You're not part of this game.", ephemeral=True
                )
            card = data[self.host_id][str(interaction.user.id)]["card"]

        bingo.generate_table(str(interaction.user.id), card)
        path = f"images/cards/{interaction.user.id}.png"
        if os.path.exists(path):
            await interaction.response.send_message(
                f"Here is your Bingo card, {interaction.user.name}:",
                file=discord.File(path),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "Sorry, I couldn't generate your card.", ephemeral=True
            )

    async def end_game(self) -> None:
        """Cleans up after a game ends."""
        async with game_data_lock:
            data = json_util.load_game_data()
            data.pop(self.host_id, None)
            json_util.save_game_data(data)
        try:
            await self.message.delete()
        except Exception:
            pass
        for img in glob.glob("images/cards/*.png"):
            try:
                os.remove(img)
            except Exception:
                pass
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass


class HostView(discord.ui.View):
    """View for host controls before and during the Bingo game."""

    def __init__(self):
        super().__init__(timeout=None)
        self._last_click: dict[int, float] = {}

    async def _check_cooldown(self, user: discord.User) -> float | None:
        now = time.time()
        last = self._last_click.get(user.id, 0)
        delay = config.BUTTON_COOLDOWN
        if now - last < delay:
            return delay - (now - last)
        self._last_click[user.id] = now
        return None

    @discord.ui.button(
        label="Start",
        style=discord.ButtonStyle.success,
        custom_id="start_button",
        emoji="🚀",
    )
    async def start_game(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Host starts the Bingo game."""
        retry = await self._check_cooldown(interaction.user)
        if retry:
            return await interaction.response.send_message(
                f"Slow down! Try again in {retry:.1f}s.", ephemeral=True
            )
        host_id = str(interaction.user.id)
        async with game_data_lock:
            data = json_util.load_game_data()
            if host_id not in data:
                return await interaction.response.send_message(
                    "No active game found.", ephemeral=True
                )
            if len(data[host_id]["players"]) < 2:
                return await interaction.response.send_message(
                    "Need at least two players to start.", ephemeral=True
                )
            data[host_id]["started"] = True
            for pid in data[host_id]["players"]:
                card = bingo.generate_bingo_card()
                data[host_id][pid] = {"card": card, "bingos": 0}
            json_util.save_game_data(data)

        embed = discord.Embed(
            title=f"🎱 Bingo Numbers - Hosted by {interaction.user.name}",
            description="No numbers drawn yet.",
            colour=discord.Colour.green(),
        )
        bingo_msg = await interaction.channel.send(embed=embed)
        await interaction.response.send_message(
            f"The game has begun, {interaction.user.mention}!", ephemeral=False
        )
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        await self._draw_numbers(host_id, bingo_msg)

    @discord.ui.button(
        label="Join",
        style=discord.ButtonStyle.success,
        custom_id="join_button",
        emoji="👥",
    )
    async def join_game(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Player joins the Bingo game."""
        retry = await self._check_cooldown(interaction.user)
        if retry:
            return await interaction.response.send_message(
                f"Slow down! Try again in {retry:.1f}s.", ephemeral=True
            )
        host_id = str(interaction.message.interaction.user.id)
        player_id = str(interaction.user.id)
        async with game_data_lock:
            data = json_util.load_game_data()
            game = data.get(host_id)
            if not game:
                return await interaction.response.send_message(
                    "No active game to join.", ephemeral=True
                )
            if game["started"]:
                return await interaction.response.send_message(
                    "Game already started.", ephemeral=True
                )
            if player_id in data:
                return await interaction.response.send_message(
                    "You are hosting another game.", ephemeral=True
                )
            if len(game["players"]) >= game["max_players"]:
                return await interaction.response.send_message(
                    "Game is full.", ephemeral=True
                )
            if player_id in game["players"]:
                return await interaction.response.send_message(
                    "You're already in this game.", ephemeral=True
                )
            game["players"].append(player_id)
            json_util.save_game_data(data)
            mentions = [
                interaction.guild.get_member(int(pid)).mention
                for pid in game["players"]
            ]
            embed = interaction.message.embeds[0]
            embed.set_field_at(
                0, name="Max Players", value=str(game["max_players"]), inline=True
            )
            embed.set_field_at(
                1, name="Players", value="\n".join(mentions), inline=False
            )
        await interaction.response.send_message(
            f"{interaction.user.mention} has joined the game!"
        )
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(
        label="Leave", style=discord.ButtonStyle.secondary, custom_id="leave_button"
    )
    async def leave_game(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Player leaves the Bingo game."""
        retry = await self._check_cooldown(interaction.user)
        if retry:
            return await interaction.response.send_message(
                f"Slow down! Try again in {retry:.1f}s.", ephemeral=True
            )
        host_id = str(interaction.message.interaction.user.id)
        player_id = str(interaction.user.id)
        async with game_data_lock:
            data = json_util.load_game_data()
            game = data.get(host_id)
            if not game or player_id not in game["players"]:
                return await interaction.response.send_message(
                    "You're not in this game.", ephemeral=True
                )
            if player_id == host_id:
                return await interaction.response.send_message(
                    "Host cannot leave their own game.", ephemeral=True
                )
            game["players"].remove(player_id)
            json_util.save_game_data(data)
            mentions = [
                interaction.guild.get_member(int(pid)).mention
                for pid in game["players"]
            ]
            embed = interaction.message.embeds[0]
            embed.set_field_at(
                1, name="Players", value="\n".join(mentions), inline=False
            )
        await interaction.response.send_message(
            f"{interaction.user.mention} has left the game."
        )
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(
        label="Cancel", style=discord.ButtonStyle.danger, custom_id="cancel_button"
    )
    async def cancel_game(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Host cancels the Bingo game."""
        retry = await self._check_cooldown(interaction.user)
        if retry:
            return await interaction.response.send_message(
                f"Slow down! Try again in {retry:.1f}s.", ephemeral=True
            )
        host_id = str(interaction.user.id)
        async with game_data_lock:
            data = json_util.load_game_data()
            if host_id not in data:
                return await interaction.response.send_message(
                    "No active game to cancel.", ephemeral=True
                )
            data.pop(host_id)
            json_util.save_game_data(data)
        await interaction.response.send_message(
            f"Game hosted by <@{host_id}> has been cancelled.", ephemeral=False
        )
        await interaction.message.delete()

    async def _draw_numbers(self, host_id: str, message: discord.Message):
        """Private method: draws numbers at intervals until someone wins or all are drawn."""
        numbers = list(range(1, 76))
        random.shuffle(numbers)
        drawn = []
        view = BingoView(host_id, message)
        await message.edit(view=view)
        for number in numbers:
            await asyncio.sleep(config.DRAW_INTERVAL)
            drawn.append(number)
            async with game_data_lock:
                data = json_util.load_game_data()
                if host_id not in data:
                    break
                data[host_id]["numbers_drawn"] = drawn
                json_util.save_game_data(data)
            embed = message.embeds[0]
            embed.clear_fields()
            embed.add_field(
                name="Numbers Drawn", value=", ".join(map(str, drawn)), inline=False
            )
            try:
                await message.edit(embed=embed)
            except discord.NotFound:
                break


# Initialize bot
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())


@bot.event
async def on_ready():
    async with game_data_lock:
        json_util.save_game_data({})
    for file in glob.glob("images/cards/*.png"):
        try:
            os.remove(file)
        except:
            pass
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")


@bot.tree.command(name="bingo", description="Host a Bingo game")
@app_commands.describe(max_players="Maximum number of players")
@app_commands.checks.has_role(int(config.BINGO_ADMIN_ROLE_ID))
async def bingo_host(interaction: discord.Interaction, max_players: int):
    """Slash command to host a new Bingo game."""
    user_id = str(interaction.user.id)
    async with game_data_lock:
        data = json_util.load_game_data()
        if user_id in data:
            return await interaction.response.send_message(
                "You're already hosting a game.", ephemeral=True
            )
        data[user_id] = {
            "max_players": max_players,
            "started": False,
            "players": [user_id],
            "numbers_drawn": [],
        }
        json_util.save_game_data(data)

    embed = discord.Embed(
        title=f"🎱 Bingo game hosted by {interaction.user.display_name}",
        description="Click 'Join' to participate!",
        colour=discord.Colour.green(),
    )
    embed.set_thumbnail(url=config.BINGO_THUMBNAIL_URL)
    embed.add_field(name="Max Players", value=str(max_players), inline=True)
    embed.add_field(name="Players", value=interaction.user.mention, inline=False)
    view = HostView()
    await interaction.response.send_message(embed=embed, view=view)


# Global error handler
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.CommandOnCooldown):
        msg = f"Command is on cooldown. Try again in {error.retry_after:.1f}s."
    elif isinstance(error, app_commands.MissingRole):
        msg = "You don't have permission to use this command."
    else:
        owner = await bot.fetch_user(config.OWNER_ID)
        await owner.send(f"Error in command {interaction.command.name}: {error}")
        msg = "An unexpected error occurred. The developer has been notified."
    await interaction.response.send_message(msg, ephemeral=True)


if __name__ == "__main__":
    bot.run(config.TOKEN)
