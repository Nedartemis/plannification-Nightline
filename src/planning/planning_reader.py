from datetime import datetime
from functools import reduce
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from helper.excel_editor import ExcelEditor
from planning.planning_struct import EventType, Language, Planning

ROW_DATES = 2
ROW_EVENT_NAME = 4
COL_SHIFT = 6

# person infos
ROW_FIRST_PERSON = 5

COL_PERSON_NEW = 0
COL_PERSON_NAME = 1
COL_PERSON_COMMENTS = 2
COL_PERSON_NUMBER_SHIFT_WANTED = 3
COL_PERSON_AGREE_TO_BE_REFERENT = 4
COL_PERSON_DATE_LAST_SHIFT = 5


# mappers
TYPE_EVENTS_NAME_MAPPER = Dict[str, EventType]
events_name_mapper: TYPE_EVENTS_NAME_MAPPER = {
    # shift
    "Shift": EventType.SHIFT,
    "Perm": EventType.SHIFT,
    # screennings
    "Screenings": EventType.SCRENNINGS,
    # GAP bilingual
    "Shared meeting\n(bilingual)": EventType.GAP_BILINGUAL,
    "GAP\n(bilingue)": EventType.GAP_BILINGUAL,
    "GAP\n(Bilingue)": EventType.GAP_BILINGUAL,
    "GAP \n(Bilingue)": EventType.GAP_BILINGUAL,
    # GAP
    "Shared meeting": EventType.GAP_FRANCO,
    "GAP": EventType.GAP_FRANCO,
    # no shift
    "No shift": EventType.NO_SHIFT,
    "Pas Perm": EventType.NO_SHIFT,
}
logos_person_is_new = {"👤": False, "🆕": True}
number_shift_wanted_mapper = {
    "Peu importe": None,
    "Pause": 0,
    None: None,
    1: 1,
    2: 2,
    3: 3,
}
agree_to_be_referent_mapper = {
    None: False,
    "ok": True,
    False: False,
    True: True,
    "non sorry": False,
    "yes": True,
    "Why not": True,
    "true": True,
    "false": False,
}
available_mapper = {None: False, False: False, True: True, "false": False, "true": True}
available_mapper = {label: not b for label, b in available_mapper.items()}


def read_page(ee: ExcelEditor, page_name: str, language: Language) -> Planning:

    page = ee.read_page(page_name)

    # store ...
    col = COL_SHIFT
    while col < page.shape[1] and page[ROW_EVENT_NAME, col] is not None:
        col += 1
    col_after_last_shift = col

    dates: List[datetime] = page[ROW_DATES, COL_SHIFT:col_after_last_shift]
    events_name: List[str] = page[ROW_EVENT_NAME, COL_SHIFT:col_after_last_shift]

    # pre-process dates
    for i in range(1, len(dates)):
        if dates[i] is None:
            dates[i] = dates[i - 1]

    # init events
    dates_unique = np.unique(dates)
    dates_unique.sort()
    data = {"date": dates_unique}
    for event in list(EventType):
        data[event.value] = [False] * len(dates_unique)
    df_events = pd.DataFrame(data=data).set_index("date")

    # fill events
    for date, event_name in zip(dates, events_name):
        event = events_name_mapper[event_name]
        df_events.loc[date, event.value] = True

    # person infos
    row = ROW_FIRST_PERSON
    while row < page.shape[0] and page[row, COL_PERSON_NAME] is not None:
        row += 1
    row_after_last_person = row

    data = [
        {
            "name": line[COL_PERSON_NAME],
            "is_new": logos_person_is_new[line[COL_PERSON_NEW]],
            "number_shift_wanted": number_shift_wanted_mapper[
                line[COL_PERSON_NUMBER_SHIFT_WANTED]
            ],
            "agree_to_be_referent": agree_to_be_referent_mapper[
                line[COL_PERSON_AGREE_TO_BE_REFERENT]
            ],
            "date_last_shift": line[COL_PERSON_DATE_LAST_SHIFT],
            "language": language,
            "comments": line[COL_PERSON_COMMENTS],
        }
        for line in page[ROW_FIRST_PERSON:row_after_last_person, :]
    ]
    df_persons_info = pd.DataFrame(data=data)

    # availabilities
    data = [
        {
            "person_name": person_name,
            "date": date,
            "event_type": events_name_mapper[event_name],
            "available": available_mapper[available],
        }
        for person_name, line in zip(
            df_persons_info["name"],
            page[
                ROW_FIRST_PERSON:row_after_last_person, COL_SHIFT:col_after_last_shift
            ],
        )
        for date, event_name, available in zip(dates, events_name, line)
    ]
    df_availabitilies = pd.DataFrame(data=data)

    # store and return
    return Planning(
        events=df_events.reset_index(),
        persons_infos=df_persons_info,
        availabilities=df_availabitilies,
    )


def read_planning(pathfile: Path) -> Planning:

    ee = ExcelEditor(path_excel=pathfile)
    # assert set(ee.get_pages_name()) == {"Franco", "Anglos", "Bilingues"}

    plannings = [
        read_page(ee, page_name, language)
        for page_name, language in {
            "Franco": Language.FRENCH_ONLY,
            "Anglos": Language.ENGLISH_ONLY,
            "Bilingues": Language.BILINGUUAL,
        }.items()
    ]

    # -- merge

    # same events
    assert all(
        (plannings[0].events == planning.events).all().all()
        for planning in plannings[1:]
    )
    events = plannings[0].events

    # merge availabilites and person infos
    person_infos = pd.concat([planning.persons_infos for planning in plannings])
    availabilities = pd.concat([planning.availabilities for planning in plannings])

    # same

    return Planning(
        events=events,
        persons_infos=person_infos,
        availabilities=availabilities,
    )


if __name__ == "__main__":
    from vars import PATH_DOCS_PLANNING_MAY

    planning = read_planning(PATH_DOCS_PLANNING_MAY)
    print(planning.persons_infos)
