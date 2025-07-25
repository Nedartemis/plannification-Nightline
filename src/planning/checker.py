from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from functools import reduce
from typing import Any, Callable, List, Optional, Tuple, Union

import pandas as pd

from planning.parameters import GapModality, PlanningParameters
from planning.planning_struct import EventType, Planning

TYPE_PLANNING_ASSIGNATION_CHECKS = List[Tuple[List[str], str]]


@dataclass
class BinCond:
    label: str
    op: Callable[[Any, Any], bool]


class BinConds(Enum):
    INFERIOR = BinCond("<", lambda a, b: a < b)
    INFERIOR_EQUAL = BinCond("<=", lambda a, b: a <= b)
    SUPERIOR = BinCond(">", lambda a, b: a > b)
    SUPERIOR_EQUAL = BinCond(">=", lambda a, b: a >= b)
    EQUAL = BinCond("=", lambda a, b: a == b)
    NOT_EQUAL = BinCond("not equal to", lambda a, b: a != b)


def fd(date: datetime) -> str:
    return date.strftime("%d/%m")


class PlanningAssignationChecksBuilder:
    obj: TYPE_PLANNING_ASSIGNATION_CHECKS

    def __init__(self):
        self.obj = []
        self.titles = []

    def set_title(self, title: str) -> None:
        self.titles = [title]

    def set_sub_title(self, sub_title: str) -> None:
        assert len(self.titles) >= 1
        self.titles = self.titles[:1]
        self.titles.append(sub_title)

    def add(self, detail: str) -> None:
        self.obj.append((self.titles, detail))

    def add_cond(self, label: str, a: Any, bin_cond: BinConds, b: Any):
        str_a = fd(a) if isinstance(a, datetime) else a
        str_b = fd(b) if isinstance(b, datetime) else b
        if bin_cond.value.op(a, b):
            self.add(
                f"{label} : '{str_a}' {bin_cond.value.label} '{str_b}'",
            )

    def add_date_cond(
        self, date: datetime, label: str, a: Any, bin_cond: BinConds, b: Any
    ):
        self.add_cond(f"On '{fd(date)}' {label}", a, bin_cond, b)

    def add_person_cond(
        self, person_name, label: str, a: Any, bin_cond: BinConds, b: Any
    ) -> None:
        self.add_cond(f"'{person_name}' {label}", a, bin_cond, b)

    def get(self) -> TYPE_PLANNING_ASSIGNATION_CHECKS:
        return self.obj


def filter_pl(
    planning: pd.DataFrame,
    assignation: bool,
    person_name: Optional[str] = None,
    date: Optional[datetime] = None,
    event_type: Optional[EventType] = None,
    is_referent: bool = False,
) -> pd.DataFrame:
    label = "assignation" if assignation else "available"

    conds = []
    if person_name is not None:
        conds.append(planning["person_name"] == person_name)
    if date is not None:
        conds.append(planning["date"] == date)
    if event_type is not None:
        conds.append(planning["event_type"] == event_type)
    if is_referent:
        conds.append(planning[label] == "ref")

    conds.append(planning[label].astype(bool) == True)

    return planning[reduce(lambda a, b: a & b, conds)]


def filter_as(
    planning: pd.DataFrame,
    person_name: Optional[str] = None,
    date: Optional[datetime] = None,
    event_type: Optional[EventType] = None,
    is_referent: bool = False,
):
    return filter_pl(
        planning=planning,
        assignation=True,
        person_name=person_name,
        date=date,
        event_type=event_type,
        is_referent=is_referent,
    )


def count_as(
    planning: pd.DataFrame,
    person_name: Optional[str] = None,
    date: Optional[datetime] = None,
    event_type: Optional[EventType] = None,
    is_referent: bool = False,
) -> pd.DataFrame:
    return len(filter_pl(planning, True, person_name, date, event_type, is_referent))


def check_planning_assignation(
    planning_assignation: Planning, planning_parameters: PlanningParameters
) -> TYPE_PLANNING_ASSIGNATION_CHECKS:

    pa = planning_assignation
    events = pa.events
    dates = events["date"].sort_values()
    person_infos = pa.persons_infos
    person_infos_index_by_name = person_infos.set_index("name")
    persons_name = person_infos["name"]
    availabitilites = pa.availabilities
    assignation = pa.assignations
    assert assignation is not None
    date_open_shifts = (
        assignation[
            (assignation["assignation"].astype(bool) == True)
            & (assignation["event_type"] == EventType.SHIFT)
        ]["date"]
        .sort_values()
        .unique()
    )
    params = planning_parameters

    checks = PlanningAssignationChecksBuilder()

    # -- Availabilities
    if availabitilites is not None:
        checks.set_title("availibilities")

        for _, row in assignation[
            assignation["assignation"].astype(bool) == True
        ].iterrows():
            person_name, date, event_type = (
                row["person_name"],
                row["date"],
                row["event_type"],
            )
            n = len(
                filter_pl(
                    availabitilites,
                    assignation=False,
                    person_name=person_name,
                    date=date,
                    event_type=event_type,
                )
            )
            if n == 0:
                checks.add(
                    f"'{person_name}' on '{date}' for the '{event_type.value}' is not available but has been assigned to it."
                )

    # -- shift rules
    checks.set_title("shift_rules")

    checks.set_sub_title("max_shift_per_person_per_month")
    for person_name in persons_name:
        n = count_as(assignation, person_name=person_name, event_type=EventType.SHIFT)
        checks.add_person_cond(
            person_name=person_name,
            label="has too many shift on the month",
            a=n,
            bin_cond=BinConds.SUPERIOR,
            b=params.max_number_shift_per_month,
        )

    checks.set_sub_title("min_per_shift_open")
    for date in dates:
        n = count_as(assignation, date=date, event_type=EventType.SHIFT)
        if n == 0 or n >= params.min_number_person_per_shift:
            continue
        checks.add(
            f"On '{date}' the number of person is anormal on the shift : 0 < '{n}' < '{params.min_number_person_per_shift}'",
        )

    checks.set_sub_title("max_person_per_shift")
    for person_name in persons_name:
        pl = filter_as(assignation, person_name=person_name, event_type=EventType.SHIFT)
        pl = pl.sort_values("date")
        for idx in range(len(pl) - 1):
            d1: datetime = pl.iloc[idx]["date"]
            d2: datetime = pl.iloc[idx + 1]["date"]
            if (d2 - d1).days < params.min_number_days_between_two_shifts:
                checks.add(
                    f"'{person_name}' has two shifts too close : "
                    f"difference between '{fd(d1)}' and '{fd(d2)}' < '{params.min_number_days_between_two_shifts}'",
                )

    # -- ref rules
    checks.set_title("reference_rules")

    checks.set_sub_title("max_number_reference_per_person_per_month")
    for person_name in persons_name:
        n = count_as(assignation, person_name=person_name, is_referent=True)
        checks.add_person_cond(
            person_name=person_name,
            label="has too many references",
            a=n,
            bin_cond=BinConds.SUPERIOR,
            b=params.max_number_reference_per_person_per_month,
        )

    checks.set_sub_title("no_reference_for_babies")
    for person_name in person_infos[person_infos["is_new"] == True]["name"]:
        n = count_as(assignation, person_name=person_name, is_referent=True)
        if n > 0:
            checks.add(f"'{person_name}' is a baby but has a reference.")

    checks.set_sub_title("exact_number_referent_per_open_shift")
    for date in date_open_shifts:
        n = count_as(assignation, date=date, is_referent=True)
        checks.add_date_cond(
            date,
            label="there is not the good number of referent in an open shift",
            a=n,
            bin_cond=BinConds.NOT_EQUAL,
            b=params.exact_number_referent_per_perm,
        )

    # -- gap rules
    checks.set_title("gap_rules")

    gaps_date = events[events[EventType.GAP_FRANCO.value] == True]["date"]
    gaps_date = gaps_date.sort_values()

    checks.set_sub_title("max_number_person_in_gap")
    for date in gaps_date:
        n = count_as(assignation, date=date, event_type=EventType.GAP_FRANCO)
        checks.add_date_cond(
            date=date,
            label="there are too many persons on the gap",
            a=n,
            bin_cond=BinConds.SUPERIOR,
            b=params.max_number_person_gap,
        )

    checks.set_sub_title("min_number_person_in_gap")
    for date in gaps_date:
        n = count_as(assignation, date=date, event_type=EventType.GAP_FRANCO)
        checks.add_date_cond(
            date=date,
            label="there are too few persons on the gap",
            a=n,
            bin_cond=BinConds.SUPERIOR,
            b=params.min_number_person_gap,
        )

    checks.set_sub_title("no_shift_if_no_gap_before")
    if params.gap_modality == GapModality.MONTH:
        for person_name in persons_name:
            if person_infos_index_by_name.loc[person_name, "did_gap_last_month"]:
                continue

            date_first_gap = filter_as(
                assignation, person_name=person_name, event_type=EventType.GAP_FRANCO
            )["date"].min()

            shifts = filter_as(
                assignation, person_name=person_name, event_type=EventType.SHIFT
            )
            for shift in shifts:
                checks.add_person_cond(
                    person_name=person_name,
                    label="did not do a GAP last month and has a shift before its gap",
                    a=shift["date"],
                    bin_cond=BinConds.INFERIOR,
                    b=date_first_gap,
                )
    elif params.gap_modality == GapModality.SHIFTS:
        raise ValueError("Cheks on GapModality.SHIFTS has not been made.")

    return checks.get()


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
    params.min_number_days_between_two_shifts = 8
    res = check_planning_assignation(pl_assign, params)
    # print(res)
