import atoti as tt
import pandas


def main():

    session = tt.Session(
        user_content_storage="./02-content",
        port=9092,
        java_options=["-Xms1G", "-Xmx10G"],
    )
    session.link

    orders = session.read_csv(
        "s3://data.atoti.io/notebooks/hierarchies/data/Orders.csv",
        types={
            "OrderId": tt.STRING,
            "OrderDate": tt.LOCAL_DATE,
            "ProductId": tt.STRING,
            "EmployeeId": tt.STRING,
            "CustomerId": tt.STRING,
        },
        date_patterns={"OrderDate": "dd/M/yyyy"},
        keys=["OrderId"],
    )
    orders.head()

    products = session.read_csv(
        "s3://data.atoti.io/notebooks/hierarchies/data/Products.csv",
        types={
            "ProductId": tt.STRING,
            "ProductName": tt.STRING,
            "ProductCategory": tt.STRING,
            "Supplier": tt.STRING,
            "PurchasingPricePerUnit": tt.DOUBLE,
        },
        keys=["ProductId"],
    )
    products.head()

    shippers = session.read_csv(
        "s3://data.atoti.io/notebooks/hierarchies/data/Shippers.csv",
        types={
            "ShipperName": tt.STRING,
            "Contact": tt.STRING,
        },
    )
    shippers.head()

    customers = session.read_csv(
        "s3://data.atoti.io/notebooks/hierarchies/data/Customers.csv",
        types={
            "CustomerId": tt.STRING,
            "CompanyName": tt.STRING,
            "Region": tt.STRING,
            "Country": tt.STRING,
            "Address": tt.STRING,
            "City": tt.STRING,
            "PostCode": tt.STRING,
            "Phone": tt.STRING,
        },
        keys=["CustomerId"],
    )
    customers.head()

    employees = session.read_csv(
        "s3://data.atoti.io/notebooks/hierarchies/data/Employees.csv",
        types={
            "EmployeeId": tt.STRING,
            "EmployeeName": tt.STRING,
            "EmployeeCountry": tt.STRING,
            "EmployeeCity": tt.STRING,
        },
        keys=["EmployeeId"],
    )
    employees.head()

    # Join tables
    orders.join(products, orders["ProductId"] == products["ProductId"])
    orders.join(employees, orders["EmployeeId"] == employees["EmployeeId"])
    orders.join(customers, orders["CustomerId"] == customers["CustomerId"])
    orders.join(shippers, orders["ShipperName"] == shippers["ShipperName"])

    # Create Cube from Atoti Table object
    cube = session.create_cube(orders)

    return cube, session
