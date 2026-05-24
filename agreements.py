"""Plain-text agreements for trustee ↔ beneficiary and per-round draw addenda."""

from datetime import date

BCLC_GROUP_RELEASE_URL = (
    "https://corporate.bclc.com/content/dam/bclccorporate/documents/forms/group-release-form.pdf"
)

_LOTTERY_LABELS = {
    "lotto_max": "Lotto Max",
    "649": "6/49",
    "both": "Lotto Max & 6/49",
}


def lottery_label(lottery_type: str | None) -> str:
    return _LOTTERY_LABELS.get(lottery_type or "", lottery_type or "BCLC draw")


def build_master_agreement(
    *,
    beneficiary_name: str,
    beneficiary_id: int,
    trustee_name: str,
    trustee_id: int,
    accepted_at: str | None = None,
) -> str:
    accepted_line = (
        f"Beneficiary accepted via Lotto Chee on {accepted_at}."
        if accepted_at
        else "Beneficiary accepted via Lotto Chee onboarding."
    )
    return f"""LOTTO CHEE — GROUP POOL TRUSTEE AGREEMENT
Between Group Trustee and Beneficiary

This agreement is between you (the Beneficiary) and the Group Trustee who purchases
BCLC group lottery tickets on behalf of the Lotto Chee pool.

PARTIES
  Group Trustee: {trustee_name} (Telegram ID {trustee_id})
  Beneficiary:   {beneficiary_name} (Telegram ID {beneficiary_id})

1. ROLE OF TRUSTEE
   The Trustee collects stakes, forms a group ticket purchase, and holds the physical
   or digital ticket until the official BCLC draw. The Trustee does not guarantee any
   prize outcome.

2. BCLC GROUP PRIZE REQUIREMENTS
   If any pooled ticket wins $10,000 CAD or more, the official BCLC Group Prize
   Agreement (Group Release Form) applies. Reference document:
   {BCLC_GROUP_RELEASE_URL}

   Each Beneficiary must provide accurate legal identity information as collected
   during Lotto Chee onboarding. The Trustee will file the BCLC form on behalf of the
   group when required.

3. STAKES & PAYOUTS
   - Stakes are held in your Lotto Chee balance until allocated to a round.
   - Prizes are distributed proportionally to each Beneficiary's verified share unless
     otherwise stated in a round-specific addendum.
   - The Trustee may deduct only pre-disclosed per-share ticket costs.

4. ROUND ADDENDA
   Each draw round has a short Round Draw Agreement (addendum) that references this
   master agreement and states your share, game type, and draw date for that round.
   Round agreements become available once entries close (one day before draw) so the
   Trustee can purchase tickets.

5. ENTRY WINDOW
   Rounds accept new stakes until 11:59 PM local time on the calendar day that is
   one full day before the scheduled draw date. After that, entries lock so tickets
   can be purchased.

6. ACCURACY & ELIGIBILITY
   You confirm you are 19+ and legally permitted to participate in BCLC lottery
   products in British Columbia. You agree your profile information is accurate.

7. LIMITATION
   BCLC is not a party to this agreement. Lotto Chee facilitates pooling only.

{accepted_line}

— Lotto Chee · BC, Canada
"""


def build_round_agreement(
    *,
    round_id: int,
    lottery_type: str | None,
    draw_date: str | None,
    beneficiary_name: str,
    shares: int,
    stake_amount: float,
    pool_amount: float,
    share_pct: float | None,
    closed_at: str | None = None,
) -> str:
    pct_line = f"{share_pct}%" if share_pct is not None else "—"
    closed_line = f"Entries closed: {closed_at}\n" if closed_at else ""
    return f"""LOTTO CHEE — ROUND DRAW AGREEMENT (ADDENDUM)
Round #{round_id}

This addendum supplements the Group Pool Trustee Agreement between you and the
Group Trustee. In case of conflict on this round only, this addendum controls for
Round #{round_id}.

ROUND DETAILS
  Game:      {lottery_label(lottery_type)}
  Draw date: {draw_date or "TBD"}
{closed_line}
YOUR PARTICIPATION
  Beneficiary: {beneficiary_name}
  Shares:      {shares}
  Stake:       ${stake_amount:.2f} CAD
  Pool share:  {pct_line} of round pool (${pool_amount:.2f} CAD total)

BCLC REFERENCE
  Official group release form (if prize ≥ $10,000 CAD):
  {BCLC_GROUP_RELEASE_URL}

By participating in this round you confirm you have read the master trustee agreement
and accept this round-specific share for the draw listed above.

— Round #{round_id} · Lotto Chee
"""
