from dataclasses import dataclass


@dataclass
class PlanningParameters:
    max_number_person_gap: int
    max_number_shift_per_month: int
    min_number_person_per_shift: int
    min_number_days_between_two_shifts: int
    max_number_reference_per_personn: int


DEFAULT_PARAMETERS = PlanningParameters(
    max_number_person_gap=10,
    max_number_shift_per_month=3,
    min_number_person_per_shift=3,
    min_number_days_between_two_shifts=6,
    max_number_reference_per_personn=1,
)
