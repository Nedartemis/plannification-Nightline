from dataclasses import dataclass
from enum import Enum


class GapModality(Enum):
    MONTH = 1
    SHIFTS = 2


class GoalModality(Enum):
    OPEN_SHIFT_PRIORITY = 1
    NUMBER_PERSON_SHIFT_PRIORITY = 2


@dataclass
class PlanningParameters:
    # shift rules
    max_number_shift_per_month: int
    min_number_person_per_shift: int
    min_number_days_between_two_shifts: int
    # reference rules
    max_number_reference_per_person_per_month: int
    exact_number_referent_per_perm: int
    # gap rules
    max_number_person_gap: int
    min_number_person_gap: int
    gap_modality: GapModality
    # goal
    goal_modality: GoalModality


DEFAULT_PARAMETERS = PlanningParameters(
    # shift rules
    max_number_shift_per_month=3,
    min_number_person_per_shift=3,
    min_number_days_between_two_shifts=6,
    # reference rules
    max_number_reference_per_person_per_month=1,
    exact_number_referent_per_perm=1,
    # gap rules
    max_number_person_gap=10,
    min_number_person_gap=1,
    gap_modality=GapModality.MONTH,
    # goal
    goal_modality=GoalModality.NUMBER_PERSON_SHIFT_PRIORITY,
)
