-- ---------------------------------
-- Database and Table creation
-- ---------------------------------

CREATE DATABASE IF NOT EXISTS ATOTI;

CREATE TABLE IF NOT EXISTS ATOTI.TRADE_PNLS (
  `BookId` Int64, 
  `AsOfDate` Date32, 
  `TradeId` String, 
  `DataSet` String, 
  `RiskFactor` String, 
  `RiskClass` String, 
  `SensitivityName` String, 
  `ccy` String, 
  `pnl_vector` Array(Float64), 
)
ENGINE = MergeTree()
PRIMARY KEY (`BookId`, `AsOfDate`, `TradeId`, `DataSet`);

-- ---------------------------------
-- Role and User creation
-- ---------------------------------


CREATE ROLE querier;

GRANT SELECT ON ATOTI.* TO querier WITH GRANT OPTION;
GRANT SELECT ON system.databases TO querier WITH GRANT OPTION;
GRANT SELECT ON system.processes TO querier WITH GRANT OPTION;
GRANT SELECT ON system.tables TO querier WITH GRANT OPTION;
GRANT SELECT ON system.columns TO querier WITH GRANT OPTION;

CREATE USER IF NOT EXISTS ATOTI_QUERIER IDENTIFIED WITH sha256_password BY '<password>' DEFAULT ROLE querier;