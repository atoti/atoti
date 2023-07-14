from __future__ import annotations

import atoti as tt

from .constants import (
    CandidateDtlTableColumn,
    CandidateTableColumn,
    LocationTableColumn,
    StateResultsTableColumn,
    StatisticsTableColumn,
    Table,
)


def create_candidate_table(session: tt.Session, /) -> None:
    session.create_table(
        Table.CANDIDATE_TBL.value,
        keys=[CandidateTableColumn.CANDIDATE_ID.value],
        types={
            CandidateTableColumn.CANDIDATE_ID.value: tt.type.STRING,
            CandidateTableColumn.CANDIDATE_NAME.value: tt.type.STRING,
            CandidateTableColumn.DISPLAYED_NAME.value: tt.type.STRING,
        },
    )


def create_candidate_dtl_table(session: tt.Session, /) -> None:
    session.create_table(
        Table.CANDIDATE_DTL_TBL.value,
        keys=[CandidateTableColumn.CANDIDATE_ID.value],
        types={
            CandidateDtlTableColumn.CANDIDATE_ID.value: tt.type.STRING,
            CandidateDtlTableColumn.CANDIDATE_NAME.value: tt.type.STRING,
            CandidateDtlTableColumn.GROUP.value: tt.type.STRING,
            CandidateDtlTableColumn.PARTY.value: tt.type.STRING,
            CandidateDtlTableColumn.STATUS.value: tt.type.INT,
        },
    )


def create_state_results_table(session: tt.Session, /) -> None:
    session.create_table(
        Table.STATE_RESULTS_TBL.value,
        keys=[
            StateResultsTableColumn.REGION.value,
            StateResultsTableColumn.DEPARTMENT.value,
            StateResultsTableColumn.RESULT_DATE.value,
            StateResultsTableColumn.CANDIDATE_NAME.value,
        ],
        types={
            StateResultsTableColumn.REGION.value: tt.type.STRING,
            StateResultsTableColumn.DEPARTMENT.value: tt.type.STRING,
            StateResultsTableColumn.RESULT_DATE.value: tt.type.LOCAL_DATE,
            StateResultsTableColumn.CANDIDATE_NAME.value: tt.type.STRING,
            StateResultsTableColumn.VOTES.value: tt.type.INT,
        },
    )


def create_statistics_table(session: tt.Session, /) -> None:
    session.create_table(
        Table.STATISTICS_TBL.value,
        keys=[
            StatisticsTableColumn.REGION.value,
            StatisticsTableColumn.DEPARTMENT.value,
            StatisticsTableColumn.RESULT_DATE.value,
        ],
        types={
            StatisticsTableColumn.REGION.value: tt.type.STRING,
            StatisticsTableColumn.DEPARTMENT.value: tt.type.STRING,
            StatisticsTableColumn.RESULT_DATE.value: tt.type.LOCAL_DATE,
            StatisticsTableColumn.ABSTENTIONS.value: tt.type.INT,
            StatisticsTableColumn.BLANK_VOTES.value: tt.type.INT,
            StatisticsTableColumn.NULL_VOTES.value: tt.type.INT,
            StatisticsTableColumn.REGISTERED_VOTERS.value: tt.type.INT,
            StatisticsTableColumn.TURNOUT.value: tt.type.INT,
            StatisticsTableColumn.VALID_VOTES.value: tt.type.INT,
        },
    )


def create_location_table(session: tt.Session, /) -> None:
    session.create_table(
        Table.LOCATION_TBL.value,
        keys=[
            LocationTableColumn.REGION.value,
        ],
        types={
            LocationTableColumn.REGION.value: tt.type.STRING,
            LocationTableColumn.LATITUDE.value: tt.type.DOUBLE,
            LocationTableColumn.LONGITUDE.value: tt.type.DOUBLE,
        },
    )


def join_tables(session: tt.Session, /) -> None:
    candidate_tbl = session.tables[Table.CANDIDATE_TBL.value]
    candidate_dtl_tbl = session.tables[Table.CANDIDATE_DTL_TBL.value]
    state_result_tbl = session.tables[Table.STATE_RESULTS_TBL.value]
    statistic_tbl = session.tables[Table.STATISTICS_TBL.value]
    location_tbl = session.tables[Table.LOCATION_TBL.value]

    candidate_tbl.join(
        candidate_dtl_tbl,
        (
            candidate_tbl[CandidateTableColumn.CANDIDATE_ID.value]
            == candidate_dtl_tbl[CandidateDtlTableColumn.CANDIDATE_ID.value]
        )
        & (
            candidate_tbl[CandidateTableColumn.CANDIDATE_NAME.value]
            == candidate_dtl_tbl[CandidateDtlTableColumn.CANDIDATE_NAME.value]
        ),
    )

    candidate_tbl.join(
        state_result_tbl,
        candidate_tbl[CandidateTableColumn.DISPLAYED_NAME.value]
        == state_result_tbl[StateResultsTableColumn.CANDIDATE_NAME.value],
    )

    state_result_tbl.join(statistic_tbl)
    state_result_tbl.join(location_tbl)


def create_and_join_tables(session: tt.Session, /) -> None:
    create_candidate_table(session)
    create_candidate_dtl_table(session)
    create_state_results_table(session)
    create_statistics_table(session)
    create_location_table(session)
    join_tables(session)
