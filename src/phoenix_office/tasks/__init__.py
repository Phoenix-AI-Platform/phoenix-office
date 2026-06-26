"""Phoenix Core task envelope factories."""

from phoenix_office.tasks.proposals import (
    PROPOSAL_GENERATION_CAPABILITY_ID,
    create_proposal_generation_task_envelope,
)

__all__ = [
    "PROPOSAL_GENERATION_CAPABILITY_ID",
    "create_proposal_generation_task_envelope",
]
