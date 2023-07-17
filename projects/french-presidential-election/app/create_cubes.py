from __future__ import annotations

import atoti as tt

from .constants import (
    Cube,
    ElectionCubeHierarchy,
    ElectionCubeLevel,
    ElectionCubeMeasure,
    LocationTableColumn,
    StateResultsTableColumn,
    StatisticsTableColumn,
    Table,
)


def create_election_cube(session: tt.Session, /) -> None:
    candidate_table = session.tables[Table.CANDIDATE_TBL.value]
    state_results_table = session.tables[Table.STATE_RESULTS_TBL.value]
    statistics_table = session.tables[Table.STATISTICS_TBL.value]
    location_table = session.tables[Table.LOCATION_TBL.value]

    cube = session.create_cube(candidate_table, Cube.ELECTION_CUBE.value)
    h, l, m = cube.hierarchies, cube.levels, cube.measures

    h[ElectionCubeHierarchy.RESULT_DATE.value].slicing = True
    l[ElectionCubeLevel.RESULT_DATE.value].order = tt.NaturalOrder(ascending=False)

    # define measures for statistics table
    m_name_stats = [
        ele
        for ele in statistics_table.columns
        if ele
        not in [
            StatisticsTableColumn.RESULT_DATE.value,
            StatisticsTableColumn.DEPARTMENT.value,
            StatisticsTableColumn.REGION.value,
        ]
    ]

    for m_name in m_name_stats:
        m[m_name] = tt.where(
            ~l[ElectionCubeLevel.REGION.value].isnull(),
            tt.agg.single_value(statistics_table[m_name]),
        )

        m[f"Total {m_name}".capitalize()] = tt.agg.sum(
            m[m_name],
            scope=tt.OriginScope(
                l[ElectionCubeLevel.REGION.value],
                l[ElectionCubeLevel.DEPARTMENT.value],
                l[ElectionCubeLevel.RESULT_DATE.value],
            ),
        )

    m.update(
        {
            ElectionCubeMeasure.NUM_DEPARTMENTS.value: tt.agg.count_distinct(
                state_results_table[StateResultsTableColumn.DEPARTMENT.value]
            ),
            ElectionCubeMeasure.NUM_REGIONS.value: tt.agg.count_distinct(
                state_results_table[StateResultsTableColumn.REGION.value]
            ),
            ElectionCubeMeasure.LONGITUDE.value: tt.where(
                ~l[StateResultsTableColumn.REGION.value].isnull(),
                tt.agg.single_value(
                    location_table[LocationTableColumn.LONGITUDE.value]
                ),
            ),
            ElectionCubeMeasure.LATITUDE.value: tt.where(
                ~l[StateResultsTableColumn.REGION.value].isnull(),
                tt.agg.single_value(location_table[LocationTableColumn.LATITUDE.value]),
            ),
            ElectionCubeMeasure.VOTES.value: tt.where(
                ~l[StateResultsTableColumn.CANDIDATE_NAME.value].isnull(),
                tt.agg.single_value(
                    state_results_table[ElectionCubeMeasure.VOTES.value]
                ),
            ),
        }
    )

    # VOTES measure has to be created first before we can chain it up
    m.update(
        {
            ElectionCubeMeasure.TOTAL_VOTES_DEPARTMENTS.value: tt.agg.sum(
                m[ElectionCubeMeasure.VOTES.value],
                scope=tt.OriginScope(
                    l[ElectionCubeLevel.REGION.value],
                    l[ElectionCubeLevel.DEPARTMENT.value],
                    l[ElectionCubeLevel.RESULT_DATE.value],
                    l[StateResultsTableColumn.CANDIDATE_NAME.value],
                ),
            ),
            ElectionCubeMeasure.PERCENT_VALID_VOTES.value: m[
                ElectionCubeMeasure.TOTAL_VALID_VOTES.value
            ]
            / m[ElectionCubeMeasure.TOTAL_REG_VOTERS.value],
            ElectionCubeMeasure.PERCENT_BLANK_VOTES.value: m[
                ElectionCubeMeasure.TOTAL_BLANK_VOTES.value
            ]
            / m[ElectionCubeMeasure.TOTAL_REG_VOTERS.value],
            ElectionCubeMeasure.PERCENT_NULL_VOTES.value: m[
                ElectionCubeMeasure.TOTAL_NULL_VOTES.value
            ]
            / m[ElectionCubeMeasure.TOTAL_REG_VOTERS.value],
            ElectionCubeMeasure.PERCENT_ABSTENTIONS.value: m[
                ElectionCubeMeasure.TOTAL_ABSTENTIONS.value
            ]
            / m[ElectionCubeMeasure.TOTAL_REG_VOTERS.value],
            ElectionCubeMeasure.TOTAL_INVALID_VOTES.value: m[
                ElectionCubeMeasure.TOTAL_BLANK_VOTES.value
            ]
            + m[ElectionCubeMeasure.TOTAL_NULL_VOTES.value]
            + m[ElectionCubeMeasure.TOTAL_ABSTENTIONS.value],
        }
    )

    # TOTAL_INVALID_VOTES measure  has to be created before we can chain it up
    m.update(
        {
            ElectionCubeMeasure.PERCENT_INVALID.value: m[
                ElectionCubeMeasure.TOTAL_INVALID_VOTES.value
            ]
            / m[ElectionCubeMeasure.TOTAL_REG_VOTERS.value]
        }
    )

    # TOTAL_VOTES_DEPARTMENTS measure has to be created first before we can chain it up
    m.update(
        {
            ElectionCubeMeasure.PERCENT_REG_VOTES.value: m[
                ElectionCubeMeasure.TOTAL_VOTES_DEPARTMENTS.value
            ]
            / m[ElectionCubeMeasure.TOTAL_REG_VOTERS.value],
            ElectionCubeMeasure.PERCENT_TURNOUT_VOTES.value: m[
                ElectionCubeMeasure.TOTAL_VOTES_DEPARTMENTS.value
            ]
            / m[ElectionCubeMeasure.TOTAL_TURNOUT.value],
            ElectionCubeMeasure.WINNING_CANDIDATE.value: tt.agg.max_member(
                m[ElectionCubeMeasure.TOTAL_VOTES_DEPARTMENTS.value],
                l[ElectionCubeLevel.CANDIDATE_NAME.value],
            ),
            ElectionCubeMeasure.WINNING_VOTES.value: tt.agg.max(
                m[ElectionCubeMeasure.TOTAL_VOTES_DEPARTMENTS.value],
                scope=tt.OriginScope(l[ElectionCubeLevel.CANDIDATE_NAME.value]),
            ),
        }
    )

    for measure_name in m:
        if "% " in measure_name:
            m[measure_name].formatter = "DOUBLE[0.000%]"


def create_cubes(session: tt.Session, /) -> None:
    create_election_cube(session)
