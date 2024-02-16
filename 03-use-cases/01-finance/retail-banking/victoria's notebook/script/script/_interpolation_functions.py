import atoti as tt

find_index_function = tt._udaf_utils.java_function.CustomJavaFunction(
    [("realTimeSpot", tt.type.DOUBLE), ("spotVector", tt.type.DOUBLE_ARRAY)],
    method_name="find_index",
    method_body="""
        int result = Arrays.binarySearch(spotVector.toDoubleArray(), realTimeSpot);
		if (result < -1) {
			result = (Math.abs(result) - 2);
		}
        result = Math.min(Math.max(0, result), spotVector.size() - 2);
		return result;
        """,
    output_type=tt.type.INT,
    additional_imports=["java.util.Arrays"],
)
