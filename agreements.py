"""Agreement text for BCLC Group Prize Agreement and per-round addenda."""

BCLC_GROUP_RELEASE_URL = (
    "https://corporate.bclc.com/content/dam/bclccorporate/documents/forms/group-release-form.pdf"
)

DEFAULT_TRUSTEE = {
    "name": "Reza Heidari",
    "street": "2039 Westview Dr.",
    "city": "North Vancouver",
    "province": "BC",
    "phone": "236-999-7878",
    "email": "rezaheidari@gmail.com",
}

# Legacy alias
TRUSTEE = DEFAULT_TRUSTEE

DECLARATION_CATEGORIES = {
    "a": "A Lottery Retailer (operates or works at a BCLC retail location)",
    "b": "A family member of a Lottery Retailer (parent, child, spouse, household)",
    "c": "A BCLC employee",
    "d": "A family member of a BCLC employee",
    "e": "None of the above",
}


def declaration_category_label(code: str | None) -> str:
    key = (code or "e").lower()
    label = DECLARATION_CATEGORIES.get(key, DECLARATION_CATEGORIES["e"])
    return f"{key.upper()} — {label}"


def build_trustee_from_user(user: dict) -> dict:
    """Build trustee dict from a users row (group trustee beneficiary profile)."""
    name = user.get("full_name") or user.get("username") or "Group Trustee"
    return {
        "name": name,
        "street": user.get("street") or DEFAULT_TRUSTEE["street"],
        "city": user.get("city") or DEFAULT_TRUSTEE["city"],
        "province": user.get("province") or DEFAULT_TRUSTEE["province"],
        "phone": user.get("phone") or DEFAULT_TRUSTEE["phone"],
        "email": user.get("email") or DEFAULT_TRUSTEE["email"],
    }

from lottery_types import lottery_label as _catalog_lottery_label

_PREF_LABELS = {"both": "Lotto Max & 6/49"}


def lottery_label(lottery_type: str | None) -> str:
    key = lottery_type or ""
    if key in _PREF_LABELS:
        return _PREF_LABELS[key]
    return _catalog_lottery_label(lottery_type)


def _format_address(street: str | None, city: str | None, province: str | None, postal: str | None) -> str:
    parts = []
    if street:
        parts.append(street)
    line2 = ", ".join(p for p in [city, province, postal] if p)
    if line2:
        parts.append(line2)
    return "\n  ".join(parts) if parts else "-"


def build_master_agreement(
    *,
    beneficiary_name: str,
    beneficiary_id: int,
    beneficiary_street: str | None = None,
    beneficiary_city: str | None = None,
    beneficiary_province: str | None = None,
    beneficiary_postal: str | None = None,
    beneficiary_phone: str | None = None,
    beneficiary_email: str | None = None,
    declaration_category: str | None = None,
    accepted_at: str | None = None,
    trustee: dict | None = None,
    pricing_plan: str | None = None,
    **_kwargs,
) -> str:
    """Full Group Prize Agreement (BCLC form content) with group trustee and round addendum notice."""
    t = trustee or DEFAULT_TRUSTEE
    if (pricing_plan or "subscription") == "prize_share":
        plan_clause = (
            "PLATFORM SERVICE PLAN\n"
            "  This group is on the Big-Prize Share plan, chosen by the Group Trustee when the\n"
            "  group was created and fixed for the life of the group. No monthly fee applies.\n"
            "  The Beneficiaries acknowledge and agree that LottoChee may claim a service fee\n"
            "  of five percent (5%) of any single Prize exceeding $1,000.00 CAD, deducted from\n"
            "  that Prize before the remainder is distributed to the Beneficiaries by share."
        )
    else:
        plan_clause = (
            "PLATFORM SERVICE PLAN\n"
            "  This group is on the Monthly Subscription plan, chosen by the Group Trustee when\n"
            "  the group was created and fixed for the life of the group. The Group Trustee pays\n"
            "  LottoChee a service fee of $6.99 CAD per month. LottoChee claims no share of\n"
            "  any Prize won by the group."
        )
    ben_address = _format_address(
        beneficiary_street, beneficiary_city, beneficiary_province, beneficiary_postal
    )
    trustee_address = _format_address(
        t["street"], t["city"], t["province"], None
    )
    decl = declaration_category_label(declaration_category)
    signed_date = accepted_at[:10] if accepted_at and len(accepted_at) >= 10 else "See LottoChee account"

    return f"""GROUP PRIZE AGREEMENT
(BCLC Group Release Form - LottoChee)

This Group Prize Agreement is required when a group lottery ticket wins a prize of
$1,000.00 CAD or greater and must be completed by all group members entitled to a
share of the prize won. LottoChee uses this agreement for pooled play and registers
each member as a Beneficiary with the Group Trustee named below.

GROUP TRUSTEE
  Name:     {t["name"]}
  Address:  {trustee_address}
  Phone:    {t["phone"]}
  Email:    {t["email"]}

BENEFICIARY
  Name:     {beneficiary_name}
  Address:  {ben_address}
  Phone:    {beneficiary_phone or "-"}
  Email:    {beneficiary_email or "-"}
  Declaration category: {decl}

ROUND AMENDMENT (ADDENDUM)
  For each draw you join, a separate Round Draw Agreement (amendment) is issued once
  entries close (one day before the draw). That amendment states your share, stake,
  pool percentage, lottery game, and draw date for that round. It supplements this
  master agreement. In case of conflict for a specific round, the round amendment
  controls for that round only.

TICKET INFORMATION
  Ticket name:            Pooled BCLC ticket per round (Lotto Max, 6/49, or as stated
                          in your round amendment)
  Draw date(s):           As stated in each round amendment you join
  Ticket control number:  Assigned by LottoChee per round when the ticket is purchased

The Group Trustee holds each pooled ticket on behalf of all Beneficiaries who joined
that round.

{plan_clause}

TERMS AND CONDITIONS
Each of the Beneficiaries, for and in consideration of and to induce the Corporations
(British Columbia Lottery Corporation, "BCLC", and the Interprovincial Lottery
Corporation, "ILC") to make payment or deliver any and all prizes associated with the
Ticket (the "Prize"), hereby represent and warrant to and agree with the Corporations
as follows:

1. That the Beneficiaries are the only individuals with a legal or beneficial interest
   in the ticket bearing the control number assigned for the round joined (the
   "Ticket").

2. The Group Trustee is the lawful holder of the Ticket and no person other than the
   Beneficiaries has any interest in the Ticket or any right to payment or delivery of
   any portion of the Prize.

3. That the Group Trustee ({t["name"]}) has been authorized by the Beneficiaries
   to accept from BCLC, for and on behalf of all Beneficiaries, the Prize.

4. That the Group Trustee is: (a) a Beneficiary and member of the group entitled to
   receive a share of the Prize; (b) the holder of the ticket as trustee for the
   Beneficiaries; and (c) irrevocably authorized to receive payment of the Prize from
   the Corporations in trust for the Beneficiaries.

5. It is the responsibility of the Group Trustee and Beneficiaries, and not the
   Corporations, to ensure that the Prize is distributed to the Beneficiaries as the
   parties solely entitled to receive a portion of the Prize.

6. The Beneficiaries have read, are familiar with and agree to be bound by, all rules
   and regulations, game conditions and prize structure statements adopted by the
   Corporations that apply to the Game or the Ticket.

7. Payment or delivery of the Prize to the Group Trustee by the Corporations as
   directed herein releases the Corporations from any further claims or demands by any
   Beneficiary in respect of the Ticket.

8. That the Beneficiaries agree the Ticket is not eligible for any additional payments
   or prizes even where payments or prizes on other tickets in the Game are unclaimed.

9. All parties entitled to the Prize have been identified as a Beneficiary in this
   agreement (and in each applicable round amendment). All Beneficiaries acknowledge
   that BCLC has no responsibility to ensure receipt of any Prize or portion thereof
   by any Beneficiary.

10. The Beneficiaries are each the full age of nineteen (19) years.

11. The Beneficiaries hereby authorize and consent to BCLC collecting, recording,
    publishing and broadcasting their respective names, addresses, places of residence,
    prize details, images and expressed statements (a) without any claim for licensing
    or broadcasting rights; and (b) without any claim related to the public release of
    the Beneficiaries' Information.

12. After two years from the date BCLC first declares the Beneficiaries' win publicly,
    BCLC will, where feasible, remove or prevent further publication of the
    Beneficiaries' Information on BCLC-controlled media. BCLC cannot control use by
    third parties beyond the two-year period.

13. The Beneficiaries hereby, jointly and severally, undertake to indemnify and save
    BCLC and the ILC harmless from and against any liability, actions, claims,
    demands, losses, payment and costs of any nature whatsoever related to the Ticket,
    the Prize, publication of the Beneficiaries' Information and the prize claim process.

14. This Agreement may be executed in counter-parts by the Group Trustee and
    Beneficiaries and shall be binding upon the Group Trustee and Beneficiaries and
    their respective heirs, executors, administrators and assigns.

15. That each Beneficiary has completed, in full, the information required above and
    by their signature below acknowledges he or she: (a) has read and accepts all
    terms contained herein; (b) has been given the opportunity to obtain independent
    legal advice; (c) confirms that all information provided is true and accurate.

GROUP-PLAY RULES & SAFEGUARDS
These rules govern how the group plays each draw and protect every Beneficiary. They
apply to all rounds under this agreement, alongside each Round Draw Agreement amendment.

  A. No pay, no share. A Beneficiary is included in a draw only if full payment is
     received and recorded by the posted cut-off time before tickets are purchased.
     LottoChee locks the paid participant list at the cut-off and preserves that final
     list as the record for the draw. No payment by the cut-off means no ownership
     share for that draw.

  B. Ticket proof after purchase. After the Group Trustee buys the ticket(s), LottoChee
     records and shows the ticket image/copy, ticket control number, draw date, total
     cost, the paid participant list, and each Beneficiary's share for that round.
     Beneficiaries can check the tickets themselves.

  C. Original ticket custody. The Group Trustee holds each pooled ticket as property
     of the group, marked "In Trust" / "Group Ticket", stored securely and kept
     separate from personal tickets, and photographed/scanned immediately. Only the
     original ticket may be used to claim a prize.

  D. Prize-claim plan. The Group Trustee coordinates prize claims with the applicable
     lottery corporation. Valid government-issued photo ID is required. Group claims of
     $10,000 CAD or more require a Group Prize Agreement completed by every member
     entitled to a share.

  E. Payout in writing. Winnings are paid to the Group Trustee as trustee only, never
     personally, using a clearly traceable account, with a written payout confirmation
     to each Beneficiary. Distribution is by the recorded pool shares for the round.

  F. Audit trail. LottoChee retains join/leave history, payment confirmations, the
     cut-off timestamp, ticket-purchase timestamp, ticket images, the final per-draw
     participant list, results, payout confirmations, and admin actions. These records
     — not chat history — are the group's evidence and can be exported per draw.

  G. Privacy & consent. LottoChee collects only the information needed to run the pool
     (name, contact, and payment details) and uses it to administer the group, record
     participation and payments, and process prize claims. Sensitive ID and payment
     data are kept out of ordinary chat. You may ask what is held about you and request
     deletion where retention is not legally required.

  H. Legal boundary. LottoChee is a coordination and record-keeping tool, not a lottery
     operator. Tickets are bought only through lawful provincial channels; the platform
     sells no chances to the public and runs no lottery scheme. All participants must
     meet the age and eligibility rules for their province.

IMPORTANT NOTES
This agreement is practical information and record-keeping, not legal advice. Lottery
rules can change; for a large win, check the current provincial lottery corporation
requirements before making any claim, and consider independent legal and tax advice.
In Canada, lottery winnings are generally not taxable as income, though income later
earned from investing winnings can be taxable.

PRIVACY STATEMENT
Your personal information is collected in accordance with the Freedom of Information
and Protection of Privacy Act, British Columbia, and will be used by BCLC to administer
and process lottery prizes (including verifying prize claims and fraud investigations);
if you are a winner, publication of details for game integrity purposes; and to comply
with applicable laws.

Questions: BCLC Customer Support, 74 West Seymour Street, Kamloops, BC V2C 1E2 -
1-866-815-0222 - bclc.com

SIGNATURES & DECLARATIONS
Group Trustee: {t["name"]}

Beneficiary: {beneficiary_name}
Digitally signed via LottoChee / Telegram - {signed_date}
Declaration: {decl}

- LottoChee - BC, Canada
"""


def build_group_play_body(*, round_id: int, trustee_name: str) -> str:
    return f"""GROUP PLAY TERMS
This form records the paid members of the pool for Round #{round_id} and each
member's share, for reference alongside the Group Prize Agreement with Group
Trustee {trustee_name}.

  - No pay, no share: a member is included only if full payment was recorded by
    the cut-off before tickets were purchased. The list above is the paid
    membership for this round.
  - The Group Trustee holds the pooled ticket(s) "In Trust" for all members; only
    the original ticket may claim a prize. Winnings are paid to the Trustee as
    trustee and distributed to members strictly by the pool shares shown.
  - Group claims of $10,000 CAD or more require a Group Prize Agreement completed
    by every member entitled to a share, with valid government-issued photo ID.

This document is practical information and record-keeping, not legal advice.

- LottoChee - Round #{round_id} - Trustee: {trustee_name}
"""


def round_ticket_control(round_id: int) -> str:
    """Stable internal control reference LottoChee assigns to a round's ticket."""
    return f"LC-R{int(round_id):05d}"


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
    trustee: dict | None = None,
    participants_count: int | None = None,
    ticket_numbers: str | None = None,
    ticket_control: str | None = None,
) -> str:
    """Per-round draw agreement (amendment) + draw-by-draw proof of ownership.

    Mirrors the BCLC LOTTO MAX group-play safeguards: it records the paid
    participant list locked at the cut-off, the "no pay, no share" rule, ticket
    proof and custody, and the prize-claim / payout terms for this specific draw.
    """
    t = trustee or DEFAULT_TRUSTEE
    pct_line = f"{share_pct}%" if share_pct is not None else "-"
    control = ticket_control or round_ticket_control(round_id)
    closed_line = (
        f"  Entries closed (cut-off): {closed_at}\n" if closed_at
        else "  Entries closed (cut-off): at 1 day before the draw\n"
    )
    paid_line = (
        f"  Paid beneficiaries:  {participants_count}\n" if participants_count is not None else ""
    )
    ticket_block = (
        f"TICKET PROOF\n"
        f"  Ticket control no.:  {control}\n"
        f"  Group ticket status: Held \"In Trust\" for the group by the Group Trustee\n"
        + (f"  Ticket numbers:      {ticket_numbers}\n" if ticket_numbers else "")
        + "  A copy of the purchased ticket is provided to beneficiaries. Only the\n"
          "  original ticket, held by the Group Trustee, may be used to claim a prize.\n\n"
    )
    return f"""ROUND DRAW AGREEMENT (AMENDMENT)
Round #{round_id}

This amendment supplements the Group Prize Agreement between you and Group Trustee
{t["name"]}. In case of conflict on this round only, this amendment controls for
Round #{round_id}. It also serves as the draw-by-draw record of who paid, which
ticket was bought, and the share each beneficiary owns for this draw.

ROUND DETAILS
  Game:      {lottery_label(lottery_type)}
  Draw date: {draw_date or "TBD"}
{closed_line}  Ticket control no.: {control}

YOUR PARTICIPATION
  Beneficiary: {beneficiary_name}
  Shares:      {shares}
  Stake:       ${stake_amount:.2f} CAD
  Pool share:  {pct_line} of round pool (${pool_amount:.2f} CAD total)

PAID PARTICIPANT LIST (LOCKED AT CUT-OFF)
{paid_line}  The final paid participant list and share allocation recorded at the cut-off
  determine ownership of the ticket(s) purchased for this draw. The list is locked
  at the cut-off and preserved as the record for Round #{round_id}.

{ticket_block}NO PAY, NO SHARE
  A participant is included in this draw only if full payment was received and
  recorded before the posted cut-off time. Late payment, partial payment, verbal
  promises, or past participation do not create a share in this draw unless the
  written Group Prize Agreement says otherwise.

PRIZE CLAIM & PAYOUT
  Any prize is paid to the Group Trustee ({t["name"]}) as trustee only, and never
  in the Trustee's personal capacity. The Trustee distributes winnings to
  beneficiaries strictly by the pool shares recorded above, using a traceable
  account, with a written payout confirmation to each beneficiary. Group claims of
  $10,000 CAD or more require a Group Prize Agreement completed by every member
  entitled to a share, with valid government-issued photo ID.

IMPORTANT NOTES
  This document is practical information and record-keeping, not legal advice.
  Lottery rules can change; for a large win the Trustee and beneficiaries should
  check the current provincial lottery corporation requirements and consider
  independent legal and tax advice before any claim or distribution. In Canada,
  lottery winnings are generally not taxable as income, though income later earned
  from investing winnings can be taxable.

By participating in this round you confirm you have read the Group Prize Agreement
and accept this round-specific share for the draw listed above.

- Round #{round_id} - Ticket {control} - Trustee: {t["name"]}
"""
