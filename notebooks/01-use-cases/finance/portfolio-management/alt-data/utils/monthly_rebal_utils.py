import pandas as pd


def monthly_rebal(df_portfolio, date, cq_alphaflow_daily):
    # get the subset of alphaflow data from only the symbols in the portfolio
    df_portfolio.reset_index(inplace=True)
    drop_zeros = df_portfolio.drop(df_portfolio[df_portfolio["weight.SUM"] == 0].index)
    rebalanced = cq_alphaflow_daily[
        cq_alphaflow_daily["symbol"].isin(drop_zeros["symbol"].to_list())
    ].copy(deep=True)

    # hold on to the zero-valued weights
    only_zeros = df_portfolio.drop(
        df_portfolio[df_portfolio["weight.SUM"] != 0].index
    ).drop(columns=["weight.SUM"])
    only_zeros["weight"] = 0
    only_zeros["iteration"] = date
    only_zeros["method"] = "monthly_rebal"

    # calculate the method ratio from this data
    rebalanced = cq_alphaflow_daily[
        cq_alphaflow_daily["symbol"].isin(drop_zeros["symbol"].to_list())
    ].copy(deep=True)
    rebalanced.drop(rebalanced[rebalanced["timestamp"] != date].index, inplace=True)
    rebalanced["method5_ratio"] = (
        rebalanced["method5_inst_buy"] / rebalanced["method5_inst_sell"]
    )
    # calculate weights from the ratio data
    total = sum(rebalanced["method5_ratio"])
    rebalanced["weight"] = rebalanced["method5_ratio"] / total
    rebalanced["portfolio"] = df_portfolio["portfolio"][0]
    rebalanced["iteration"] = date
    rebalanced["method"] = "monthly_rebal"

    return pd.concat(
        [
            rebalanced[["portfolio", "iteration", "method", "symbol", "weight"]],
            only_zeros,
        ]
    )
