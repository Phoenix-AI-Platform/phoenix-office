"""Interactive proposal intake helpers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation

from phoenix_office.models.proposal import PricingLine, ProposalInput, ScopeItem

Prompt = Callable[[str], str]


def collect_proposal_input(
    prompt: Prompt | None = None,
    *,
    today: date | None = None,
) -> ProposalInput:
    """Collect A-1 proposal details from prompt answers."""
    prompt = prompt or input
    default_date = today or date.today()

    customer_name = _prompt_required(prompt, "Customer name: ")
    street_address = _prompt_required(prompt, "Street address: ")
    city_state_zip = _prompt_required(prompt, "City/state/zip: ")
    proposal_date = _prompt_date(prompt, f"Proposal date [{default_date.isoformat()}]: ", default_date)
    tank_size = _prompt_required(prompt, "Tank size (gallons): ")
    tank_type = _prompt_choice(prompt, "Tank type (AST/UST): ", {"AST", "UST"})
    contents_status = _prompt_choice(prompt, "Contents known or unknown (known/unknown): ", {"known", "unknown"})
    pricing_type = _prompt_choice(prompt, "Pricing type (fixed/starting-at): ", {"fixed", "starting-at"})
    price = _prompt_decimal(prompt, "Price: ")
    pricing_note = _prompt_optional(prompt, "Pricing note (optional): ")
    note = _prompt_optional(prompt, "Notes (optional): ")

    item_description = f"Removal of {tank_size} Gallon {_tank_type_description(tank_type)}"
    scope_description = _scope_description(
        tank_size=tank_size,
        tank_type=tank_type,
        street_address=street_address,
        city_state_zip=city_state_zip,
        contents_unknown=contents_status == "unknown",
    )

    return ProposalInput(
        customer_name=customer_name,
        street_address=street_address,
        city_state_zip=city_state_zip,
        proposal_date=proposal_date,
        item_description=item_description,
        scope_items=[ScopeItem(number=1, description=scope_description)],
        pricing=PricingLine(
            amount=price,
            is_starting_at=pricing_type == "starting-at",
            pricing_note=pricing_note or None,
        ),
        notes=[note] if note else [],
    )


def _prompt_required(prompt: Prompt, message: str) -> str:
    while True:
        value = prompt(message).strip()
        if value:
            return value
        print("Please enter a value.")


def _prompt_optional(prompt: Prompt, message: str) -> str:
    return prompt(message).strip()


def _prompt_choice(prompt: Prompt, message: str, choices: set[str]) -> str:
    normalized_choices = {choice.lower(): choice for choice in choices}
    while True:
        value = prompt(message).strip().lower()
        if value in normalized_choices:
            return normalized_choices[value]
        print(f"Please enter one of: {', '.join(sorted(choices))}.")


def _prompt_date(prompt: Prompt, message: str, default: date) -> date:
    while True:
        value = prompt(message).strip()
        if not value:
            return default
        try:
            return date.fromisoformat(value)
        except ValueError:
            print("Please enter a date as YYYY-MM-DD.")


def _prompt_decimal(prompt: Prompt, message: str) -> Decimal:
    while True:
        value = prompt(message).strip().replace("$", "").replace(",", "")
        try:
            amount = Decimal(value)
        except InvalidOperation:
            print("Please enter a valid price.")
            continue
        if amount > 0:
            return amount
        print("Please enter a price greater than zero.")


def _tank_type_description(tank_type: str) -> str:
    if tank_type == "AST":
        return "Aboveground Storage Tank"
    return "Underground Storage Tank"


def _scope_description(
    *,
    tank_size: str,
    tank_type: str,
    street_address: str,
    city_state_zip: str,
    contents_unknown: bool,
) -> str:
    description = (
        f"Remove one {tank_size} gallon {tank_type} tank located at "
        f"{street_address}, {city_state_zip}"
    )
    if contents_unknown:
        description = f"{description} (contents unknown)"
    return f"{description}."
