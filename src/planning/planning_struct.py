from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd


class EventType(Enum):
    SHIFT = "shift"
    SCRENNINGS = "scrennings"
    GAP_FRANCO = "gap_franco"
    GAP_BILINGUAL = "gap_bilingual"
    NO_SHIFT = "no_shift"


class Language(Enum):
    FRENCH_ONLY = 1
    ENGLISH_ONLY = 2
    BILINGUUAL = 3


@dataclass
class Planning:
    events: (
        pd.DataFrame
    )  # date, perm (bool), screenings (bool), GAP franco (bool), GAP anglo (bool)
    persons_infos: (
        pd.DataFrame
    )  # person name, is new, comments, number_shift_wanted, agree_to_be_referent, date_last_shift, date_last_gap, language

    availabilities: Optional[pd.DataFrame] = None
    assignations: Optional[pd.DataFrame] = None
