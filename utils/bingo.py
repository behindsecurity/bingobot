import random
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageFont


def generate_table(user_id: str, current_card: list):
    # Load the template image
    template_path = "images/cartela512x512.png"
    template_image = Image.open(template_path)

    # Bingo numbers to place on the card
    bingo_numbers = sorted(current_card)

    # Positions to place the bingo numbers on the card
    positions = [
        (i, j) for i in range(5) for j in range(5) if not (i == 2 and j == 2)
    ]  # Skip the center position

    # Define font and size
    font_path = "fonts/LEMONMILK-Bold.otf"
    font_size = 50

    # Draw the numbers on the card
    draw = ImageDraw.Draw(template_image)
    font = ImageFont.truetype(font_path, font_size)

    for (i, j), number in zip(positions, bingo_numbers):
        # Calculate position to place the number
        x = 102 * j + 51
        y = 94 * i + 91
        # Draw the number centered in its grid cell
        draw.text((x, y), str(number), font=font, fill="red", anchor="mm")

    # Save the modified image
    output_path = f"images/cards/{user_id}.png"
    template_image.save(output_path)


def generate_bingo_card():
    card = []
    while len(card) < 24:
        num = random.randint(1, 75)
        if num not in card:
            card.append(num)
    return card


def end_game(host_player: str):
    game_data = json_util.load_game_data()
    del game_data[host_player]
    json_util.save_game_data(game_data)


def check_winner(game_data: dict, host_player: str):
    drawn_numbers = set(game_data[host_player]["numbers_drawn"])
    # Lord please forgive me
    for player_id, player_data in game_data[host_player].items():
        if isinstance(player_data, dict) and "card" in player_data:
            if set(player_data["card"]).issubset(drawn_numbers):
                return True
    return False


def update_leaderboard(winner_id: str):
    leaderboard_data = json_util.load_leaderboard_data()
    if winner_id in leaderboard_data:
        leaderboard_data[winner_id] += 1
    else:
        leaderboard_data[winner_id] = 1
    json_util.save_leaderboard_data(leaderboard_data)
