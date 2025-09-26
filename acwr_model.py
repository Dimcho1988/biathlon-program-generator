import pandas as pd

def compute_acwr(df: pd.DataFrame):
    """
    Изчислява ACWR от минутите за последните 7 и 28 дни.
    df: DataFrame с колона 'Minutes'
    """
    load7 = df["Minutes"].tail(7).sum()
    load28 = df["Minutes"].tail(28).sum()
    acwr = load7 / (load28 / 4) if load28 else None
    return {"acwr": acwr}

