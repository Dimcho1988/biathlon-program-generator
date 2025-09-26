def compute_cs(tt_results):
    """
    Изчислява Critical Speed от два теста.
    tt_results: [{'distance': m, 'time': s}, ...]
    """
    d1, d2 = tt_results
    cs = (d2["distance"] - d1["distance"]) / (d2["time"] - d1["time"])  # m/s
    return {"cs": cs * 3.6}  # km/h
