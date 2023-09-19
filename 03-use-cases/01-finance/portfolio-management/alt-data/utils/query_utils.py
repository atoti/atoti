import pandas as pd


class Query:
    def __init__(self, session):
        self.session = session
        self.cube = session.cubes["esg_optimization"]

        self.l = self.cube.levels
        self.m = self.cube.measures

    def get_portfolio(self):
        portfolio_df = self.cube.query(
            self.m["contributors.COUNT"],
            levels=[self.l["portfolio"], self.l["iteration"], self.l["method"]],
        )

        return portfolio_df.index.get_level_values(0).unique().to_list()

    def get_portfolio_details(self, _portfolio, _iteration=None):
        portfolio_dtl = self.cube.query(
            self.m["contributors.COUNT"],
            levels=[
                self.l["portfolio"],
                self.l[("Portfolios Allocation", "interation", "interation")],
                self.l[("Portfolios Allocation", "method", "method")],
            ],
            filter=(self.l["portfolio"] == _portfolio),
            mode="raw",
        )

        iteration_list = portfolio_dtl["iteration"].unique().tolist()

        # get the opt method for the first default method
        iter_val = _iteration if _iteration != None else iteration_list[0]
        opt_mtd_list = portfolio_dtl[portfolio_dtl["iteration"] == iter_val][
            "method"
        ].to_list()

        iteration_list.sort()
        opt_mtd_list.sort()

        return iteration_list, opt_mtd_list

    def get_weights(self, _portfolio, _iteration, _opt_mtd, weight_type):
        weights = {}
        portfolio_dtl = self.cube.query(
            self.m["contributors.COUNT"],
            self.m["weight.SUM"],
            levels=[self.l[weight_type]],
            filter=(self.l["portfolio"] == _portfolio)
            & (
                self.l[("Portfolios Allocation", "iteration", "iteration")]
                == _iteration
            )
            & (self.l[("Portfolios Allocation", "method", "method")] == _opt_mtd),
        )

        portfolio_dtl = portfolio_dtl.reset_index()
        for row in portfolio_dtl.to_dict("records"):
            weights[row[weight_type]] = {
                "min": 0.0,
                "max": 1.0,
                "current": row["weight.SUM"],
            }

        return weights

    def get_historical_pricing(self, portfolio, iteration, opt_mtd):
        df_historical_price = self.cube.query(
            self.m["Daily Price"],
            levels=[
                self.l["historical_date"],
                self.l["symbol"],
            ],
            filter=(
                (self.l["portfolio"] == portfolio)
                & (self.l["iteration"] == iteration)
                & (self.l["method"] == opt_mtd)
            ),
        )

        df_historical_price.reset_index(inplace=True)
        df_price = df_historical_price.pivot(
            index="historical_date", columns="symbol", values="Daily Price"
        )

        return df_price

    def get_sector_spread(self, portfolio, iteration, opt_mtd):
        sector_df = self.cube.query(
            self.m["contributors.COUNT"],
            levels=[self.l["GICS Sector"], self.l["symbol"]],
            filter=(
                (self.l["portfolio"] == portfolio)
                & (self.l["iteration"] == iteration)
                & (self.l["method"] == opt_mtd)
            ),
        )

        return sector_df

    def load_weights(self, weights_df):
        portfolio_table = self.session.tables["Portfolios Allocation"]
        portfolio_table.load_pandas(weights_df)

    def load_limits(
        self,
        portfolio,
        # iteration,
        opt_mtd,
        sector_spread,
        sector_weight_upper,
        sector_weight_lower,
        ticker_weight_upper,
        ticker_weight_lower,
        target_returns,
        # limit_type="Ticker",
    ):
        lb_ticker_max_weight = "Max symbol weight"
        lb_ticker_min_weight = "Min symbol weight"
        lb_sector_max_weight = "Max esg weight"
        lb_sector_min_weight = "Min esg weight"
        lb_sector_column_name = "GICS Sector"
        lb_ticker_column_name = "symbol"
        lb_simulation_name = "Weight simulation"

        sector_limits_df = pd.merge(
            pd.DataFrame(
                sector_weight_upper.items(),
                columns=[lb_sector_column_name, lb_sector_max_weight],
            ),
            pd.DataFrame(
                sector_weight_lower.items(),
                columns=[lb_sector_column_name, lb_sector_min_weight],
            ),
            how="outer",
            on=[lb_sector_column_name],
        )

        ticker_limits_df = pd.merge(
            pd.DataFrame(
                ticker_weight_upper.items(),
                columns=[lb_ticker_column_name, lb_ticker_max_weight],
            ),
            pd.DataFrame(
                ticker_weight_lower.items(),
                columns=[lb_ticker_column_name, lb_ticker_min_weight],
            ),
            how="outer",
            on=[lb_ticker_column_name],
        )

        # get sector for the ticker
        _ticker_df = pd.merge(
            ticker_limits_df, sector_spread, on=[lb_ticker_column_name], how="inner"
        )
        limits_df = pd.merge(
            sector_limits_df, _ticker_df, on=[lb_sector_column_name], how="outer"
        )

        limits_df["Scenario"] = lb_simulation_name
        limits_df["Portfolio"] = portfolio
        limits_df["Opt Method"] = opt_mtd
        limits_df["Target returns"] = target_returns

        limit_simulation = self.session.tables[lb_simulation_name]
        limit_simulation.load_pandas(limits_df[limit_simulation.columns])

    ###########################
    # For sector optimization
    ###########################

    def get_distinct_sectors(self):
        sector_df = self.cube.query(
            self.m["contributors.COUNT"], levels=[self.l["GICS Sector"]], mode="raw"
        )
        return sector_df["GICS Sector"].to_list()

    def get_historical_price_by_sector(self, sector):
        df_historical_price = self.cube.query(
            self.m["Daily Price"],
            levels=[
                self.l["Historical Dates"],
                self.l["Tickers"],
            ],
            filter=(self.l["GICS Sector"] == sector),
        )

        df_historical_price.reset_index(inplace=True)
        df_price = df_historical_price.pivot(
            index="Historical Dates", columns="Tickers", values="Daily Price"
        )

        return df_price

    # i believe there should / maybe want a function to do get_esg_data_by_sector

    def get_past_pricing(self):
        df_historical_price = self.cube.query(
            self.m["Daily Price"],
            levels=[
                self.l["historical_date"],
                self.l["symbol"],
            ],
        )

        df_historical_price.reset_index(inplace=True)
        df_price = df_historical_price.pivot(
            index="historical_date", columns="symbol", values="Daily Price"
        )

        return df_price

    def get_esg(self):
        esg_df = self.cube.query(
            self.m["ESG Score"],
            levels=[self.l["symbol"]],
        )

        return esg_df

    def get_departures_by_office(self, office) -> pd.DataFrame:
        """
        This function will return a dataframe defined by a measure and only that measure,
        relative to the symbols in the cube. This is used to optimize values relative to the
        symbol later.
        """
        office_df = self.cube.query(
            self.m[office],
            levels=[self.l["symbol"]],
        )
        return office_df
