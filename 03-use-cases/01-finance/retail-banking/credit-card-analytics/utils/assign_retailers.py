# Assign Retailer IDs to Card Brand, Card Type combinations
cc_dict = {
    "Amex Credit": [1, 2, 3, 4],
    "Discover Credit": [5, 6],
    "Mastercard Credit": [7, 8, 9, 10],
    "Mastercard Debit": [11, 12, 13, 14, 15, 16],
    "Mastercard Debit (Prepaid)": [17, 18, 19],
    "Visa Credit": [20, 21, 22, 23],
    "Visa Debit": [24, 25, 26, 27, 28],
    "Visa Debit (Prepaid)": [29, 30],
}

def assign_retailers(cc_df, cc_combinations_df):
    for user in cc_df["User"].unique():
        df = cc_df.loc[cc_df["User"] == user].sort_values(by=["Card Brand", "Card Type"])
        prev_row = None
    
        for index, row in df.iterrows():
            cc_input = row["Card Brand"] + " " + row["Card Type"]
            distinct_count = cc_combinations_df.loc[
                (cc_combinations_df["User"] == user)
                & (cc_combinations_df["Card Brand"] == row["Card Brand"])
                & (cc_combinations_df["Card Type"] == row["Card Type"])
            ]["size"].values[0]
    
            if prev_row is None:
                # print("FIRST ROW AND NEW CARD FOR USER")
                num_counter = 0
                # print(f"  User {user} has a {cc_input}, and has {distinct_count} distinct cards")
                assignment = cc_dict[cc_input][num_counter]
                # print(f"    Assigning to Retailer ID... {assignment}")
                cc_df.loc[index, "Retailer ID"] = assignment
                prev_row = row
    
            else:
                if str(prev_row["Card Brand"]) == str(row["Card Brand"]) and str(
                    prev_row["Card Type"]
                ) == str(row["Card Type"]):
                    # print("SAME CARD AS PREVIOUS ROW")
                    num_counter += 1
                    # print(f"  User {user} has a {cc_input}, which is same as above, and has {distinct_count} distinct cards")
                    assignment = cc_dict[cc_input][num_counter]
                    # print(f"    Assigning to Retailer ID... {assignment}")
                    cc_df.loc[index, "Retailer ID"] = assignment
                    prev_row = row
    
                else:
                    # print("NEW CARD FOR SAME USER")
                    num_counter = 0
                    # print(f"  User {user} has a {cc_input}, and has {distinct_count} distinct cards")
                    assignment = cc_dict[cc_input][num_counter]
                    # print(f"    Assigning to Retailer ID... {assignment}")
                    cc_df.loc[index, "Retailer ID"] = assignment
                    prev_row = row

    return cc_df