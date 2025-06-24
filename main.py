import discord
import asyncio
import random
import time

from discord import app_commands
from discord.ext import commands
from datetime import datetime

from utils import config, json_util, bingo

# Global lock to prevent concurrent file access
game_data_lock = asyncio.Lock()


# Helper to build a rich Bingo numbers embed
def make_bingo_embed(
    host_name: str, drawn: list[int], new: int | None
) -> discord.Embed:
    """Constructs an embed showing Bingo columns, progress, and the most recent number."""
    # Distribute drawn numbers into B-I-N-G-O columns
    columns = {"B": [], "I": [], "N": [], "G": [], "O": []}
    for n in drawn:
        if n <= 15:
            columns["B"].append(str(n))
        elif n <= 30:
            columns["I"].append(str(n))
        elif n <= 45:
            columns["N"].append(str(n))
        elif n <= 60:
            columns["G"].append(str(n))
        else:
            columns["O"].append(str(n))

    embed = discord.Embed(
        title=f"🎱 Bingo Numbers — Hosted by {host_name}",
        color=discord.Colour.green(),
        timestamp=datetime.utcnow(),
    )
    # Show the most recently called number
    if new is not None:
        embed.add_field(name="🎉 Just Called", value=f"**{new}**", inline=False)
    else:
        embed.add_field(name="🎉 Just Called", value="—", inline=False)

    # Add each Bingo column
    for letter in "BINGO":
        nums = " ".join(sorted(columns[letter])) or "—"
        embed.add_field(
            name=f"{letter} ({len(columns[letter])})", value=nums, inline=False
        )

    # Progress bar footer
    total = 75
    called = len(drawn)
    filled = int(called / total * 10)
    bar = "█" * filled + "░" * (10 - filled)
    embed.set_footer(text=f"{called}/{total} numbers drawn • {bar}")
    return embed


class CardView(discord.ui.View):
    """Interactive 5×5 Bingo card for a single player."""

    def __init__(self, host_id: str, player_id: str):
        super().__init__(timeout=None)
        self.host_id = host_id
        self.player_id = player_id

        # Load the player's card and marks
        game = json_util.load_game_data()[host_id]
        card_numbers = sorted(game[player_id]["card"])
        self.marks = set(game[player_id].get("marks", []))

        # Build a 5×5 grid mapping (row,col) → number (skip center)
        grid: list[list[int | None]] = [[None] * 5 for _ in range(5)]
        positions = [
            (r, c) for r in range(5) for c in range(5) if not (r == 2 and c == 2)
        ]
        for (r, c), num in zip(positions, card_numbers):
            grid[r][c] = num

        # Add a button for each cell
        for r in range(5):
            for c in range(5):
                if r == 2 and c == 2:
                    # Free space
                    btn = discord.ui.Button(
                        label="by @behindsecurity",
                        style=discord.ButtonStyle.success,
                        disabled=True,
                        row=r,
                    )
                else:
                    num = grid[r][c]
                    marked = num in self.marks
                    btn = discord.ui.Button(
                        label=str(num),
                        style=(
                            discord.ButtonStyle.success
                            if marked
                            else discord.ButtonStyle.secondary
                        ),
                        custom_id=f"bingo_card:{host_id}:{player_id}:{num}",
                        row=r,
                    )
                    # every dynamic button uses the same callback
                    btn.callback = self.toggle_mark
                self.add_item(btn)

    async def toggle_mark(self, interaction: discord.Interaction):
        # Only the rightful owner may click
        if str(interaction.user.id) != self.player_id:
            return await interaction.response.send_message(
                "This isn’t your card!", ephemeral=True
            )

        # Parse which number was clicked
        _, host, player, num_s = interaction.data["custom_id"].split(":")
        number = int(num_s)

        # Toggle in-memory
        if number in self.marks:
            self.marks.remove(number)
        else:
            self.marks.add(number)

        # Persist back to disk
        async with game_data_lock:
            data = json_util.load_game_data()
            data[host][player]["marks"] = list(self.marks)
            json_util.save_game_data(data)

        # Update the button’s color
        for btn in self.children:
            if getattr(btn, "custom_id", None) == interaction.data["custom_id"]:
                btn.style = (
                    discord.ButtonStyle.success
                    if number in self.marks
                    else discord.ButtonStyle.secondary
                )
                break

        # Re-render the view
        await interaction.response.edit_message(view=self)


class BingoView(discord.ui.View):
    """View for player interactions during a Bingo game."""

    def __init__(self, host_id: str, message: discord.Message):
        super().__init__(timeout=None)
        self.host_id = host_id
        self.message = message
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
        retry = await self._check_cooldown(interaction.user)
        if retry:
            return await interaction.response.send_message(
                f"Slow down! Try again in {retry:.1f}s.", ephemeral=True
            )

        async with game_data_lock:
            data = json_util.load_game_data()
            if str(interaction.user.id) not in data.get(self.host_id, {}).get(
                "players", []
            ):
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
        label="My Card",
        style=discord.ButtonStyle.primary,
        custom_id="card_button",
        emoji="🃏",
    )
    async def send_card(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        retry = await self._check_cooldown(interaction.user)
        if retry:
            return await interaction.response.send_message(
                f"Slow down! Try again in {retry:.1f}s.", ephemeral=True
            )

        host = self.host_id
        player = str(interaction.user.id)
        async with game_data_lock:
            data = json_util.load_game_data()
            game = data.get(host, {})
            if player not in game.get("players", []):
                return await interaction.response.send_message(
                    "You're not part of this game.", ephemeral=True
                )

        # Build and send the interactive card
        card_view = CardView(host, player)
        await interaction.response.send_message(
            "Here’s your interactive Bingo card—click to mark numbers! (**green numbers does not mean you actually scored, just that you marked them on your card**)",
            view=card_view,
            ephemeral=True,
        )

    async def end_game(self) -> None:
        async with game_data_lock:
            data = json_util.load_game_data()
            data.pop(self.host_id, None)
            json_util.save_game_data(data)
        try:
            await self.message.delete()
        except:
            pass
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(view=self)
        except:
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
        label="Start Bingo",
        style=discord.ButtonStyle.success,
        custom_id="start_button",
        emoji="🚀",
    )
    async def start_game(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        retry = await self._check_cooldown(interaction.user)
        if retry:
            return await interaction.response.send_message(
                f"Slow down! Try again in {retry:.1f}s.", ephemeral=True
            )
        host_id = str(interaction.user.id)
        async with game_data_lock:
            data = json_util.load_game_data()
            if host_id not in data or len(data[host_id]["players"]) < 2:
                return await interaction.response.send_message(
                    "Need at least two players to start.", ephemeral=True
                )
            data[host_id]["started"] = True
            for pid in data[host_id]["players"]:
                data[host_id][pid] = {
                    "card": bingo.generate_bingo_card(),
                    "marks": [],
                    "bingos": 0,
                }
            json_util.save_game_data(data)

        embed = make_bingo_embed(interaction.user.display_name, [], None)
        bingo_msg = await interaction.channel.send(embed=embed)
        # Attach player controls (Claim Bingo & My Card)
        bingo_view = BingoView(host_id, bingo_msg)
        await bingo_msg.edit(view=bingo_view)
        await interaction.response.send_message(
            f"The game has begun, {interaction.user.mention}!", ephemeral=False
        )
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        await self._draw_numbers(host_id, bingo_msg)

    @discord.ui.button(
        label="Join Game",
        style=discord.ButtonStyle.success,
        custom_id="join_button",
        emoji="👥",
    )
    async def join_game(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
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
            if (
                not game
                or game["started"]
                or player_id in data
                or len(game["players"]) >= game["max_players"]
                or player_id in game["players"]
            ):
                return await interaction.response.send_message(
                    "Cannot join game.", ephemeral=True
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
            f"{interaction.user.mention} has joined the game!", ephemeral=True
        )
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(
        label="Leave Game",
        style=discord.ButtonStyle.secondary,
        custom_id="leave_button",
        emoji="🚪",
    )
    async def leave_game(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
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
            if not game or player_id not in game["players"] or player_id == host_id:
                return await interaction.response.send_message(
                    "Cannot leave game.", ephemeral=True
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
            f"{interaction.user.mention} has left the game.", ephemeral=True
        )
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(
        label="Cancel Game",
        style=discord.ButtonStyle.danger,
        custom_id="cancel_button",
        emoji="❌",
    )
    async def cancel_game(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        retry = await self._check_cooldown(interaction.user)
        if retry:
            return await interaction.response.send_message(
                f"Slow down! Try again in {retry:.1f}s.", ephemeral=True
            )
        host_id = str(interaction.user.id)

        async with game_data_lock:
            data = json_util.load_game_data()
            if not data.get(host_id):
                await interaction.response.send_message(
                    "You aren't hosting a game.", ephemeral=True
                )
                return
            data.pop(host_id, None)
            json_util.save_game_data(data)

        await interaction.response.send_message(
            f"Game by <@{host_id}>has been cancelled.", ephemeral=False
        )
        await interaction.message.delete()

    async def _draw_numbers(self, host_id: str, message: discord.Message):
        numbers = list(range(1, 76))
        random.shuffle(numbers)
        drawn: list[int] = []
        for number in numbers:
            await asyncio.sleep(config.DRAW_INTERVAL)
            drawn.append(number)
            async with game_data_lock:
                data = json_util.load_game_data()
                if host_id not in data:
                    break
                data[host_id]["numbers_drawn"] = drawn
                json_util.save_game_data(data)
            # Fetch host name dynamically
            guild = message.guild
            host_member = guild.get_member(int(host_id)) if guild else None
            host_name = host_member.display_name if host_member else str(host_id)
            embed = make_bingo_embed(host_name, drawn, number)
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
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")


@bot.tree.command(name="bingo", description="Host a Bingo game")
@app_commands.describe(max_players="Maximum players")
@app_commands.checks.has_role(int(config.BINGO_ADMIN_ROLE_ID))
async def bingo_host(interaction: discord.Interaction, max_players: int):
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
        description="Click 'Join Game' to participate!",
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
