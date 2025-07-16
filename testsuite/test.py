import pytest

from planning.checker import check_planning_assignation
from planning.parameters import DEFAULT_PARAMETERS
from planning.planning_reader import read_planning
from planning.solver import solve_planning
from vars import PATH_DOCS_PLANNING_MAY

planning = read_planning(PATH_DOCS_PLANNING_MAY)

params = DEFAULT_PARAMETERS
pl_assign = solve_planning(
    planning_availabilities=planning, parameters=params, verbose=False
)

checks = check_planning_assignation(pl_assign, params)


@pytest.mark.parametrize(
    ("error"),
    [pytest.param(detail, id="-".join(titles)) for titles, detail in checks],
)
def test_failed(error: str):
    assert error is None


@pytest.mark.parametrize(
    ("success"),
    [pytest.param("success")] if len(checks) == 0 else [],
)
def test_sucess(success: str):
    print(success)
