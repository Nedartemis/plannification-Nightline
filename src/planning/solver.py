from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Union

import numpy as np
import pandas as pd
import pulp

from planning.parameters import GapModality, GoalModality, PlanningParameters
from planning.planning_struct import EventType, Language, Planning


class SolverStatus(Enum):
    UNBOUNDED = -2
    INFEASIBLE = -1
    SUCESS = 1


def define_variables_array(label: str, n: int) -> np.ndarray:
    return np.array(
        [pulp.LpVariable(f"{label}_{idx}", cat=pulp.LpBinary) for idx in range(n)]
    )


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
    planning_availabilities: Planning,
    parameters: PlanningParameters,
    verbose: bool = True,
) -> Planning:

    # Constants
    events = planning_availabilities.events
    persons_infos = planning_availabilities.persons_infos
    availabilities = planning_availabilities.availabilities

    number_persons = len(persons_infos)
    dates = np.sort(events["date"])
    number_dates = len(dates)
    # dates_last_shift = persons_infos["date_last_shift"]
    did_gap_last_month = persons_infos["did_gap_last_month"]
    # is_new = persons_infos["is_new"]

    date_to_date_idx: Dict[datetime, int] = dict(zip(dates, range(number_dates)))
    person_name_to_person_idx: Dict[str, int] = dict(
        zip(persons_infos["name"], range(number_persons))
    )
    persons_name: List[str] = list(persons_infos["name"])

    BIG_NUMBER = 100

    # Variables
    shifts = define_variables_matrix("shift", number_persons, number_dates)
    gaps = define_variables_matrix("gap", number_persons, number_dates)
    screenings = define_variables_matrix("scrennings", number_persons, number_dates)
    references = define_variables_matrix("referencce", number_persons, number_dates)

    open_shifts = define_variables_array("open_shifts", n=number_dates)
    open_gaps = define_variables_array("open_gaps", n=number_dates)

    event_type_to_variables: Dict[EventType, np.ndarray] = {
        EventType.SHIFT: shifts,
        EventType.GAP_FRANCO: gaps,
        EventType.GAP_BILINGUAL: None,
        EventType.SCRENNINGS: screenings,
    }

    # model
    solver = pulp.LpProblem("pulp", pulp.LpMaximize)

    # Rules

    # -- Events openess

    # not open events
    for event_type, variables in event_type_to_variables.items():
        if variables is None:
            continue
        for date, opened in zip(events["date"], events[event_type.value]):
            if not opened:
                date_idx = date_to_date_idx[date]

                # close for the varible link to event
                for person_idx in range(number_dates):
                    solver += (
                        variables[person_idx, date_idx] == 0,
                        f"not_open_event_{event_type}_{person_idx}_{date_idx}",
                    )
                    # if person_idx == 0 and event_type == EventType.GAP_FRANCO:
                    #     print(open_gaps[date_idx] == 0)

                # special case for open shift
                if event_type == EventType.SHIFT:
                    solver += open_shifts[date_idx] == 0
                elif event_type == EventType.GAP_FRANCO:
                    solver += open_gaps[date_idx] == 0

    # -- Availabilities

    # not available --> shift|gaps|screenings = 0
    for _, row in availabilities.iterrows():
        if not row["available"]:
            person_idx = person_name_to_person_idx[row["person_name"]]
            date_idx = date_to_date_idx[row["date"]]
            event_type = row["event_type"]
            variables = event_type_to_variables[event_type]
            if variables is None:
                continue
            # print(person_idx, date_idx)
            # print(variables)

            solver += (
                variables[person_idx, date_idx] == 0,
                f"not available_{event_type}_{person_idx}_{date_idx}",
            )
            # if person_idx == 0 and row["event_type"] == EventType.GAP_FRANCO:
            #     print(variables[person_idx, date_idx] == 0)

    # -- Shift rules

    if True:
        # max number of shifts per month
        for person_idx in range(number_persons):
            solver += (
                pulp.lpSum(shifts[person_idx, :])
                <= parameters.max_number_shift_per_month
            )

        # a shift is neither open (nb person >= 3) or close (nb == 0)
        for date_idx in range(number_dates):
            nb_person_on_a_day = pulp.lpSum(shifts[:, date_idx])

            # disjuntive case thanks to BIG_NUMBER
            solver += nb_person_on_a_day <= 0 + BIG_NUMBER * open_shifts[date_idx]
            solver += (
                nb_person_on_a_day
                >= parameters.min_number_person_per_shift
                - BIG_NUMBER * (1 - open_shifts[date_idx])
            )

        # no 2 shifts consecutively under an amount of days
        for person_idx in range(number_persons):
            for date_idx in range(
                number_dates - parameters.min_number_days_between_two_shifts + 1
            ):
                vars = shifts[
                    person_idx,
                    range(
                        date_idx,
                        date_idx + parameters.min_number_days_between_two_shifts,
                    ),
                ]
                solver += pulp.lpSum(vars) <= 1

    # -- Reference

    if True:
        # max number reference per person per month
        for person_idx in range(number_persons):
            solver += pulp.lpSum(references[person_idx, :]) <= 1

        # no reference for new person
        for person_idx in range(number_persons):
            if persons_infos["is_new"].iloc[person_idx]:
                for date_idx in range(number_dates):
                    solver += references[person_idx, date_idx] == 0

        # max one referent per shift
        for date_idx in range(number_dates):
            solver += (
                pulp.lpSum(references[:, date_idx])
                <= parameters.exact_number_referent_per_perm
            )

        # at least the good number of referent in an open shift
        for date_idx in range(number_dates):
            nb_referent_on_a_day = pulp.lpSum(references[:, date_idx])

            # disjuntive case thanks to BIG_NUMBER
            solver += nb_referent_on_a_day <= 0 + BIG_NUMBER * open_shifts[date_idx]
            solver += (
                nb_referent_on_a_day
                >= parameters.exact_number_referent_per_perm
                - BIG_NUMBER * (1 - open_shifts[date_idx])
            )

        # you are referent --> you have a shift
        for person_idx in range(number_persons):
            for date_idx in range(number_dates):
                solver += (
                    shifts[person_idx, date_idx] >= references[person_idx, date_idx]
                )

    # -- GAP

    if True:
        # max one GAP per person per month
        for person_idx in range(number_persons):
            solver += pulp.lpSum(gaps[person_idx, :]) <= 1

        # max and min number person in a GAP
        for date_idx in range(number_dates):
            s = pulp.lpSum(gaps[:, date_idx])

            # max
            solver += s <= parameters.max_number_person_gap

            # min on open gaps
            solver += s <= 0 + BIG_NUMBER * open_gaps[date_idx]
            solver += s >= parameters.min_number_person_gap - BIG_NUMBER * (
                1 - open_gaps[date_idx]
            )

        # modality gap
        if parameters.gap_modality == GapModality.MONTH:
            # no gap before the shifts (last month or before in the same month) --> no shifts
            for person_idx in range(number_persons):
                if not did_gap_last_month.iloc[person_idx]:
                    for day_idx in range(number_dates):
                        total_gap_done = pulp.lpSum(gaps[person_idx, :day_idx])
                        solver += shifts[person_idx, day_idx] <= total_gap_done
        else:
            raise ValueError(f"Gap modality '{parameters.gap_modality}' not handled.")

    # goal
    number_person_shift = pulp.lpSum(shifts[:, :])
    number_open_shift = pulp.lpSum(open_shifts[:])
    if parameters.goal_modality == GoalModality.OPEN_SHIFT_PRIORITY:
        solver += number_open_shift * 1000 + number_person_shift
    elif parameters.goal_modality == GoalModality.NUMBER_PERSON_SHIFT_PRIORITY:
        solver += number_person_shift * 1000 + number_open_shift
    else:
        raise ValueError(f"Goal modality '{parameters.goal_modality}' not handled.")

    # solve
    solver.solve(pulp.PULP_CBC_CMD(msg=0))
    print("------------")
    if solver.status == SolverStatus.INFEASIBLE.value:
        raise RuntimeError("Infeasible planning")
    elif solver.status == SolverStatus.UNBOUNDED.value:
        raise RuntimeError("Unbounded problem")
    elif solver.status == SolverStatus.SUCESS.value:
        print("Sucess")
    else:
        raise RuntimeError(f"Not handled status : {solver.status}")
    print("------------")

    # convert the results
    data = []

    def add_data(
        person_idx: int,
        date_idx: int,
        event_type: EventType,
        assignation: Union[bool, str],
    ) -> None:
        obj = {
            "person_name": persons_name[person_idx],
            "date": dates[date_idx],
            "event_type": event_type,
            "assignation": assignation,
        }
        data.append(obj)

    # events
    for event_type, variables in event_type_to_variables.items():
        if variables is None:
            continue
        # print(event_type)
        for person_idx, lst in enumerate(variables):
            for date_idx, assigned in enumerate(lst):
                add_data(person_idx, date_idx, event_type, bool(assigned.value()))

    assignations = pd.DataFrame(data)
    assignations["assignation"] = assignations["assignation"].astype(object)

    # reference
    for person_idx, lst in enumerate(references):
        for date_idx, is_referent in enumerate(lst):
            person_name = persons_name[person_idx]
            date = dates[date_idx]

            if bool(is_referent.value()):
                # erase the True by "ref"
                assignations.loc[
                    (assignations["person_name"] == person_name)
                    & (assignations["date"] == date)
                    & (assignations["event_type"] == EventType.SHIFT),
                    "assignation",
                ] = "ref"

    # os = [e.value() for e in open_shifts]
    # print(len(os), os)

    name = persons_infos.iloc[0]["name"]
    # print(name)
    # print(
    #     availabilities[
    #         (availabilities["person_name"] == name)
    #         & (availabilities["event_type"] == EventType.GAP_FRANCO)
    #     ]
    # )
    # print(
    #     assignations[
    #         (assignations["person_name"] == name)
    #         & (assignations["event_type"] == EventType.GAP_FRANCO)
    #     ]
    # )
    # print(
    #     assignations[
    #         (assignations["event_type"] == EventType.GAP_FRANCO)
    #         & (assignations["assigned"] == True)
    #     ]
    # )
    # for name, c in solver.constraints.items():
    #     if "gap_0" in str(c):
    #         print(name, c)

    # return
    return Planning(
        events=planning_availabilities.events,
        persons_infos=planning_availabilities.persons_infos,
        availabilities=availabilities,
        assignations=assignations,
    )


if __name__ == "__main__":
    from planning.parameters import DEFAULT_PARAMETERS
    from planning.planning_reader import read_planning
    from vars import PATH_DOCS_PLANNING_MAY

    print("Reading planning...")
    planning = read_planning(PATH_DOCS_PLANNING_MAY)
    print("Solving planning...")
    solve_planning(planning_availabilities=planning, parameters=DEFAULT_PARAMETERS)
