from atoti import MeasureMetadata


def set_measure_metadata(m, measure, formatter=None, folder=None):
    if m.__contains__(measure):
        metadata = None
        if (formatter is not None) & (folder is not None):
            metadata = MeasureMetadata(formatter=formatter, folder=folder)
        elif folder is not None:
            metadata = MeasureMetadata(folder=folder)
        elif formatter is not None:
            metadata = MeasureMetadata(formatter=formatter)
        if metadata is not None:
            m[measure] = (m[measure], metadata)


def rearrange_measures(m):
    # formatter
    big_formatter = "DOUBLE[#,###]"
    double_formatter = "DOUBLE[#,###.00]"
    double_precise_formatter = "DOUBLE[#,###.0000000]"
    int_formatter = "INT[#,###]"

    percentage_formatter = "DOUBLE[#,###.00%]"
    precise_percentage_formatter = "DOUBLE[#,###.0000%]"

    # folders
    sep = "\\"
    count_folder = "Counts"
    mtm = "MtM"
    pnl = "PnL"
    sensi = "Sensi"
    explainers = "Explainers"
    day_to_day = "DayToDay"
    intraday = "Intraday"
    interpolation = "Interpolation"
    spot = "Spot"
    product = "Product"
    underlying = "Underlying"
    realtime = "Realtime"
    static = "Static"

    set_measure_metadata(m, "CrossGamma", formatter=double_formatter, folder=sensi)

    set_measure_metadata(
        m,
        "CrossGamma Explainer",
        formatter=double_formatter,
        folder=pnl + sep + day_to_day + sep + explainers,
    )

    set_measure_metadata(
        m,
        "CrossGamma Predict (static)",
        formatter=double_formatter,
        folder=pnl + sep + explainers + sep + intraday,
    )

    set_measure_metadata(
        m, "CrossGamma Previous", formatter=double_formatter, folder=sensi
    )

    set_measure_metadata(m, "Delta", formatter=double_formatter, folder=sensi)

    set_measure_metadata(
        m,
        "Delta Explainer",
        formatter=double_formatter,
        folder=pnl + sep + day_to_day + sep + explainers,
    )

    set_measure_metadata(
        m,
        "Delta Predict (Cross Gamma)",
        formatter=double_formatter,
        folder=pnl + sep + explainers + sep + intraday,
    )

    set_measure_metadata(m, "Delta Previous", formatter=double_formatter, folder=sensi)

    set_measure_metadata(m, "Gamma", formatter=double_formatter, folder=sensi)

    set_measure_metadata(
        m,
        "Gamma Explainer",
        formatter=double_formatter,
        folder=pnl + sep + day_to_day + sep + explainers,
    )

    set_measure_metadata(
        m,
        "Gamma Predict (interpolated)",
        formatter=double_formatter,
        folder=pnl + sep + explainers + sep + intraday,
    )

    set_measure_metadata(m, "Gamma Previous", formatter=double_formatter, folder=sensi)

    set_measure_metadata(
        m, "Gamma Left", formatter=double_formatter, folder=interpolation
    )

    set_measure_metadata(
        m, "Gamma Right", formatter=double_formatter, folder=interpolation
    )

    set_measure_metadata(m, "Gamma Vector", folder=interpolation)

    set_measure_metadata(
        m, "LeftBoundIndex", formatter=int_formatter, folder=interpolation
    )

    set_measure_metadata(
        m, "MtM", formatter=big_formatter, folder=mtm + sep + day_to_day
    )

    set_measure_metadata(
        m, "MtM Predict", formatter=big_formatter, folder=mtm + sep + intraday
    )

    set_measure_metadata(
        m,
        "MtM Without New Trades",
        formatter=big_formatter,
        folder=mtm + sep + day_to_day,
    )

    set_measure_metadata(m, "MarketValue", formatter=big_formatter, folder=mtm)

    set_measure_metadata(
        m,
        "New Trade Explainer",
        formatter=big_formatter,
        folder=pnl + sep + day_to_day + sep + explainers,
    )

    set_measure_metadata(
        m, "PnL", formatter=big_formatter, folder=pnl + sep + day_to_day
    )

    set_measure_metadata(
        m, "PnL Explain", formatter=big_formatter, folder=pnl + sep + explainers
    )

    set_measure_metadata(
        m,
        "PnL Explain Without New Trades",
        formatter=big_formatter,
        folder=pnl + sep + intraday,
    )

    set_measure_metadata(
        m, "PnL Predict", formatter=big_formatter, folder=pnl + sep + intraday
    )

    set_measure_metadata(
        m, "PnL Unexplain", formatter=big_formatter, folder=pnl + sep + day_to_day
    )

    set_measure_metadata(
        m,
        "Realtime Spot",
        formatter=double_precise_formatter,
        folder=spot + sep + realtime,
    )

    set_measure_metadata(
        m,
        "Realtime Spot Product",
        formatter=double_precise_formatter,
        folder=spot + sep + realtime + sep + product,
    )

    set_measure_metadata(
        m,
        "Realtime Spot Underlying",
        formatter=double_precise_formatter,
        folder=spot + sep + realtime + sep + underlying,
    )

    set_measure_metadata(
        m, "RightBoundIndex", formatter=int_formatter, folder=interpolation
    )

    set_measure_metadata(m, "Spot", formatter=double_precise_formatter, folder=spot)

    set_measure_metadata(
        m,
        "Spot Change Absolute",
        formatter=double_precise_formatter,
        folder=spot + sep + realtime,
    )

    set_measure_metadata(
        m,
        "Spot Change Absolute Product",
        formatter=double_precise_formatter,
        folder=spot + sep + realtime + sep + product,
    )

    set_measure_metadata(
        m,
        "Spot Change Absolute Underlying",
        formatter=double_precise_formatter,
        folder=spot + sep + realtime + sep + underlying,
    )

    set_measure_metadata(
        m,
        "Spot Change Relative",
        formatter=double_precise_formatter,
        folder=spot + sep + realtime,
    )

    set_measure_metadata(
        m,
        "Spot Change Relative Product",
        formatter=double_precise_formatter,
        folder=spot + sep + realtime + sep + product,
    )

    set_measure_metadata(
        m,
        "Spot Change Relative Underlying",
        formatter=double_precise_formatter,
        folder=spot + sep + realtime + sep + underlying,
    )

    set_measure_metadata(
        m,
        "Spot DayToDay Absolute",
        formatter=double_precise_formatter,
        folder=spot + sep + static,
    )

    set_measure_metadata(
        m,
        "Spot DayToDay Absolute Product",
        formatter=double_precise_formatter,
        folder=spot + sep + static + sep + product,
    )

    set_measure_metadata(
        m,
        "Spot DayToDay Absolute Underlying",
        formatter=double_precise_formatter,
        folder=spot + sep + static + sep + underlying,
    )

    set_measure_metadata(
        m,
        "Spot DayToDay Relative",
        formatter=double_precise_formatter,
        folder=spot + sep + static,
    )

    set_measure_metadata(
        m,
        "Spot DayToDay Relative Product",
        formatter=double_precise_formatter,
        folder=spot + sep + static + sep + product,
    )

    set_measure_metadata(
        m,
        "Spot DayToDay Relative Underlying",
        formatter=double_precise_formatter,
        folder=spot + sep + static + sep + underlying,
    )

    set_measure_metadata(
        m, "Spot Left", formatter=double_precise_formatter, folder=interpolation
    )

    set_measure_metadata(
        m,
        "Spot Product",
        formatter=double_precise_formatter,
        folder=spot + sep + static + sep + product,
    )

    set_measure_metadata(
        m,
        "Spot Product T-1",
        formatter=double_precise_formatter,
        folder=spot + sep + static + sep + product,
    )

    set_measure_metadata(
        m, "Spot Right", formatter=double_precise_formatter, folder=interpolation
    )

    set_measure_metadata(
        m,
        "Spot Underlying",
        formatter=double_precise_formatter,
        folder=spot + sep + static + sep + underlying,
    )

    set_measure_metadata(
        m,
        "Spot Underlying T-1",
        formatter=double_precise_formatter,
        folder=spot + sep + static + sep + underlying,
    )

    set_measure_metadata(m, "Spot Vector", folder=interpolation)

    set_measure_metadata(m, "Vega Weighted", formatter=double_formatter, folder=sensi)

    set_measure_metadata(
        m,
        "Vega Weighted Explainer",
        formatter=double_formatter,
        folder=pnl + sep + day_to_day + sep + explainers,
    )

    set_measure_metadata(
        m,
        "Vega Weighted Predict (static)",
        formatter=double_formatter,
        folder=pnl + sep + explainers + sep + intraday,
    )

    set_measure_metadata(
        m, "Vega Weighted Previous", formatter=double_formatter, folder=sensi
    )

    set_measure_metadata(m, "Weight", formatter=double_precise_formatter, folder=mtm)

    set_measure_metadata(
        m, "Weight Previous", formatter=double_precise_formatter, folder=mtm
    )

    set_measure_metadata(
        m, "Distinct Product", formatter=int_formatter, folder=count_folder
    )

    set_measure_metadata(
        m, "Distinct Underlying", formatter=int_formatter, folder=count_folder
    )

    set_measure_metadata(
        m, "contributors.COUNT", formatter=int_formatter, folder=count_folder
    )

    set_measure_metadata(
        m, "Gamma Interpolated", formatter=double_formatter, folder=sensi
    )

    set_measure_metadata(
        m,
        "MtM Predict Difference",
        formatter=big_formatter,
        folder=mtm + sep + intraday,
    )

    set_measure_metadata(
        m,
        "MtM Predict Difference Percentage",
        formatter=percentage_formatter,
        folder=mtm + sep + intraday,
    )

    set_measure_metadata(
        m, "MtM Predict Previous", formatter=big_formatter, folder=mtm + sep + intraday
    )

    set_measure_metadata(m, "MtM Previous", formatter=big_formatter, folder=mtm)

    set_measure_metadata(
        m, "Gamma Vector Expand", formatter=double_precise_formatter, folder=sensi
    )

    set_measure_metadata(
        m, "MtM Predict Difference", formatter=big_formatter, folder=mtm
    )

    set_measure_metadata(
        m, "PnL Predict Difference", formatter=big_formatter, folder=pnl
    )

    set_measure_metadata(
        m,
        "PnL Predict Difference Percentage",
        formatter=percentage_formatter,
        folder=pnl,
    )

    set_measure_metadata(
        m, "PnL Predict Previous", formatter=big_formatter, folder=pnl + sep + intraday
    )

    set_measure_metadata(
        m,
        "Spot Vector Expand",
        formatter=double_precise_formatter,
        folder=spot + sep + realtime,
    )

    set_measure_metadata(
        m, "Vector Index Measure", formatter=int_formatter, folder=interpolation
    )
