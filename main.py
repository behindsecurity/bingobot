import discord
import requests
import random
import asyncio
import os
import glob

from discord.ext.commands.cooldowns import BucketType
from discord.ext.commands import CooldownMapping
from discord.ext import commands

from utils import config, json_util, bingo


class BingoView(discord.ui.View):
    def __init__(self, host_player, message):
        super().__init__(timeout=None)
        self.host_player = host_player
        self.message = message
        self.cooldown = commands.CooldownMapping.from_cooldown(1, 2, commands.BucketType.member)

    @discord.ui.button(label="Bingo!", style=discord.ButtonStyle.green, custom_id="bingo_button", emoji="🎉")
    async def bingo_check(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check for cooldown
        retry = self.cooldown.get_bucket(interaction.message).update_rate_limit()
        if retry:
            return await interaction.response.send_message(f"Devagar! Tente novamente em {round(retry, 1)} segundos!", ephemeral=True)

        game_data = json_util.load_game_data()
        player_id = str(interaction.user.id)

        # Check if the player is in the game
        if player_id not in game_data[self.host_player]['players']:
            return await interaction.response.send_message('Você não está nesse jogo!', ephemeral=True)

        # Check if the player has a bingo
        player_card = set(game_data[self.host_player][player_id]['card'])
        drawn_numbers = set(game_data[self.host_player]['numbers_drawn'])
        if player_card.issubset(drawn_numbers):
            await interaction.response.send_message('Parabéns! Você fez um Bingo!', ephemeral=True)
            await interaction.channel.send(f'{interaction.user.mention} fez um Bingo!')

            # Delete the message containing the bingo numbers embed
            await self.message.delete()
            await interaction.channel.send(f"O jogo de Bingo hospedado por <@{self.host_player}> terminou!")
        else:
            await interaction.response.send_message('Ainda não! Continue tentando.', ephemeral=True)

    @discord.ui.button(label="Minha Tabela", style=discord.ButtonStyle.blurple, custom_id="card_button", emoji="🃏")
    async def send_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check for cooldown
        retry = self.cooldown.get_bucket(interaction.message).update_rate_limit()
        if retry:
            return await interaction.response.send_message(f"Devagar! Tente novamente em {round(retry, 1)} segundos!", ephemeral=True)
        
        game_data = json_util.load_game_data()
        player_id = str(interaction.user.id)

        # Check if the player is in the game
        if player_id not in game_data[self.host_player]['players']:
            return await interaction.response.send_message('Você não está nesse jogo!', ephemeral=True)

        # Generate the bingo card
        bingo.generate_table(player_id, game_data[self.host_player][player_id]['card'])

        # Send the bingo card as a file
        file = discord.File(f"images/cards/{player_id}.png", filename="bingo_card.png")
        await interaction.response.send_message(f'Aqui está a sua tabela, {interaction.user.name}', file=file, ephemeral=True) 


class hostButtons(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.cooldown = commands.CooldownMapping.from_cooldown(1, 3, commands.BucketType.user)

    @discord.ui.button(label="Iniciar Bingo", style=discord.ButtonStyle.green, custom_id="start_button", emoji="🚀")
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        host_player = str(interaction.message.interaction.user.id)
        interacting_player = str(interaction.user.id)
        if interacting_player != host_player:
            return await interaction.response.send_message('Somente o hospedeiro do jogo pode começar a partida!', ephemeral=True)

        game_data = json_util.load_game_data()

        if len(game_data[host_player]['players']) == 1:
            return await interaction.response.send_message('Não dá pra iniciar a sua partida, está vazio por aqui...', ephemeral=True)

        game_data[host_player]['started'] = True

        for player_id in game_data[host_player]['players']:
            card = bingo.generate_bingo_card()
            game_data[host_player][player_id] = {"card": card, "bingos": 0}
            json_util.save_game_data(game_data)

        # Saves users cards
        json_util.save_game_data(game_data)

        # Create initial embed for bingo numbers
        bingo_embed = discord.Embed(title=f"🎱 Números do Bingo - Partida de {interaction.message.interaction.user.name}", description="Números sorteados aparecerão aqui.", color=discord.Colour.green())
        message = await interaction.channel.send(embed=bingo_embed)

        await interaction.response.send_message(f'O jogo de {interaction.message.interaction.user.mention} começou!')
        await interaction.message.edit(view=None)

        return await call_numbers(interaction, message)
        

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green, custom_id="join_button", emoji="👥")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        host_player = str(interaction.message.interaction.user.id)
        interacting_player = str(interaction.user.id)

        # If reaches the max player limit
        game_data = json_util.load_game_data()
        if len(game_data[host_player]['players']) == game_data[host_player]['max_players']:
            return await interaction.response.send_message('Esse jogo está cheio!', ephemeral=True)

        # Players can't join if the game has started
        if game_data[host_player]['started']:
            return await interaction.response.send_message('Esse jogo já começou!', ephemeral=True)

        if interacting_player in game_data[host_player]['players']:
            return await interaction.response.send_message('Você já está nesse jogo!', ephemeral=True)

        # Player can't join if they are the host of the game
        if interacting_player == host_player:
            return await interaction.response.send_message('Huh? Mas foi você quem começou o jogo!', ephemeral=True)

        # If the interacting player is hosting a game (present as a dictionary key in the game data), they should
        # not be able to join others' games.
        if interacting_player in game_data:
            return await interaction.response.send_message('Você está hospedando um jogo, portanto não pode entrar no jogo de outras pessoas.', ephemeral=True)

        game_data[host_player]['players'].append(interacting_player)
        json_util.save_game_data(game_data)
        
        # Update the embed with the new player list
        players_mentions = [interaction.guild.get_member(int(player_id)).mention for player_id in game_data[host_player]['players']]
        embed = interaction.message.embeds[0]
        embed.clear_fields()
        embed.add_field(name="📢 Máximo de jogadores", value=f"{game_data[host_player]['max_players']}")
        embed.add_field(name="👥 Jogadores", value="\n".join(players_mentions) if players_mentions else "Nenhum jogador ainda.")

        await interaction.message.edit(embed=embed, view=self)
        return await interaction.response.send_message(f'Você entrou no jogo de {interaction.message.interaction.user.mention}', ephemeral=True)


    @discord.ui.button(label="Sair", style=discord.ButtonStyle.blurple, custom_id="leave_button", emoji="🚪")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        host_player = str(interaction.message.interaction.user.id)
        interacting_player = str(interaction.user.id)

        game_data = json_util.load_game_data()
        if interacting_player not in game_data[host_player]['players']:
            return await interaction.response.send_message('Você não está nesse jogo!', ephemeral=True)

        if interacting_player == host_player:
            return await interaction.response.send_message('Ué, mas você não pode sair de um jogo que você mesmo hospedou!', ephemeral=True)

        game_data[host_player]['players'].remove(interacting_player)
        json_util.save_game_data(game_data)

        players_mentions = [interaction.guild.get_member(int(player_id)).mention for player_id in game_data[host_player]['players']]
        embed = interaction.message.embeds[0]
        embed.clear_fields()
        embed.add_field(name="📢 Máximo de jogadores", value=f"{game_data[host_player]['max_players']}")
        embed.add_field(name="👥 Jogadores", value="\n".join(players_mentions) if players_mentions else "Nenhum jogador ainda.")
        await interaction.message.edit(embed=embed, view=self)
        
        return await interaction.response.send_message(f'Você saiu do jogo de {interaction.message.interaction.user.mention}', ephemeral=True)


    @discord.ui.button(label="Cancelar Bingo", style=discord.ButtonStyle.red, custom_id="cancel_button", emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        host_player = str(interaction.message.interaction.user.id)
        interacting_player = str(interaction.user.id)

        if interacting_player != host_player:
            return await interaction.response.send_message('Somente o host da partida pode cancelar a partida!', ephemeral=True)

        game_data = json_util.load_game_data()
        del game_data[host_player]

        json_util.save_game_data(game_data)
        await interaction.response.send_message(f'O jogo hospedado por {interaction.message.interaction.user.mention} foi cancelado!')
        return await interaction.message.delete()


class aclient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(intents=intents)
        self.synced = False  # we use this so the bot doesn't sync commands more than once
        self.added = False

    async def on_ready(self):
        await self.wait_until_ready()

        # Clear the JSON file
        self.clear_game_data()

        # Delete all PNG files from the images/cards directory
        self.delete_png_files()

        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="Bingo!"))

        # Check if slash commands have been synced
        if not self.synced:
            # Can choose to sync guild only or global adding id=...
            #await tree.sync(guild=discord.Object(id=config.GUILD_ID))
            await tree.sync()
            # await wait_ready.start()
            self.synced = True
        
        if not self.added:
            """
            self.add_view(economy_launcher())
            self.add_view(ticket_launcher())
            self.add_view(main())
            self.add_view(reaction_roles())
            self.add_view(crash_view())
            """
            self.added = True
        
        print(f"[+] Tudo pronto, login efetuado como {self.user}.")

    def clear_game_data(self):
        """Clear all game data from the JSON file."""
        game_data = {}
        json_util.save_game_data(game_data)
        print("Game data cleared from JSON file.")

    def delete_png_files(self):
        """Delete all PNG files from the images/cards directory."""
        files = glob.glob('images/cards/*.png')
        for file in files:
            try:
                os.remove(file)
                print(f"Deleted file: {file}")
            except Exception as e:
                print(f"Error deleting file {file}: {e}")

client = aclient()
tree = discord.app_commands.CommandTree(client)









@tree.command(name="bingo", description="Hospede uma partida de Bingo!")
@discord.app_commands.describe(max_players = "Qual é o número máximo de jogadores?")
@discord.app_commands.checks.has_role("🎲 Bingo Admin")
async def bingo_host(interaction: discord.Interaction, max_players: int):
    game_data = json_util.load_game_data()
    
    interacting_player = str(interaction.user.id) 

    if interacting_player in game_data:
        await interaction.response.send_message("Você já está hospedando um jogo de bingo!", ephemeral=True)
        return
    
    game_data[interacting_player] = {
        "max_players": max_players,
        "started": False,
        "players": [interacting_player],
        "numbers_drawn": []
    }
    json_util.save_game_data(game_data)

    embed = discord.Embed(title=f"🎱 Bingo hospedado por {interaction.user.name}", description="Para participar, basta clicar no botão abaixo!", color=discord.Colour.green())
    embed.set_thumbnail(url="https://media.discordapp.net/attachments/1256669755700674591/1256670355045613598/IMG_7625.jpg")
    embed.set_footer(text=config.FOOTER_TEXT)
    embed.add_field(name="📢 Máximo de jogadores", value=max_players)

    return await interaction.response.send_message(embed=embed, view=hostButtons())


async def call_numbers(interaction: discord.Interaction, message: discord.Message):
    host_player = str(interaction.user.id)
    game_data = json_util.load_game_data()
    drawn_numbers = game_data[host_player]["numbers_drawn"]

    bingo_view = BingoView(host_player, message)
    await message.edit(view=bingo_view)

    while len(drawn_numbers) < 75:
        await asyncio.sleep(10)

        number = random.randint(1, 75)
        if number not in drawn_numbers:
            drawn_numbers.append(number)
            game_data[host_player]["numbers_drawn"] = drawn_numbers
            
            # Update the embed with the new number
            bingo_embed = message.embeds[0]
            bingo_embed.description = f"Números sorteados: {', '.join(map(str, drawn_numbers))}"
            
            # If we fail to edit the message it means the game ended
            try:
                await message.edit(embed=bingo_embed)
            except Exception:
                game_data = json_util.load_game_data()
                del game_data[host_player]
                json_util.save_game_data(game_data)
                
                break

            # If not, save the game data and continue
            json_util.save_game_data(game_data)




@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    embed = discord.Embed(title="Erro!", description=f"Aconteceu um erro na execução do comando `{interaction.command.name}`.", color=discord.Colour.red())
    name = "🧾 Informações"
    
    if isinstance(error, discord.app_commands.CommandOnCooldown):
        value = f"O comando está em cooldown! Tente novamente em: {round(error.retry_after)} segundos ({round(error.retry_after) // 60} minutos)."
    elif isinstance(error, discord.app_commands.MissingPermissions):
        value = "Você não tem permissão para executar esse comando."
    elif isinstance(error, discord.app_commands.MissingRole):
        value = "Você não tem o cargo necessário para executar esse comando."
    elif isinstance(error, discord.app_commands.MissingRequiredArgument):
            value = "Você esqueceu de fornecer um argumento necessário para este comando."
    elif isinstance(error, discord.app_commands.BadArgument):
        value = "Você forneceu um argumento inválido para este comando."
    elif isinstance(error, discord.app_commands.CommandNotFound):
        value = "Esse comando não existe."
    elif isinstance(error, discord.app_commands.BotMissingPermissions):
        value = "Eu não tenho permissão para executar este comando."
    elif isinstance(error, discord.app_commands.NoPrivateMessage):
        value = "Esse comando não pode ser usado em mensagens privadas."
    elif isinstance(error, discord.app_commands.DisabledCommand):
        value = "Esse comando está desativado."
    elif isinstance(error, discord.app_commands.CommandInvokeError):
        value = f"Ocorreu um erro ao tentar executar este comando: {error.original}"
    else:
        owner = await client.fetch_user(1199395072983179356)
        await owner.send(f"Ocorreu um erro inesperado na execução de um comando.\n\nCanal: {interaction.channel.mention}\nQuem executou: {interaction.user.mention}\nComando: `{interaction.command.name}`\nInformações detalhadas do erro: `{error}`")
        
        if interaction.response.is_done():
            return await interaction.followup.send("Não foi possível executar o comando, pois ele contém 1 ou mais erros. De qualquer maneira, enviei informações detalhadas do erro para o meu criador.")
        
        return await interaction.response.send_message("Não foi possível executar o comando, pois ele contém 1 ou mais erros. De qualquer maneira, enviei informações detalhadas do erro para o meu criador.", ephemeral=True)
    
    embed.add_field(name=name, value=value)
    embed.set_footer(text=config.FOOTER_TEXT)
    if interaction.response.is_done(): return await interaction.followup.send(embed=embed)
    return await interaction.response.send_message(embed=embed, ephemeral=True)



try:
    client.run(config.TOKEN)
except:
    r = requests.head(url="https://discord.com/api/v1")
    retry_after = int(r.headers['Retry-After'])
    print(f"[-] Bloqueado pela API do Discord.\n\nRate limit: {round(retry_after / 60)} minutos restantes.")
