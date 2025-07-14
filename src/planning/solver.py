from datetime import datetime
from typing import Dict

import numpy as np
import pulp

from planning.parameters import PlanningParameters
from planning.planning_struct import EventType, Language, Planning


def define_variables_array(label: str, n: int) -> np.ndarray:
    return np.array([pulp.LpVariable(f"{label}_{idx}") for idx in range(n)])


def define_variables_matrix(label: str, nrows: int, ncols: int) -> np.ndarray:
    return np.array(
        [
            [
                pulp.LpVariable(f"{label}_{row_idx}_{col_idx}", cat=pulp.LpBinary)
                for col_idx in range(ncols)
            ]
            for row_idx in range(nrows)
        ]
    )


def solve_planning(
    planning_availabilities: Planning, parameters: PlanningParameters
) -> Planning:

    # Constants
    events = planning_availabilities.events
    persons_infos = planning_availabilities.persons_infos
    availabilities = planning_availabilities.availabilities

    number_persons = len(persons_infos)
    dates = np.sort(events["date"])
    number_days = len(dates)
    # dates_last_shift = persons_infos["date_last_shift"]
    # did_gap_last_month = [True] * number_persons
    # is_new = persons_infos["is_new"]

    date_to_date_idx: Dict[datetime, int] = dict(zip(dates, range(number_days)))
    person_name_to_person_idx: Dict[str, int] = dict(
        zip(persons_infos["name"], range(number_persons))
    )

    BIG_NUMBER = 100

    # Variables
    shifts = define_variables_matrix("shift", number_persons, number_days)
    gaps = define_variables_matrix("gap", number_persons, number_days)
    screenings = define_variables_matrix("scrennings", number_persons, number_days)
    references = define_variables_matrix("referencce", number_persons, number_days)
    open_shift = define_variables_array("open_shift", n=number_days)

    event_type_to_variables: Dict[EventType, np.ndarray] = {
        EventType.SHIFT: shifts,
        EventType.GAP_FRANCO: gaps,
        EventType.GAP_BILINGUAL: gaps,
        EventType.SCRENNINGS: screenings,
    }

    # model
    solver = pulp.LpProblem("pulp", pulp.LpMaximize)

    # Rules

    # -- events

    # not open events
    for event_type, variables in event_type_to_variables.items():
        for date, opened in zip(events["date"], events[event_type.value]):
            if not opened:
                date_idx = date_to_date_idx[date]

                # close for the varible link to event
                for person_idx in range(number_days):
                    solver += variables[person_idx, date_idx] == 0

                # special case for open event
                if event_type == EventType.SHIFT:
                    solver += open_shift[date_idx] == 0

    # not available --> shift|gaps|references = 0
    for _, row in availabilities.iterrows():
        if not row["available"]:
            person_idx = person_name_to_person_idx[row["person_name"]]
            date_idx = date_to_date_idx[row["date"]]
            variables = event_type_to_variables[row["event_type"]]
            # print(person_idx, date_idx)
            # print(variables)

            solver += variables[person_idx, date_idx] == 0

    # -- Shift

    # max number of shifts per month
    for person_idx in range(number_persons):
        solver += (
            pulp.lpSum(shifts[person_idx, :]) <= parameters.max_number_shift_per_month
        )

    # a shift is neither open (nb person >= 3) or close (nb == 0)
    for date_idx in range(number_days):
        nb_person_on_a_day = pulp.lpSum(shifts[:, date_idx])
        # disjuntive case thanks to BIG_NUMBER

        solver += nb_person_on_a_day <= 0 + BIG_NUMBER * open_shift[date_idx]
        solver += (
            nb_person_on_a_day
            >= parameters.min_number_person_per_shift
            - BIG_NUMBER * (1 - open_shift[date_idx])
        )

    # no 2 shifts consecutively under an amount of days
    for person_idx in range(number_persons):
        for date_idx in range(
            number_days - parameters.min_number_days_between_two_shifts
        ):
            vars = shifts[
                person_idx,
                range(
                    date_idx, date_idx + parameters.min_number_days_between_two_shifts
                ),
            ]
            solver += pulp.lpSum(vars) <= 1

    # -- Reference

    # max number reference per person per month
    for person_idx in range(number_persons):
        solver += pulp.lpSum(references[person_idx, :]) <= 1

    # no reference for new person
    for person_idx in range(number_persons):
        if persons_infos["is_new"].iloc[person_idx]:
            for date_idx in range(number_days):
                solver += references[person_idx, date_idx] == 0

    # -- GAP

    # goal
    solver += pulp.lpSum(shifts[:, :])

    # solve
    solver.solve()
    vars = [var.value() for var in shifts[0, :]]
    name = persons_infos.index[0]
    print(name)
    print(
        availabilities[
            (availabilities["person_name"] == name)
            & (availabilities["event_type"] == EventType.SHIFT)
        ]
    )
    print(vars)

    # return
    return Planning(
        events=planning_availabilities.events,
        persons_infos=planning_availabilities.persons_infos,
        availabilities=None,
    )


if __name__ == "__main__":
    from planning.parameters import DEFAULT_PARAMETERS
    from planning.planning_reader import read_planning
    from vars import PATH_DOCS_PLANNING_MAY

    print("Reading planning...")
    planning = read_planning(PATH_DOCS_PLANNING_MAY)
    print("Solving planning...")
    solve_planning(planning_availabilities=planning, parameters=DEFAULT_PARAMETERS)
