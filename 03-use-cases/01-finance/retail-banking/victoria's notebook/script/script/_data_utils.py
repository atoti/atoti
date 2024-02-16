import threading
import time
import pandas as pd
import random
from datetime import datetime


class DataUtils(object):
    def __init__(
        self,
        session,
        interval=1,
        spot_numbers=-1,
        spotunderlying_numbers=-1,
        backup_interval=60,
        product_file=None,
        underlying_file=None,
        backup=False,
        new_data_folder=None,
        empty_spot_file=None,
    ):
        self.session = session
        self.spot_store = session.tables.get("Spot")
        self.spotunderlying_store = session.tables.get("Spotunderlyings")
        self.interval = interval
        self.spot_numbers = spot_numbers
        self.spotunderlying_numbers = spotunderlying_numbers
        self.count = 0
        self.backup_interval = backup_interval
        self.product_file = product_file
        self.underlying_file = underlying_file
        self.init_tuples()
        self.stop = False
        self.backup = backup
        self.dates_list = []
        self.data_folder = new_data_folder
        self.empty_spot_file = empty_spot_file

        self.trade_store = self.session.tables.get("Trades")
        self.cube = self.session.cubes["Trades"]
        self.m = self.cube.measures
        self.lvl = self.cube.levels
        self.print_stop_message = False
        self.is_running = False

    def get_portfolios(self):
        if self.is_running:
            self.pause_real_time()
            time.sleep(1.5 * self.interval)
        df = self.cube.query(
            self.m["contributors.COUNT"], levels=[self.lvl["PortfolioGroup"]]
        )
        return df.reset_index()["PortfolioGroup"].values.tolist()

    def start_real_time(self):
        if self.is_running:
            self.stop = True
            time.sleep(self.interval)
        self.stop = False
        thread_spot = threading.Thread(
            target=self.run_all,
            args=(
                lambda: self.stop,
                lambda: self.backup,
            ),
        )
        thread_spot.start()

    def pause_real_time(self, print_stop_message=False):
        self._print_stop_message = print_stop_message
        self.stop = True

    def start_backup(self):
        self.backup = True

    def pause_backup(self):
        self.backup = False

    def init_tuples(self):
        spot_df = pd.read_csv(self.product_file)
        self.product_tuples = []
        for raw in spot_df.values:
            self.product_tuples.append(
                [
                    datetime.strptime(raw[0], "%Y-%m-%dT%H:%M:%S"),
                    raw[1],
                    raw[2],
                    raw[2],
                    raw[3],
                ]
            )
        self.underlying_tuples = []
        spotunderlying_df = pd.read_csv(self.underlying_file)
        for raw in spotunderlying_df.values:
            self.underlying_tuples.append(
                [datetime.strptime(raw[0], "%Y-%m-%dT%H:%M:%S"), raw[1], raw[2]]
            )

    def change_files(self, product_file, underlying_file):
        self.pause_real_time()
        time.sleep(1.5 * self.interval)
        self.product_file = product_file
        self.underlying_file = underlying_file
        self.init_tuples()

    def run_all(self, stop, backup):
        """Method that runs forever"""
        while True:
            self.is_running = True
            product_tuples_ids = random.sample(
                range(len(self.product_tuples)), self.spot_numbers
            )
            underlying_tuples_ids = random.sample(
                range(len(self.underlying_tuples)), self.spotunderlying_numbers
            )

            for i in product_tuples_ids:
                raw = self.product_tuples[i]
                if random.gauss(0, 1) > 1:
                    limit_down = raw[3]
                    limit_up = raw[4]
                    rt_price = raw[2] + (limit_up - limit_down) * random.gauss(0, 0.02)
                    if (rt_price < limit_down) | (rt_price > limit_up):
                        rt_price = (limit_down + limit_up) / 2
                    raw[2] = rt_price
                self.product_tuples[i] = raw

            for i in underlying_tuples_ids:
                raw = self.underlying_tuples[i]
                if random.gauss(0, 1) > 1:
                    raw[2] = raw[2] * (1 + random.gauss(0, 0.001))
                self.underlying_tuples[i] = raw

            new_product_tuples = [
                tuple(self.product_tuples[i][0:3]) for i in product_tuples_ids
            ]
            new_underlying_tuples = [
                tuple(self.underlying_tuples[i][0:3]) for i in underlying_tuples_ids
            ]
            # Ingesting tuples
            with self.session.start_transaction():
                self.spot_store.append(*new_product_tuples)
                self.spotunderlying_store.append(*new_underlying_tuples)

            # Thread Management
            if stop():
                if self.print_stop_message:
                    print("Spot producer has been stopped")
                self.print_stop_message = False
                self.is_running = False
                break
            time.sleep(self.interval)
            # Backup management
            self.count = self.count + 1
            if self.count % self.backup_interval == 0 and backup():
                branch_time_name = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.dates_list.append(branch_time_name)
                if len(self.dates_list) > 10:
                    self.session.delete_scenario(self.dates_list[0])
                    del self.dates_list[0]
                self.spot_store.scenarios[branch_time_name].load_csv(
                    self.empty_spot_file
                )

    def load_new_date(self, as_of_date):
        self.pause_real_time()
        time.sleep(1.5 * self.interval)

        date_file_name = as_of_date.strftime("%Y%m%d_%H")
        date_pandas = as_of_date.replace(hour=9).strftime("%Y-%m-%d %H:%M:%S")

        df_product = pd.read_csv(
            self.data_folder + "ProductDetails/products_" + date_file_name + ".csv"
        )
        df_underlying = pd.read_csv(
            self.data_folder
            + "UnderlyingDetails/underlyingDetails_"
            + date_file_name
            + ".csv"
        )
        df_product["AsOfDate"] = date_pandas
        df_underlying["AsOfDate"] = date_pandas
        df_product.rename(
            columns={"Spot Product": "Spot Product Realtime"}, inplace=True
        )
        df_underlying.rename(
            columns={"Spot Underlying": "Spot Underlying Realtime"}, inplace=True
        )
        # Load new date (need the real time to be stopped)
        spot_store = self.session.tables.get("Spot")
        spotunderlying_store = self.session.tables.get("Spotunderlyings")

        products_store = self.session.tables.get("Productdetails")
        underlying_store = self.session.tables.get("Underlyingdetails")
        decomposition_store = self.session.tables.get("Decomposition")
        trade_store = self.session.tables.get("Trades")

        # Load new date (need the real time to be stopped)
        with self.session.start_transaction():
            products_store.load_csv(
                self.data_folder + "ProductDetails/*.csv", array_separator=";"
            )
            underlying_store.load_csv(self.data_folder + "UnderlyingDetails/*.csv")
            spot_store.load_csv(self.data_folder + "Spot/*.csv")
            spotunderlying_store.load_csv(self.data_folder + "SpotUnderlyings/*.csv")
            decomposition_store.load_csv(self.data_folder + "Decomposition/*.csv")
            trade_store.load_csv(self.data_folder + "Trades/*.csv")

        # Prepare realtime
        self.change_files(
            product_file=self.data_folder
            + "Realtime/spotProductExtremas_"
            + date_file_name
            + ".csv",
            underlying_file=self.data_folder
            + "Realtime/spotUnderlying_"
            + date_file_name
            + ".csv",
        )
        print("Loaded new date")

    def get_trade_values(self, trade_ids):
        if self.is_running == True:
            self.pause_real_time()
            time.sleep(1.5 * self.interval)
        columns = self.trade_store.columns
        measure_list = []
        lvl_list = []
        for column in columns:
            if self.m.__contains__(column):
                measure_list.append(self.m[column])
            if self.lvl.__contains__(column):
                lvl_list.append(self.lvl[column])
        result = self.cube.query(
            measure_list[0],
            levels=lvl_list,
            filter=(self.lvl["TradeId"].isin(*trade_ids)),
        )
        result = result.reset_index()
        result = result.astype({"NewTrade": bool})
        result["AsOfDate"] = pd.to_datetime(result["AsOfDate"], format="%Y-%m-%dT%H:%M")
        return result

    def load_trades(self, trade_values):
        if self.is_running == True:
            self.pause_real_time()
            time.sleep(1.5 * self.interval)
        self.trade_store.load_pandas(trade_values)

    def load_underlyings(self, underlying_values, branch):
        if self.is_running == True:
            self.pause_real_time()
            time.sleep(1.5 * self.interval)
        self.session.tables["Spotunderlyings"].scenarios[branch].load_pandas(
            underlying_values
        )
