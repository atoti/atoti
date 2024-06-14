import atoti as tt
import pandas


def main():

    # Start Atoti server and link UI
    session = tt.Session(
        user_content_storage="./02-content",
        port=9092,
        java_options=["-Xms1G", "-Xmx10G"],
    )
    session.link

    # Load data
    orders = session.read_csv(
        "s3://data.atoti.io/notebooks/hierarchies/data/Orders.csv",
        types={
            "OrderId": tt.STRING,
            "OrderDate": tt.LOCAL_DATE,
            "ProductId": tt.STRING,
            "EmployeeId": tt.STRING,
            "CustomerId": tt.STRING,
            "InventoryId": tt.STRING,
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

    inventory = session.read_csv(
        "s3://data.atoti.io/notebooks/hierarchies/data/Inventory.csv",
        types={
            "InventoryId": tt.STRING,
            "AsOfDate": tt.LOCAL_DATE,
            "Inventory": tt.INT,
        },
        date_patterns={"AsOfDate": "dd/M/yyyy"},
        keys=["InventoryId"],
    )

    # Join tables
    orders.join(products, orders["ProductId"] == products["ProductId"])
    orders.join(employees, orders["EmployeeId"] == employees["EmployeeId"])
    orders.join(customers, orders["CustomerId"] == customers["CustomerId"])
    orders.join(shippers, orders["ShipperName"] == shippers["ShipperName"])
    orders.join(inventory, orders["InventoryId"] == inventory["InventoryId"])

    # Create Cube from Atoti Table object
    cube = session.create_cube(orders)

    return cube, session
