from __future__ import annotations

import logging

import atoti as tt

from .config import Config
from .constants import Table


def load_tables(session: tt.Session, /, *, config: Config) -> None:
    with session.start_transaction():
        session.tables[Table.CANDIDATE_TBL.value].load_csv(
            f"{config.aws_s3_path}candidate_mapping.csv"
        )

        session.tables[Table.CANDIDATE_DTL_TBL.value].load_csv(
            f"{config.aws_s3_path}candidates.csv",
            columns={
                "": "Candidate ID",
                "name": "Candidate name",
                "group": "Group",
                "party": "Party",
                "status": "Status",
            },
        )

        session.tables[Table.STATE_RESULTS_TBL.value].load_csv(
            f"{config.aws_s3_path}states_results.csv",
            encoding="iso-8859-15",
            columns={
                "Region": "Region",
                "Department": "Department",
                "Result date": "Result date",
                "Candidate name": "Candidate name",
                "Votes": "Votes",
            },
        )

        session.tables[Table.STATISTICS_TBL.value].load_csv(
            f"{config.aws_s3_path}states_statistics.csv",
            encoding="iso-8859-15",
        )

        session.tables[Table.LOCATION_TBL.value].load_csv(
            f"{config.aws_s3_path}region_location.csv"
        )

    logging.info(
        "Loaded into %s - columns: %d, rows: %d",
        Table.CANDIDATE_TBL.value,
        len(session.tables[Table.CANDIDATE_TBL.value].columns),
        len(session.tables[Table.CANDIDATE_TBL.value]),
    )

    logging.info(
        "Loaded into %s - columns: %d, rows: %d",
        Table.CANDIDATE_DTL_TBL.value,
        len(session.tables[Table.CANDIDATE_DTL_TBL.value].columns),
        len(session.tables[Table.CANDIDATE_DTL_TBL.value]),
    )

    logging.info(
        "Loaded into %s - columns: %d, rows: %d",
        Table.STATE_RESULTS_TBL.value,
        len(session.tables[Table.STATE_RESULTS_TBL.value].columns),
        len(session.tables[Table.STATE_RESULTS_TBL.value]),
    )

    logging.info(
        "Loaded into %s - columns: %d, rows: %d",
        Table.STATISTICS_TBL.value,
        len(session.tables[Table.STATISTICS_TBL.value].columns),
        len(session.tables[Table.STATISTICS_TBL.value]),
    )

    logging.info(
        "Loaded into %s - columns: %d, rows: %d",
        Table.LOCATION_TBL.value,
        len(session.tables[Table.LOCATION_TBL.value].columns),
        len(session.tables[Table.LOCATION_TBL.value]),
    )
