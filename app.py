import pandas as pd
from cs_model import compute_cs
from acwr_model import compute_acwr
from generator import generate_plan

# 1. Демонстрационни тестови данни (две TT за CS)
tt_results = [
    {"distance": 1200, "time": 240},   # 1200m за 4:00
    {"distance": 3000, "time": 720}    # 3000m за 12:00
]

# 2. Базов план (Week, Day, Zone, Minutes)
base_df = pd.DataFrame({
    "Week": [1,1,1,1,1],
    "Day": ["Mon","Tue","Wed","Thu","Fri"],
    "Zone": [1,2,3,4,5],
    "Minutes": [60,50,45,40,30]
})

# 3. Изчисляваме модели
cs = compute_cs(tt_results)["cs"]
acwr = compute_acwr(base_df)["acwr"]

# 4. Генерираме план
plan = generate_plan(cs, acwr, base_df)

# 5. Показваме резултати
print(f"Critical Speed: {cs:.2f} km/h")
print(f"ACWR: {acwr:.2f}")
print("\nGenerated plan:\n", plan)
