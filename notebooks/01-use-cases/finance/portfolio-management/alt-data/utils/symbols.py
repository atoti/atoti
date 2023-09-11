import datetime
import datetime as dt
import pandas as pd

def get_historical_vector(df_close):
    
    # compute returns
    df_daily_ret = df_close.diff().iloc[1:]
    df_daily_ret = df_daily_ret[(df_daily_ret == 0).sum(1) < 2]
    df_daily_ret_t = df_daily_ret.T
    df_daily_ret_t["daily_returns_vector"] = df_daily_ret_t.values.tolist()
    df_daily_ret_t = (
        df_daily_ret_t[["daily_returns_vector"]].rename_axis("symbol").reset_index()
    )

    # compute daily Rate of Returns
    df_daily_ror = df_close.resample("D").last().pct_change().iloc[1:]
    df_daily_ror = df_daily_ror[(df_daily_ror == 0).sum(1) < 2]
    df_daily_ror_t = df_daily_ror.T
    df_daily_ror_t["daily_ROR_vector"] = df_daily_ror_t.values.tolist()
    df_daily_ror_t = (
        df_daily_ror_t[["daily_ROR_vector"]].rename_axis("symbol").reset_index()
    )

    # compute monthly Rate of Returns
    df_mthly_ror = df_close.resample("M").last().pct_change().iloc[1:]
    df_mthly_ror = df_mthly_ror[(df_mthly_ror == 0).sum(1) < 2]
    df_mthly_ror_t = df_mthly_ror.T
    df_mthly_ror_t["monthly_ROR_vector"] = df_mthly_ror_t.values.tolist()
    df_mthly_ror_t = (
        df_mthly_ror_t[["monthly_ROR_vector"]].rename_axis("symbol").reset_index()
    )

    # ensure the dateline between daily ROR and the price vectors are consistent
    left, right = df_close.align(df_daily_ret, join="outer", axis=0)
    left = left.fillna(method="ffill").iloc[1:]

    # transform daily pricing
    df_price = left.T
    df_price["closing_price"] = df_price.values.tolist()
    df_price = df_price[["closing_price"]].rename_axis("symbol").reset_index()

    df_ror = pd.merge(df_daily_ret_t, df_daily_ror_t, on="symbol")
    df_ror = pd.merge(df_ror, df_mthly_ror_t, on="symbol")
    df_ror = pd.merge(df_ror, df_price, on="symbol")

    # get vector index
    daily_dates = pd.DataFrame(data={"historical_date": df_daily_ror.index.to_list()})
    daily_dates = daily_dates.rename_axis("date_index").reset_index()

    mthly_dates = pd.DataFrame(data={"historical_date": df_mthly_ror.index.to_list()})
    mthly_dates = mthly_dates.rename_axis("monthly_date_index").reset_index()

    df_dates = pd.merge(daily_dates, mthly_dates, on="historical_date", how="left")
    df_dates = df_dates.fillna(-1)
    df_dates[["date_index", "monthly_date_index"]] = df_dates[
        ["date_index", "monthly_date_index"]
    ].astype(int)
    
    df_ror["daily_returns_vector"] = [",".join(map(str, l)) for l in df_ror["daily_returns_vector"]]
    df_ror["daily_ROR_vector"] = [",".join(map(str, l)) for l in df_ror["daily_ROR_vector"]]
    df_ror["monthly_ROR_vector"] = [",".join(map(str, l)) for l in df_ror["monthly_ROR_vector"]]
    df_ror["closing_price"] = [",".join(map(str, l)) for l in df_ror["closing_price"]]

    return df_ror, df_dates


def get_new_tickers(df, session):
    # to improve - symbol should be refreshed for all portfolios available in the cube
    new_symbol = list(set(symbol + df["symbol"].to_list()))
    data, date_index = download_tickers(new_symbol, 3)

    session.tables["Price"].drop()
    session.tables["Price"].load_pandas(data)
    print("Finish loading historical pricing..")

    # load historical dates
    session.tables["Historical Dates"].drop()
    session.tables["Historical Dates"].load_pandas(date_index)
    print("Finish loading historical dates..")

    # load new portfolio allocation
    session.tables["Portfolios Allocation"].load_pandas(df)
    print("Finish loading portfolio allocation...")
