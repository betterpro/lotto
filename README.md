# Lottoomax Bot (@Lottoomax_bot)

A private Telegram group lottery bot — invite-only, weekly rounds, proportional chances.

## Setup

```bash
git clone https://github.com/betterpro/lotto.git
cd lotto
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set your TRUSTEE_TELEGRAM_ID (get it from @userinfobot)
python bot.py
```

## Bot Info

| Field | Value |
|-------|-------|
| Bot | [@Lottoomax_bot](https://t.me/Lottoomax_bot) |
| Trustee | @RezHey |

## Member Commands

| Command | Description |
|---------|-------------|
| `/start` | Register and open main menu |
| `/balance` | Check credit balance |
| `/deposit` | Request credit top-up (trustee approves) |
| `/round` | Current round: pool, participants, your % chance |
| `/participate` | Stake credit in the open round |
| `/tickets` | Your current + past stakes |
| `/history` | Full round history with winners |
| `/transactions` | Your credit ledger |
| `/invite` | Get your personal referral link |

## Trustee Commands (@RezHey only)

| Command | Description |
|---------|-------------|
| `/newround` | Open a new weekly round |
| `/closeround` | Lock entries, prepare for draw |
| `/draw` | Weighted-random draw → type CONFIRM to finalise |
| `/roundinfo` | Live view of stakes and percentages |
| `/deposits` | Approve or reject pending deposit requests |
| `/members` | All registered members with balances |

## How a Round Works



**Chance example:** Alice 50 + Bob 30 + Carol 20 = 100 pool → Alice 50%, Bob 30%, Carol 20%

## Deploy 24/7 (Linux systemd)

```ini
[Unit]
Description=Lottoomax Telegram Bot
After=network.target

[Service]
WorkingDirectory=/path/to/lotto
ExecStart=/path/to/lotto/.venv/bin/python bot.py
Restart=always
EnvironmentFile=/path/to/lotto/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now lottoomax
```
