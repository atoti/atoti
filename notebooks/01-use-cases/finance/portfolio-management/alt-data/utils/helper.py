from utils import optimizer_utils as opt_utils
from utils import query_utils
import time
import pandas as pd

class Helper:
    def __init__(self, session):
        self.session = session
        self.cube = session.cubes["esg_optimization"]
        self.optimizer = opt_utils.Optimizer()
        self.querier = query_utils.Query(session)

    def query_and_optimize(self, selected_port, selected_method, selected_iteration):
        l, m = self.cube.levels, self.cube.measures
        self.portfolio_tbl = self.session.tables["portfolios"]

        historical_pricing = self.querier.get_past_pricing()
        office_contraints = [] # list[tuple[str, pd.DataFrame]]
        offices = ["#CFO_departures_in_past_1_year",
                   "#CEO_departures_in_past_1_year",
                   "#COO_departures_in_past_1_year"] # <~~ change this with actual measure[strings] of concern
        office_constraints = [1,2,3] # num departures per office in timeframe considered
        for office, limit in zip(offices, office_constraints):
            office_constraints.append((self.querier.get_departures_by_office(office), limit))

        weights_esg_min_vol = self.constr_min_volatility(historical_pricing, office_contraints)

        self.upload_iteration_weights(weights_esg_min_vol, selected_port, selected_iteration)

    def upload_iteration_weights(self, df, _name, _opt_mtd):
        """
        this function takes the iteration/simulation parameters
        and loads it back into the portfolio table
        """
        df["portfolio"] = _name # title of simulation
        df["iteration"] = f'{_opt_mtd}_{time.strftime("%Y%m%d_%X")}' # timestamp of simulation
        df["method"] = "esg_min_vol"
        # df["method"] = f'{_name}' # concat of both as a title
        self.portfolio_tbl.load_pandas(df) # upload to table
        
    
    def constr_min_volatility(self, df_hist_price, office_limit_list:tuple[pd.DataFrame,float]):
        """
        This function will compute a volitility-minimal, return-maximal portfolio
        subject to a constraint determined from the constraint dataframe (constr_df)
        with a minimum defined by min_constr_score  (default = 0.5)
        """
        # initialize efficent frontier optimizer
        ef = self.optimizer.init_model(df_hist_price)

        # set limits for each of the offices defined as 'relevant'
        # this is where the tuple of office data and departure limits is separated
        for off_df, limit in office_limit_list:
            # flatten constraint scores to a list
            constr_scores = off_df.values.flatten().tolist()
            # add the limit as a constraint on that office departure value
            ef.add_constraint(lambda w: constr_scores @ w <= limit) # a @ b == dot_product(a,b)

        # optimize based on minimal volitility
        ef.min_volatility()
        # get the resultant weights
        return_weights = ef.clean_weights()

        # not sure what this does
        ef.portfolio_performance(verbose=True)

        # make a dataframe from the weights
        weights_df = (
            pd.DataFrame.from_dict(return_weights, orient="index", columns=["weight"])
            .rename_axis("symbol")
            .reset_index()
        )

        return weights_df
    
    def get_opt_mtd(self, portfolio):
        l, m = self.cube.levels, self.cube.measures

        opt_mtd = ["base|base"]
        if portfolio != None:
            opt_mtd_df = self.cube.query(
                m["contributors.COUNT"],
                levels=[l["iteration"], l["method"]],
                # filter=(
                #     l[("portfolios", "portfolio", "portfolio")] == portfolio
                # ),
            )
            opt_mtd = opt_mtd_df.index.map("|".join).to_list()

        return opt_mtd

