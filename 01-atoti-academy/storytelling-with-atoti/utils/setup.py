import atoti as tt


def setup_tables(session):
    product_tbl = session.read_csv(
        "s3://data.atoti.io/atoti-academy/data/Products.csv",
        table_name="Products",
        data_types={
            "ProductId": tt.type.STRING,
        },
        keys=["ProductId"],
    )

    orders_tbl = session.read_csv(
        "s3://data.atoti.io/atoti-academy/data/Orders.csv",
        table_name="Orders",
        keys=["OrderId", "ProductId"],
        data_types={
            "OrderId": tt.type.STRING,
            "ProductId": tt.type.STRING,
            "EmployeeId": tt.type.STRING,
            "OrderDate": tt.type.LOCAL_DATE,
        },
        date_patterns={"OrderDate": "dd/M/yyyy"},
        default_values={"QuantitySold": 0, "SellingPricePerUnit": 0.0},
    )

    customer_tbl = session.read_csv(
        "s3://data.atoti.io/atoti-academy/data/Customers.csv",
        table_name="Customers",
        keys=["CustomerId"],
    )

    employee_tbl = session.read_csv(
        "s3://data.atoti.io/atoti-academy/data/Employees.csv",
        table_name="Employees",
        keys=["EmployeeId"],
        data_types={
            "EmployeeId": tt.type.STRING,
        },
    )

    historicalPrices_tbl = session.read_csv(
        "s3://data.atoti.io/atoti-academy/data/HistoricalPrices.csv",
        keys=["ProductId"],
        table_name="HistoricalPrices",
        data_types={
            "HistoricalPrice": tt.type.DOUBLE_ARRAY,
            "ProductId": tt.type.STRING,
        },
    )

    shipper_tbl = session.read_csv(
        "s3://data.atoti.io/atoti-academy/data/Shippers.csv",
        table_name="Shippers",
        keys=["Shipper", "Interval"],
    )

    orders_tbl.join(product_tbl, (orders_tbl["ProductId"] == product_tbl["ProductId"]))
    orders_tbl.join(
        customer_tbl, (orders_tbl["CustomerId"] == customer_tbl["CustomerId"])
    )
    orders_tbl.join(
        employee_tbl, (orders_tbl["EmployeeId"] == employee_tbl["EmployeeId"])
    )
    orders_tbl.join(shipper_tbl, orders_tbl["ShipperName"] == shipper_tbl["Shipper"])

    product_tbl.join(
        historicalPrices_tbl,
        product_tbl["ProductId"] == historicalPrices_tbl["ProductId"],
    )

    return orders_tbl


def create_hierarchies(session):
    orders_tbl = session.tables["Orders"]
    product_tbl = session.tables["Products"]
    cube = session.cubes["Order Cube"]

    cube.create_date_hierarchy(
        "Dates",
        column=orders_tbl["OrderDate"],
        levels={"Year": "yyyy", "Quarter": "QQQ", "Month": "MM", "Day": "dd"},
    )

    cube.hierarchies["Products"] = [
        product_tbl["ProductCategory"],
        product_tbl["ProductName"],
    ]


def create_measures(session):
    orders_tbl = session.tables["Orders"]
    product_tbl = session.tables["Products"]
    shipper_tbl = session.tables["Shippers"]

    cube = session.cubes["Order Cube"]

    h, l, m = cube.hierarchies, cube.levels, cube.measures

    # creating measures from the referenced table
    m["PurchasingPricePerUnit.SUM"] = tt.agg.sum(product_tbl["PurchasingPricePerUnit"])
    m["PurchasingPricePerUnit.MEAN"] = tt.agg.mean(
        product_tbl["PurchasingPricePerUnit"]
    )
    m["PurchasingPricePerUnit"] = tt.agg.single_value(
        product_tbl["PurchasingPricePerUnit"]
    )

    m["SellingPricePerUnit"] = tt.agg.single_value(orders_tbl["SellingPricePerUnit"])

    # Compute Profit
    m["ProfitPerUnit"] = tt.where(
        ~l["OrderId"].isnull(), m["SellingPricePerUnit"] - m["PurchasingPricePerUnit"]
    )

    m["Profit"] = tt.agg.sum(
        m["ProfitPerUnit"] * m["QuantitySold.SUM"],
        scope=tt.OriginScope(levels={l["OrderId"]}),
    )

    m["Profit.MEAN"] = tt.agg.sum(
        m["Profit"] / m["QuantitySold.SUM"], scope=tt.OriginScope(levels={l["OrderId"]})
    )

    # Compute transport rates
    m["ShipperRate"] = tt.agg.single_value(shipper_tbl["Rate"])
    l["Interval"].order = tt.CustomOrder(
        first_elements=[
            "Quantity less than 100",
            "Quantity between 100 and 300",
            "Quantity between 300 and 500",
            "Quantity between 500 and 700",
            "Quantity more than 700",
        ]
    )

    quantitySold = m["QuantitySold.SUM"]

    m["Interval"] = tt.where(
        (~l["OrderId"].isnull()),
        tt.where(
            {
                (quantitySold > 0) & (quantitySold < 100): "Quantity less than 100",
                (quantitySold >= 100)
                & (quantitySold < 300): "Quantity between 100 and 300",
                (quantitySold >= 300)
                & (quantitySold < 500): "Quantity between 300 and 500",
                (quantitySold >= 500)
                & (quantitySold < 700): "Quantity between 500 and 700",
                quantitySold >= 700: "Quantity more than 700",
            },
            default="Unknown",
        ),
    )

    m["TransportOrdersCount"] = tt.agg.sum(
        tt.where((l["Interval"] == m["Interval"]), 1),
        scope=tt.OriginScope(levels={l["OrderId"]}),
    )
    m["TransportRate"] = tt.where((l["Interval"] == m["Interval"]), m["ShipperRate"])

    m["TransportCost"] = tt.agg.sum_product(
        m["TransportRate"],
        m["QuantitySold.SUM"],
        scope=tt.OriginScope(levels={l["ShipperName"], l["OrderId"], l["Interval"]}),
    )

    m["ShipperRate"].formatter = "DOUBLE[#,##0.000]"
    m["ShipperRate"].folder = "Transport"
    m["Interval"].folder = "Transport"
    m["TransportOrdersCount"].folder = "Transport"
    m["TransportRate"].folder = "Transport"
    m["TransportCost"].folder = "Transport"


def nb2_measures(cube):
    h, l, m = cube.hierarchies, cube.levels, cube.measures

    # Compute sales and profit margin
    m["Sales"] = tt.agg.sum_product(
        m["QuantitySold.SUM"],
        m["SellingPricePerUnit"],
        scope=tt.OriginScope(levels={l["ProductId"], l["OrderId"]}),
    )

    m["ProfitMargin"] = m["Profit"] / m["Sales"]
    m["ProfitMargin"].formatter = "DOUBLE[0.00%]"


def nb3_measures(cube):
    h, l, m = cube.hierarchies, cube.levels, cube.measures

    # Compute sales trend
    previousSales = tt.shift(m["Sales"], h["OrderDate"], offset=-1)
    m["SalesTrend"] = tt.where(~previousSales.isnull(), m["Sales"] - previousSales)

    m["ProductProfitabilityRank"] = tt.rank(
        m["ProfitMargin"], h["Products"], ascending=False
    )

    # compute the total of the parent level
    # i.e. at Product level, return the profit of the product category it belongs to
    m["TotalProfit"] = tt.parent_value(m["Profit"], degrees={h["Products"]: 1})

    # compute the percentage contribution to the total of the category it belongs to
    m["%ProfitContribution"] = m["Profit"] / m["TotalProfit"]
    m["%ProfitContribution"].formatter = "DOUBLE[0.00%]"

    # rank products by the contribution
    m["ProfitContributionRank"] = tt.rank(
        m["%ProfitContribution"], h["Products"], ascending=False
    )

    # s3://github.com/atoti/atoti/discussions/785
    # to perform cumulation based on measure ranks than levels
    m["%CumulativeProfitContribution"] = tt.agg.sum(
        m["%ProfitContribution"],
        scope=tt.CumulativeScope(level=l[("Products", "Products", "ProductName")]),
    )

    m["TotalProfit (Product)"] = tt.parent_value(
        m["Profit"], degrees={h["ProductName"]: 1}
    )

    # Take contribution across the product's total profit.
    m["%ProfitContribution (Product)"] = m["Profit"] / m["TotalProfit (Product)"]
    m["%ProfitContribution (Product)"].formatter = "DOUBLE[0.00%]"

    # Rank against the product name
    m["ProfitContributionRank (Product)"] = tt.rank(
        m["%ProfitContribution (Product)"], h["ProductName"], ascending=False
    )

    m["%CumulativeProfitContribution (Product)"] = tt.agg.sum(
        m["%ProfitContribution (Product)"],
        scope=tt.CumulativeScope(level=l[("Products", "ProductName", "ProductName")]),
    )

    # put products level measures into the product folder
    for _m_name in m:
        if "(Product)" in _m_name and m[_m_name].visible == True:
            m[_m_name].folder = "Products"


def create_app(ses_name="training1", port=9095):
    session = tt.Session.start(
        tt.SessionConfig(
            # name=ses_name,
            user_content_storage=f"./{ses_name}",
            port=port,
            java_options=["-Xms1G", "-Xmx8G"],
            # requires Atoti license
            # app_extensions=tt.ADVANCED_APP_EXTENSION,
        )
    )

    base_table = setup_tables(session)
    cube = session.create_cube(base_table, name="Order Cube")
    create_hierarchies(session)
    create_measures(session)

    return session, cube
