def generate_plan(cs: float, acwr: float, base_df):
    """
    Генерира примерен план на база CS и ACWR.
    """
    plan = base_df.copy()
    plan["Target_speed"] = plan["Zone"].map({
        1: (0.6, 0.75),
        2: (0.76, 0.80),
        3: (0.81, 0.88),
        4: (0.89, 0.95),
        5: (0.96, 1.05)
    }).apply(lambda rng: f"{rng[0]*cs:.1f}-{rng[1]*cs:.1f} km/h")
    plan["ACWR_flag"] = "OK" if acwr and acwr < 1.5 else "⚠ High Load"
    return plan

