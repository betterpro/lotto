# Lottoomax Bot (@Lottoomax_bot)

A private Telegram group lottery bot — invite-only, weekly rounds, proportional chances.

## Setup

```bash
git clone https://github.com/betterpro/lotto.git
cd lotto
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set PLATFORM_ADMIN_TELEGRAM_IDS (your Telegram id from @userinfobot)
python bot.py
```

## Bot Info

| Field   | Value                                        |
| ------- | -------------------------------------------- |
| Bot     | [@Lottoomax_bot](https://t.me/Lottoomax_bot) |
| Trustee | @RezHey                                      |

## Member Commands

| Command         | Description                                      |
| --------------- | ------------------------------------------------ |
| `/start`        | Register and open main menu                      |
| `/balance`      | Check credit balance                             |
| `/deposit`      | Request credit top-up (trustee approves)         |
| `/round`        | Current round: pool, participants, your % chance |
| `/participate`  | Stake credit in the open round                   |
| `/tickets`      | Your current + past stakes                       |
| `/history`      | Full round history with winners                  |
| `/transactions` | Your credit ledger                               |
| `/invite`       | Get your personal referral link                  |

## Trustee Commands (@RezHey only)

| Command       | Description                                     |
| ------------- | ----------------------------------------------- |
| `/newround`   | Open a new weekly round                         |
| `/closeround` | Lock entries, prepare for draw                  |
| `/draw`       | Weighted-random draw → type CONFIRM to finalise |
| `/roundinfo`  | Live view of stakes and percentages             |
| `/deposits`   | Approve or reject pending deposit requests      |
| `/members`    | All registered members with balances            |

## How a Round Works

**Chance example:** Alice 50 + Bob 30 + Carol 20 = 100 pool → Alice 50%, Bob 30%, Carol 20%

## VR Experience Booking (`/book`)

A self-contained, Zero Latency–style booking site for reserving free-roam VR
sessions and paying with Stripe. It runs inside the same FastAPI service.

- **Booking page:** `GET /book` — choose experience → date → time slot → players
  → details → Stripe Checkout.
- **Confirmation:** `/book/confirmation.html?ref=VR-XXXXXX` (guests land here
  after paying).
- **API:** `/api/vr/config`, `/api/vr/availability`, `/api/vr/checkout`,
  `/api/vr/booking/{ref}`, and the Stripe webhook `POST /api/vr/webhook`.

Experiences, venue hours, and pricing are configured in `vr_booking.py`
(`EXPERIENCES` / `VENUE`). Bookings are stored in the `vr_bookings` table
(created idempotently at startup; see `migrations/015_vr_bookings.sql`).

**Stripe setup:** set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`, then add a
webhook endpoint in the Stripe dashboard pointing at
`https://<your-host>/api/vr/webhook` for the `checkout.session.completed` and
`checkout.session.expired` events. If `STRIPE_SECRET_KEY` is unset, the flow
still works in **demo mode** — reservations are confirmed without a charge (and
clearly labelled as such).

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
