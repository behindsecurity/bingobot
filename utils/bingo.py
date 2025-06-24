import random
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageFont


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
