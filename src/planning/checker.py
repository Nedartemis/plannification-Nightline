from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import reduce
from typing import List, Optional, Tuple, Union

import pandas as pd

from planning.parameters import PlanningParameters
from planning.planning_struct import EventType, Planning

TYPE_PLANNING_ASSIGNATION_CHECKS = List[Tuple[List[str], List[str]]]


class PlanningAssignationChecksBuilder:
    obj: TYPE_PLANNING_ASSIGNATION_CHECKS

    def __init__(self):
        self.obj = []

    def add(self, titles: List[str], details: Union[str, List[str]]) -> None:
        if isinstance(details, str):
            details = [details]
        self.obj.extend(zip(titles, details))

    def get(self) -> TYPE_PLANNING_ASSIGNATION_CHECKS:
        return self.obj


def fd(date: datetime) -> str:
    return date.strftime("%d/%m")


def filter_pl(
    planning: pd.DataFrame, person_name: Optional[str], event_type: Optional[EventType]
) -> pd.DataFrame:
    conds = []
    if person_name:
        conds.append(planning["person_name"] == person_name)
    if event_type:
        conds.append(planning["event_type"] == event_type)

    return planning[reduce(lambda a, b: a & b, conds)]


def check_planning_assignation(
    planning_assignation: Planning, planning_parameters: PlanningParameters
) -> TYPE_PLANNING_ASSIGNATION_CHECKS:

    pa = planning_assignation
    events = pa.events
    person_infos = pa.persons_infos
    availabitilites = pa.availabilities
    assignation = pa.assignations
    parameters = planning_parameters

    pacb = PlanningAssignationChecksBuilder()

    # -- shift rules
    title = "shift_rules"

    sub_title = "max_person_per_shift"
    for person_name in person_infos["name"]:
        pl = filter_pl(assignation, person_name=person_name, event_type=EventType.SHIFT)
        pl = pl.sort_values("date")
        for idx in range(len(pl) - 1):
            d1: datetime = pl.iloc[idx]["date"]
            d2: datetime = pl.iloc[idx + 1]["date"]
            if (d2 - d1).days <= parameters.min_number_days_between_two_shifts:
                pacb.add(
                    [title, sub_title],
                    f"The person '{person_name}' has two shifts to closed : '{fd(d1)}' and '{fd(d2)}'",
                )

    return pacb.get()


if __name__ == "__main__":
    from planning.parameters import DEFAULT_PARAMETERS
    from planning.planning_reader import read_planning
    from planning.solver import solve_planning
    from vars import PATH_DOCS_PLANNING_MAY

    print("Reading planning...")
    planning = read_planning(PATH_DOCS_PLANNING_MAY)
    print("Solving planning...")
    params = DEFAULT_PARAMETERS
    pl_assign = solve_planning(
        planning_availabilities=planning, parameters=params, verbose=False
    )
    print("Check planning...")
    params.min_number_days_between_two_shifts = 4
    res = check_planning_assignation(pl_assign, params)
    print(res)
