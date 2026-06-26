"""Interactive proposal intake helpers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation

from phoenix_office.models.proposal import PricingLine, ProposalInput, ScopeItem

Prompt = Callable[[str], str]

TANK_SIZE_PRESETS = ("275", "500", "550", "1000")
PRICING_NOTE_PRESETS = (
    "Additional charges may apply if contents are discovered in the tank.",
    "Additional charges may apply if concrete, obstructions, or unusual access conditions are encountered.",
    "Starting at price based on information provided prior to inspection.",
)
OPTIONAL_NOTE_PRESETS = (
    "Payment due upon completion.",
    "Customer is responsible for access to the tank area.",
    "Price assumes normal access and working conditions.",
)


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
    proposal_date = _prompt_date(
        prompt,
        f"Proposal date [{default_date.isoformat()}]: ",
        default_date,
    )
    tank_size = _prompt_tank_size(prompt)
    tank_type = _prompt_choice(prompt, "Tank type (AST/UST): ", {"AST", "UST"})
    contents_status = _prompt_choice(
        prompt,
        "Contents known or unknown (known/unknown): ",
        {"known", "unknown"},
    )
    pricing_type = _prompt_choice(
        prompt,
        "Pricing type (fixed/starting-at): ",
        {"fixed", "starting-at"},
    )
    price = _prompt_decimal(prompt, "Price: ")
    pricing_note = _prompt_preset_or_custom(
        prompt,
        "Pricing note",
        PRICING_NOTE_PRESETS,
    )
    note = _prompt_preset_or_custom(prompt, "Notes", OPTIONAL_NOTE_PRESETS)

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


def _prompt_choice(prompt: Prompt, message: str, choices: set[str]) -> str:
    normalized_choices = {choice.lower(): choice for choice in choices}
    while True:
        value = prompt(message).strip().lower()
        if value in normalized_choices:
            return normalized_choices[value]
        print(f"Please enter one of: {', '.join(sorted(choices))}.")


def _prompt_tank_size(prompt: Prompt) -> str:
    value = _prompt_required(
        prompt,
        f"Tank size (gallons) [{'/'.join(TANK_SIZE_PRESETS)} or custom]: ",
    )
    preset_by_number = {str(idx): preset for idx, preset in enumerate(TANK_SIZE_PRESETS, start=1)}
    return preset_by_number.get(value, value)


def _prompt_preset_or_custom(prompt: Prompt, label: str, presets: tuple[str, ...]) -> str:
    print(f"{label}:")
    for idx, preset in enumerate(presets, start=1):
        print(f"  {idx}. {preset}")

    value = prompt("Enter for none, number for preset, or type custom note: ").strip()
    if not value:
        return ""

    preset_by_number = {str(idx): preset for idx, preset in enumerate(presets, start=1)}
    return preset_by_number.get(value, value)


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
