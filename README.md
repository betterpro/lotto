# Group Lottery Telegram Bot

A private Telegram bot for running weekly group lotteries among friends (and friends-of-friends).

## Features

| Feature | Description |
|---------|-------------|
| **Invite-only** | Members join via personal referral links — no public access |
| **Credit wallet** | Each member has an in-bot balance; deposits are confirmed by the trustee |
| **Weekly rounds** | Trustee opens/closes rounds; members stake any amount of their credit |
| **Proportional chance** | Your chance = your stake ÷ total pool (shown live as a %) |
| **Weighted draw** | Winner selected randomly, weighted by stake size |
| **Auto-notification** | All participants notified of result; winner gets pool credited instantly |
| **Full history** | Members see past rounds, their own tickets, transaction ledger |
| **One trustee** | A single admin manages rounds, approves deposits, sees all members |

---

## Quick Start

### 1. Create a Telegram Bot

Talk to [@BotFather](https://t.me/BotFather) on Telegram:

```
/newbot
```

Copy the token it gives you.

### 2. Find your Telegram user ID

Talk to [@userinfobot](https://t.me/userinfobot) — it replies with your numeric ID (e.g. `123456789`). This will be the trustee ID.

### 3. Install dependencies

```bash
cd lotto_bot
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Configure

```bash
cp .env.example .env
# Edit .env and fill in BOT_TOKEN and TRUSTEE_TELEGRAM_ID
```

### 5. Run

```bash
python bot.py
```

---

## Bot Commands

### Members

| Command | Description |
|---------|-------------|
| `/start` | Register and see main menu |
| `/balance` | Check credit balance |
| `/deposit` | Request a credit top-up (trustee must approve) |
| `/round` | View current round: pool, participants, your % chance |
| `/participate` | Stake credit in the open round |
| `/tickets` | See your stake in the current round + past rounds |
| `/history` | Full round history with winners |
| `/transactions` | Your credit ledger |
| `/invite` | Get your personal referral link |

### Trustee only

| Command | Description |
|---------|-------------|
| `/newround` | Open a new lottery round |
| `/closeround` | Lock the round (no more entries) |
| `/draw` | Weighted random draw → shows winner → type CONFIRM to finalise |
| `/roundinfo` | Live view of current round and all stakes |
| `/deposits` | List and approve/reject pending deposit requests |
| `/members` | All registered members with balances |

---

## How a Round Works

```
Trustee: /newround          ← round opens
Members: /participate       ← each member stakes some credit
Trustee: /closeround        ← no more entries accepted
Trustee: /draw              ← bot picks weighted-random winner, shows result
Trustee: types CONFIRM      ← winner notified, prize credited to their balance
```

**Chance calculation example:**
- Alice stakes 50, Bob stakes 30, Carol stakes 20 → pool = 100
- Alice: 50% chance, Bob: 30%, Carol: 20%

---

## Deploying 24/7

Run on any server (VPS, Raspberry Pi, etc.):

```bash
# Using systemd (Linux)
sudo nano /etc/systemd/system/lotto-bot.service
```

```ini
[Unit]
Description=Group Lottery Telegram Bot
After=network.target

[Service]
WorkingDirectory=/path/to/lotto_bot
ExecStart=/path/to/lotto_bot/.venv/bin/python bot.py
Restart=always
EnvironmentFile=/path/to/lotto_bot/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now lotto-bot
```

---

## File Structure

```
lotto_bot/
├── bot.py              # Entry point, handler wiring
├── config.py           # Env-var loading
├── database.py         # SQLite async layer (aiosqlite)
├── keyboards.py        # Inline keyboard builders
├── handlers/
│   ├── start.py        # /start, /menu
│   ├── credit.py       # /deposit, /balance, /transactions
│   ├── lottery.py      # /participate, /tickets, /round, /history
│   └── admin.py        # Trustee commands + draw flow
├── requirements.txt
├── .env.example
└── lotto.db            # Created automatically on first run
```
