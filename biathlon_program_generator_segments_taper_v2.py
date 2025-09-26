
import pandas as pd
import numpy as np
import random
from datetime import timedelta

# ===============================
# Helpers to read base & find patterns
# ===============================
def load_base(base_path):
    df = pd.read_excel(base_path)
    # Normalize columns
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
    zone_cols = [c for c in df.columns if c.lower().startswith("zone ") or c.lower()=="strength"]
    # Fill NaNs with 0 for zones
    for c in zone_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    # Detect starts if present
    if "Type" in df.columns:
        df["Is_Start"] = df["Type"].fillna("").str.contains("Start", case=False, regex=True)
        # Standardize type labels
        def _map_type(x):
            t = str(x).lower()
            if "main" in t or "основ" in t: return "Main start"
            if "control" in t or "контрол" in t: return "Control start"
            return ""
        df["Start_type"] = df["Type"].apply(_map_type)
    else:
        df["Is_Start"] = False
        df["Start_type"] = ""
    # Day_index (optional)
    if "Day_index" not in df.columns:
        df["Day_index"] = (df["Date"] - df["Date"].min()).dt.days + 1
    return df

def _normalize_starts(starts):
    norm = []
    for s in starts:
        d = pd.to_datetime(s.get("date"))
        t_raw = str(s.get("type","")).strip().lower()
        if "main" in t_raw or "основ" in t_raw:
            t = "Main start"
        elif "control" in t_raw or "контрол" in t_raw:
            t = "Control start"
        else:
            t = "Control start"
        norm.append({"date": d.normalize(), "type": t})
    if norm:
        df_s = pd.DataFrame(norm).sort_values("date").reset_index(drop=True)
        # keep main if same date
        df_s = df_s.sort_values(["date","type"], key=lambda c: c.map({"Main start":0,"Control start":1}) if c.name=="type" else c)
        df_s = df_s.drop_duplicates(subset=["date"], keep="first")
        return df_s.to_dict(orient="records")
    return norm

def _first_last_main_dates_from_norm(norm_starts):
    main_dates = [s["date"] for s in norm_starts if s["type"]=="Main start"]
    if not main_dates:
        return None, None
    return min(main_dates), max(main_dates)

def _week_index(df, start_date):
    return ((df["Date"] - start_date).dt.days // 7).astype(int)

# ===============================
# Patterns derived from base file
# ===============================
def derive_taper_profile(base_df, window_days=7):
    """Average last-N-days (per offset) zone distribution & total minutes from base before any starts."""
    zone_cols = [c for c in base_df.columns if c.lower().startswith("zone ") or c.lower()=="strength"]
    starts = base_df.loc[base_df["Is_Start"], "Date"].sort_values().tolist()
    if not starts:
        # default conservative taper: totals and proportions
        offsets = range(1, window_days+1)
        totals = {k: float(60 - (k-1)*5) for k in offsets}  # decreasing totals
        # proportions: Z1↑, Z3-5↓, Strength↓
        props = {k: {"Zone 1":0.55, "Zone 2":0.25, "Zone 3":0.12, "Zone 4":0.06, "Zone 5":0.02, "Strength":0.0} for k in offsets}
        return {"totals": totals, "props": props}

    recs = []
    for d in starts:
        s = base_df[(base_df["Date"] >= d - timedelta(days=window_days)) & (base_df["Date"] < d)].copy()
        if s.empty: 
            continue
        s["offset"] = (d - s["Date"]).dt.days  # 1..7
        # daily sums & proportions
        s["Day_total"] = s[zone_cols].sum(axis=1)
        for z in zone_cols:
            s[z+"_prop"] = np.where(s["Day_total"]>0, s[z]/s["Day_total"], 0.0)
        recs.append(s)
    if not recs:
        return derive_taper_profile(base_df, window_days)  # fallback

    T = pd.concat(recs, ignore_index=True)
    # average per offset
    totals = T.groupby("offset")["Day_total"].mean().to_dict()
    props = {}
    for k, g in T.groupby("offset"):
        dct = {}
        for z in ["Zone 1","Zone 2","Zone 3","Zone 4","Zone 5","Strength"]:
            if z in g.columns:
                dct[z] = float(g[z+"_prop"].mean())
        # ensure props sum to 1.0
        ssum = sum(dct.values())
        if ssum <= 0:
            dct = {"Zone 1":0.6,"Zone 2":0.25,"Zone 3":0.1,"Zone 4":0.04,"Zone 5":0.01,"Strength":0.0}
        else:
            for z in dct:
                dct[z] = dct[z] / ssum
        props[int(k)] = dct
    # fill any missing offsets
    for k in range(1, window_days+1):
        if k not in props:
            props[k] = {"Zone 1":0.6,"Zone 2":0.25,"Zone 3":0.1,"Zone 4":0.04,"Zone 5":0.01,"Strength":0.0}
        if k not in totals:
            totals[k] = 60.0 - (k-1)*5.0
    return {"totals": {int(k): float(v) for k,v in totals.items()}, "props": props}

def derive_focus_pattern(base_df):
    """Estimate 'focus day' intensity pattern from base: how much Z4+Z5 concentrates on peak day vs others."""
    zone_cols = [c for c in base_df.columns if c in ["Zone 1","Zone 2","Zone 3","Zone 4","Zone 5","Strength"]]
    if "Date" not in base_df.columns:
        return {"focus_mult_hi":1.5, "focus_mult_lo":0.7}
    widx = _week_index(base_df, base_df["Date"].min())
    df = base_df.copy()
    df["Week"] = widx
    df["HI"] = df.get("Zone 4",0) + df.get("Zone 5",0)
    ratios = []
    for w, g in df.groupby("Week"):
        if g.empty: continue
        if g["HI"].sum() <= 0: continue
        hi_day = g["HI"].idxmax()
        max_val = g.loc[hi_day, "HI"]
        other_sum = g["HI"].sum() - max_val
        if other_sum > 0:
            ratios.append( max_val / (other_sum / max(1, (len(g)-1))) )
    if not ratios:
        return {"focus_mult_hi":1.5, "focus_mult_lo":0.7}
    r = float(np.clip(np.nanmean(ratios), 1.2, 2.0))
    # map ratio into multipliers
    hi = min(1.2 + (r-1.2)*0.5, 1.7)
    lo = max(1.0 - (hi-1.0)*0.6, 0.6)
    return {"focus_mult_hi": hi, "focus_mult_lo": lo}

def derive_prep_tercile_multipliers(base_df):
    """Relative emphasis by terciles in preparatory phase (before first main)."""
    if "Date" not in base_df.columns:
        return {"early":{"Z1":1.05,"Z2":1.03,"Z3":0.95,"Z4":0.9,"Z5":0.85,"S":1.0},
                "mid":{"Z1":0.98,"Z2":1.02,"Z3":1.05,"Z4":1.08,"Z5":1.05,"S":1.05},
                "late":{"Z1":0.95,"Z2":1.0,"Z3":1.08,"Z4":1.12,"Z5":1.10,"S":1.05}}
    starts = base_df.loc[base_df["Start_type"]=="Main start","Date"].sort_values().tolist()
    if not starts:
        return {"early":{"Z1":1.05,"Z2":1.03,"Z3":0.95,"Z4":0.9,"Z5":0.85,"S":1.0},
                "mid":{"Z1":0.98,"Z2":1.02,"Z3":1.05,"Z4":1.08,"Z5":1.05,"S":1.05},
                "late":{"Z1":0.95,"Z2":1.0,"Z3":1.08,"Z4":1.12,"Z5":1.10,"S":1.05}}
    first_main = starts[0]
    prep = base_df[base_df["Date"] < first_main].copy()
    if prep.empty:
        return {"early":{"Z1":1.05,"Z2":1.03,"Z3":0.95,"Z4":0.9,"Z5":0.85,"S":1.0},
                "mid":{"Z1":0.98,"Z2":1.02,"Z3":1.05,"Z4":1.08,"Z5":1.05,"S":1.05},
                "late":{"Z1":0.95,"Z2":1.0,"Z3":1.08,"Z4":1.12,"Z5":1.10,"S":1.05}}
    n = len(prep)
    terciles = np.array_split(prep.index.values, 3)
    def zone_sum(idx):
        s = prep.loc[idx, ["Zone 1","Zone 2","Zone 3","Zone 4","Zone 5","Strength"]].sum()
        return s
    sums = [zone_sum(t) for t in terciles if len(t)>0]
    if len(sums)<3:
        return {"early":{"Z1":1.05,"Z2":1.03,"Z3":0.95,"Z4":0.9,"Z5":0.85,"S":1.0},
                "mid":{"Z1":0.98,"Z2":1.02,"Z3":1.05,"Z4":1.08,"Z5":1.05,"S":1.05},
                "late":{"Z1":0.95,"Z2":1.0,"Z3":1.08,"Z4":1.12,"Z5":1.10,"S":1.05}}
    tot = sum(sums)
    props = [s / tot for s in sums]
    # Convert to intuitive multipliers around 1.0 by comparing each zone prop to mean
    mean_prop = sum(props) / 3.0
    mult = []
    for p in props:
        m = {}
        for z_key, z_name in zip(["Z1","Z2","Z3","Z4","Z5","S"], ["Zone 1","Zone 2","Zone 3","Zone 4","Zone 5","Strength"]):
            base = p.get(z_name, 1/6)
            avg = mean_prop.get(z_name, 1/6)
            # gentle scaling around 1
            m[z_key] = float(np.clip(0.8 + (base/avg)*0.2, 0.85, 1.15))
        mult.append(m)
    return {"early": mult[0], "mid": mult[1], "late": mult[2]}

# ===============================
# Core adjustments
# ===============================
def assign_week_theme(df, start_date):
    weeks = ((df["Date"] - start_date).dt.days // 7).astype(int)
    themes = []
    for w in weeks:
        if w % 4 == 3:
            themes.append("recovery")
        elif w % 3 == 1:
            themes.append("strength")
        else:
            themes.append("endurance")
    return pd.Series(themes, index=df.index)

def adjust_by_theme(df, themes):
    out = df.copy()
    for idx, theme in themes.items():
        if theme == "endurance":
            for c in ["Zone 1","Zone 2"]:
                if c in out.columns:
                    out.loc[idx, c] = out.loc[idx, c] * 1.05
        elif theme == "strength":
            if "Strength" in out.columns:
                out.loc[idx, "Strength"] = out.loc[idx, "Strength"] * 1.2
        elif theme == "recovery":
            for col in ["Zone 1","Zone 2","Zone 3","Zone 4","Zone 5","Strength"]:
                if col in out.columns:
                    out.loc[idx, col] = out.loc[idx, col] * 0.5
    return out

def enforce_focus_days(df, focus_mult_hi=1.5, focus_mult_lo=0.7):
    """Concentrate Z4/Z5 on 1–2 days per week like in real files."""
    out = df.copy()
    out["Week"] = ((out["Date"] - out["Date"].min()).dt.days // 7).astype(int)
    for w, g in out.groupby("Week"):
        if g.empty: continue
        idxs = g.index.tolist()
        # skip if this is a recovery themed week (majority labeled recovery)
        if "Week_theme" in out.columns:
            if (g["Week_theme"]=="recovery").sum() >= len(g)/2:
                continue
        # choose 2 focus days deterministically: middle and second-to-last
        f1 = idxs[len(idxs)//2]
        f2 = idxs[-2] if len(idxs) >= 2 else idxs[-1]
        # apply multipliers
        for i in idxs:
            if i in [f1, f2]:
                if "Zone 4" in out.columns:
                    out.loc[i, "Zone 4"] *= focus_mult_hi
                if "Zone 5" in out.columns:
                    out.loc[i, "Zone 5"] *= focus_mult_hi
            else:
                if "Zone 4" in out.columns:
                    out.loc[i, "Zone 4"] *= focus_mult_lo
                if "Zone 5" in out.columns:
                    out.loc[i, "Zone 5"] *= focus_mult_lo
    out.drop(columns=["Week"], inplace=True)
    return out

def taper_apply_profile(df, starts, profile, vo2_scale=1.0, window_days=7):
    """Override the last N days before each start to follow base taper profile exactly (scaled by VO2)."""
    out = df.copy()
    for st in starts:
        d = pd.to_datetime(st["date"]).normalize()
        for k in range(1, window_days+1):
            day = d - timedelta(days=k)
            mask = out["Date"].dt.normalize() == day
            if not mask.any():
                continue
            target_total = profile["totals"].get(k, 60.0) * vo2_scale
            props = profile["props"].get(k, {})
            # write zones
            for z_key in ["Zone 1","Zone 2","Zone 3","Zone 4","Zone 5","Strength"]:
                if z_key in out.columns:
                    out.loc[mask, z_key] = target_total * props.get(z_key, 0.0)
    return out

def enforce_start_day_rules(df, starts):
    """On start days: Zone 5 ≈ 10–15 min; keep others minimal (short warmup/cooldown)."""
    out = df.copy()
    for st in starts:
        d = pd.to_datetime(st["date"]).normalize()
        m = out["Date"].dt.normalize() == d
        if not m.any(): 
            continue
        # set Z5
        z5 = float(np.random.uniform(10.0, 15.0))
        if "Zone 5" in out.columns:
            out.loc[m, "Zone 5"] = z5
        # light Z4 (3–6), some Z1 cool/warm (15–30), others near 0
        if "Zone 4" in out.columns:
            out.loc[m, "Zone 4"] = float(np.random.uniform(3.0, 6.0))
        if "Zone 1" in out.columns:
            out.loc[m, "Zone 1"] = float(np.random.uniform(15.0, 30.0))
        for c in ["Zone 2","Zone 3","Strength"]:
            if c in out.columns:
                out.loc[m, c] = float(np.random.uniform(0.0, 5.0))
        # mark
        if "Is_Start" in out.columns:
            out.loc[m, "Is_Start"] = True
        if "Start_type" in out.columns and out.loc[m, "Start_type"].eq("").any():
            out.loc[m, "Start_type"] = st.get("type","")
        if "Type" in out.columns:
            out.loc[m, "Type"] = st.get("type","")
    return out

def _finalize_phases_and_trim(df, starts):
    nstarts = _normalize_starts(starts)
    if not isinstance(df["Date"].dtype, pd.DatetimeTZDtype):
        df["Date"] = pd.to_datetime(df["Date"])

    # clear start flags then set exact matches
    df["Is_Start"] = False
    df["Start_type"] = ""
    s_map = {s["date"].normalize(): s["type"] for s in nstarts}
    mask = df["Date"].dt.normalize().isin(s_map.keys())
    df.loc[mask, "Is_Start"] = True
    df.loc[mask, "Start_type"] = df.loc[mask, "Date"].dt.normalize().map(s_map)

    # phases
    first_main, last_main = _first_last_main_dates_from_norm(nstarts)
    if first_main is not None:
        df["Phase"] = np.where(df["Date"] < first_main, "Preparatory", "Competition")
    else:
        df["Phase"] = "Preparatory"

    # TRIM to last main
    if last_main is not None:
        df = df[df["Date"] <= last_main].copy()

    # Backward-compatible 'Type'
    if 'Type' not in df.columns:
        df['Type'] = ''
    df.loc[df['Is_Start'], 'Type'] = df.loc[df['Is_Start'], 'Start_type']

    return df

# ===============================
# PUBLIC: generate_program
# ===============================
def generate_program(vo2max, starts, seed=42, scale_base_vo2=65, base_path=None):
    random.seed(seed)
    np.random.seed(seed)

    # base & stats
    base_df = load_base(base_path)
    taper_profile = derive_taper_profile(base_df, window_days=7)
    focus_pattern = derive_focus_pattern(base_df)
    tercile_mult = derive_prep_tercile_multipliers(base_df)

    # start from base calendar skeleton (keeping dates & baseline structure)
    df = base_df.copy()

    # scale zones by VO2
    vo2_scale = float(vo2max) / float(scale_base_vo2)
    for col in ["Zone 1","Zone 2","Zone 3","Zone 4","Zone 5","Strength"]:
        if col in df.columns:
            df[col] = df[col] * vo2_scale

    # themes
    themes = assign_week_theme(df, df["Date"].min())
    df = adjust_by_theme(df, themes)
    df["Week_theme"] = themes.values

    # Focus days (concentrate HI work weekly)
    df = enforce_focus_days(df, focus_mult_hi=focus_pattern["focus_mult_hi"],
                               focus_mult_lo=focus_pattern["focus_mult_lo"])

    # Phase split & trim to last main
    df = _finalize_phases_and_trim(df, starts)

    # Preparatory terciles emphasis
    if (df["Phase"]=="Preparatory").any():
        first_main_date = df.loc[df["Phase"]=="Competition","Date"].min()
        prep_mask = df["Phase"]=="Preparatory"
        prep_idx = df[prep_mask].index.tolist()
        if prep_idx:
            # split indices into 3 parts
            parts = np.array_split(prep_idx, 3)
            for i, key in enumerate(["early","mid","late"]):
                mult = tercile_mult[key]
                idxs = parts[i] if i < len(parts) else []
                for z_key, col in [("Z1","Zone 1"),("Z2","Zone 2"),("Z3","Zone 3"),("Z4","Zone 4"),("Z5","Zone 5"),("S","Strength")]:
                    if col in df.columns and len(idxs)>0:
                        df.loc[idxs, col] = df.loc[idxs, col] * mult[z_key]

    # Taper: strictly follow base 7-day profile before each start
    nstarts = _normalize_starts(starts)
    df = taper_apply_profile(df, nstarts, taper_profile, vo2_scale=vo2_scale, window_days=7)

    # Enforce start day rules (Zone 5 ≈ 10–15 min)
    df = enforce_start_day_rules(df, nstarts)

    # Days_to_next_start + Start_type forward fill
    df["Days_to_next_start"] = np.nan
    df["Start_type"] = df["Start_type"].fillna("")
    future_starts = [pd.to_datetime(s["date"]).normalize() for s in nstarts]
    future_types  = [s["type"] for s in nstarts]
    for i, row in df.iterrows():
        deltas = [(d - row["Date"].normalize()).days for d in future_starts if (d - row["Date"].normalize()).days >= 0]
        if deltas:
            dmin = min(deltas)
            df.at[i, "Days_to_next_start"] = dmin

    # Ensure non-negative & small rounding
    for c in ["Zone 1","Zone 2","Zone 3","Zone 4","Zone 5","Strength"]:
        if c in df.columns:
            df[c] = df[c].clip(lower=0.0)
            df[c] = np.round(df[c], 1)

    return df
