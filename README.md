![Bingo The Bot](./images/bingo-the-bot.webp)

A Bingo game bot for Discord, built with discord.py and asyncio. Host, join, and play Bingo with friends—complete with dynamic bingo boards, real-time number draws, and a global leaderboard.

---

## Features

* **Host a Bingo Game**: Use `/bingo` to create a new game, set a maximum player limit, and invite others.
* **Join / Leave**: Players can join or leave waiting rooms via interactive buttons.
* **Start / Cancel**: Hosts can start the game or cancel it at any time.
* **Dynamic Number Draw**: Automatically draws one number at configurable intervals, updates a rich embed grouped by B‑I‑N‑G‑O columns, highlights the latest number, and shows progress.
* **Claim Bingo**: Players can click “Claim Bingo” to verify their card instantly.
* **Personal Bingo Card**: Generate and send personalized bingo cards as PNG images.
* **Leaderboard**: Tracks lifetime wins in a persistent JSON file and displays the top winners with `/leaderboard`.
* **Cooldowns & Concurrency**: Button clicks are rate‑limited per user, and file accesses are synchronized to prevent race conditions.

---

## Prerequisites

* Python 3.10 or higher
* A Discord bot token
* The `discord.py` library (v2.x)

---

## Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/behindsecurity/bingobot.git
   cd bingobot
   ```

2. **Install dependencies**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure the bot**

   * Move `utils/config.example.py` to `utils/config.py`.
   * Fill in your bot token and IDs at `utils/config.py`:

     ```python
TOKEN = "YOUR_BOT_TOKEN"  # Discord bot token
GAME_DATA_PATH = "./bingo_game_data.json"  # Path to a json file that will host the bingo data, e.g. ./bingo_game_data.json
BINGO_ADMIN_ROLE_ID = 1  # Role allowed to host (ROLE ID, INTEGER)
OWNER_ID = 1  # Developer for error alerts (USER ID, INTEGER)

BUTTON_COOLDOWN = 5  # Seconds between button presses
DRAW_INTERVAL = 10  # Seconds between number draws
BINGO_THUMBNAIL_URL = ""  # Embed thumbnail image
     ```

---

## Usage

### Slash Commands

* `/bingo max_players:<int>` — Create a new bingo game.
* `/leaderboard` — Show the all‑time wins leaderboard.

### Interactive Buttons

Once a game is created, players will see buttons:

* **Join Game** (`👥`) — Join the waiting lobby.
* **Leave Game** (`🚪`) — Leave the lobby.
* **Start Bingo** (`🚀`) — Host only: begin drawing numbers.
* **Cancel Game** (`❌`) — Host only: cancel the game.
* **Claim Bingo** (`🎉`) — During a game: claim your bingo.
* **My Card** (`🃏`) — Receive your bingo card.

---

## File Structure

```
├── main.py               # Bot entrypoint and command definitions
├── utils/
│   ├── config.py         # Configuration constants
│   ├── json_util.py      # Game & leaderboard JSON load/save
│   └── bingo.py          # Bingo card generation & image creation
├── data/
│   ├── game_data.json    # Current game sessions
│   └── leaderboard.json  # Lifetime wins tracker
├── images/
│   └── cards/            # Generated bingo card PNGs
├── requirements.txt      # Python dependencies
└── README.md             # This file
```

---

## Contributing

1. Fork the repo.
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes.
4. Push to your fork: `git push origin feature/my-feature`
5. Open a pull request.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
