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
            "  The Beneficiaries acknowledge and agree that Lotto Chee may claim a service fee\n"
            "  of five percent (5%) of any single Prize exceeding $1,000.00 CAD, deducted from\n"
            "  that Prize before the remainder is distributed to the Beneficiaries by share."
        )
    else:
        plan_clause = (
            "PLATFORM SERVICE PLAN\n"
            "  This group is on the Monthly Subscription plan, chosen by the Group Trustee when\n"
            "  the group was created and fixed for the life of the group. The Group Trustee pays\n"
            "  Lotto Chee a service fee of $6.99 CAD per month. Lotto Chee claims no share of\n"
            "  any Prize won by the group."
        )
    ben_address = _format_address(
        beneficiary_street, beneficiary_city, beneficiary_province, beneficiary_postal
    )
    trustee_address = _format_address(
        t["street"], t["city"], t["province"], None
    )
    decl = declaration_category_label(declaration_category)
    signed_date = accepted_at[:10] if accepted_at and len(accepted_at) >= 10 else "See Lotto Chee account"

    return f"""GROUP PRIZE AGREEMENT
(BCLC Group Release Form - Lotto Chee)

This Group Prize Agreement is required when a group lottery ticket wins a prize of
$1,000.00 CAD or greater and must be completed by all group members entitled to a
share of the prize won. Lotto Chee uses this agreement for pooled play and registers
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
  Ticket control number:  Assigned by Lotto Chee per round when the ticket is purchased

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
Digitally signed via Lotto Chee / Telegram - {signed_date}
Declaration: {decl}

- Lotto Chee - BC, Canada
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
    trustee: dict | None = None,
) -> str:
    t = trustee or DEFAULT_TRUSTEE
    pct_line = f"{share_pct}%" if share_pct is not None else "-"
    closed_line = f"Entries closed: {closed_at}\n" if closed_at else ""
    return f"""ROUND DRAW AGREEMENT (AMENDMENT)
Round #{round_id}

This amendment supplements the Group Prize Agreement between you and Group Trustee
{t["name"]}. In case of conflict on this round only, this amendment controls for
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

By participating in this round you confirm you have read the Group Prize Agreement
and accept this round-specific share for the draw listed above.

- Round #{round_id} - Trustee: {t["name"]}
"""
