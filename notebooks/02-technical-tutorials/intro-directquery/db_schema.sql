----------------------
-- Reference https://docs.activeviam.com/products/atoti/server/latest/docs/directquery/getting_started/
-- Create schema 
----------------------

CREATE SCHEMA tutorial;

----------------------
-- Create SALES table 
----------------------

CREATE TABLE IF NOT EXISTS `tutorial`.SALES (
  SALE_ID STRING NOT NULL,
  DATE DATE NOT NULL,
  SHOP STRING NOT NULL,
  PRODUCT STRING NOT NULL,
  QUANTITY INT64 NOT NULL,
  UNIT_PRICE FLOAT64 NOT NULL
);

INSERT INTO `tutorial`.SALES VALUES
  ('S0010','2022-01-31','shop_2','BED_2',3,150),
  ('S0009','2022-01-31','shop_3','BED_2',1,150),
  ('S0008','2022-01-31','shop_4','BED_2',1,150),
  ('S0007','2022-02-01','shop_5','BED_2',1,150),
  ('S0019','2022-02-02','shop_3','HOO_5',1,48),
  ('S0018','2022-02-03','shop_3','HOO_5',1,48),
  ('S0017','2022-02-04','shop_3','HOO_5',1,48),
  ('S0000','2022-02-04','shop_0','TAB_0',1,210),
  ('S0001','2022-02-03','shop_1','TAB_0',1,210),
  ('S0002','2022-02-02','shop_2','TAB_0',1,210),
  ('S0003','2022-02-01','shop_3','TAB_0',1,210),
  ('S0004','2022-02-03','shop_1','TAB_1',1,300),
  ('S0005','2022-02-02','shop_2','TAB_1',1,300),
  ('S0006','2022-02-01','shop_4','TAB_1',2,300),
  ('S0013','2022-02-01','shop_4','TSH_3',1,22),
  ('S0012','2022-02-02','shop_5','TSH_3',1,22),
  ('S0011','2022-02-03','shop_5','TSH_3',1,22),
  ('S0016','2022-01-31','shop_1','TSH_4',2,24),
  ('S0015','2022-02-01','shop_2','TSH_4',2,24),
  ('S0014','2022-02-02','shop_4','TSH_4',1,24);
  


----------------------
-- Create PRODUCTS table 
----------------------

CREATE TABLE IF NOT EXISTS `tutorial`.PRODUCTS (
  PRODUCT_ID STRING NOT NULL,
  CATEGORY STRING NOT NULL,
  SUB_CATEGORY STRING NOT NULL,
  SIZE STRING NOT NULL,
  PURCHASE_PRICE FLOAT64 NOT NULL,
  COLOR STRING NOT NULL,
  BRAND STRING NOT NULL
);

INSERT INTO `tutorial`.PRODUCTS VALUES
  ('TAB_0','Furniture','Table','1m80',190,'black','Basic'),
  ('TAB_1','Furniture','Table','2m40',280,'white','Mega'),
  ('BED_2','Furniture','Bed','Single',127,'red','Mega'),
  ('TSH_3','Cloth','Tshirt','M',19,'brown','Over'),
  ('TSH_4','Cloth','Tshirt','L',20,'black','Over'),
  ('HOO_5','Cloth','Hoodie','M',38,'red','Mega');