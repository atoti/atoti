@session.endpoint("getIteration/{portfolio}", method="GET")
def get_iteration(request, user, session):
    portfolio = request.path_parameters["portfolio"]

    helper_util = helper.Helper(session)
    opt_mtd = helper_util.get_opt_mtd(portfolio)

    return opt_mtd


@session.endpoint("optimize", method="POST")
def trigger_optimization(request, user, session):
    helper_util = helper.Helper(session)
    data = request.body

    selected_port = data["portfolio"]
    selected_method = data["method"]
    selected_iteration = data["iteration"]
    # helper_util.query_and_optimize(selected_port, selected_method, selected_iteration)
    return f"hello {selected_port}, {selected_method}, {selected_iteration} "


@session.endpoint("upload/portfolio", method="POST")
def upload_portfolio(request, user, session):
    helper_util = helper.Helper(session)
    data = request.body
    portfolio = data["portfolio"]

    df = pd.DataFrame(data=portfolio[1:], columns=portfolio[0])
    df.dropna(inplace=True)
    df["Weights"] = pd.to_numeric(df["Weights"])
    tickers.get_new_tickers(df, session)

    return "Porfolio(s) uploaded successfully"
