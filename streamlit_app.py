import streamlit as st
import pandas as pd
import io, tempfile
from typing import List, Dict

# ВАЖНО: файлът с генератора трябва да е в същата папка и да се казва така:
from biathlon_program_generator_segments_taper_v2 import generate_program

st.set_page_config(page_title="onFlows Biathlon Generator", page_icon="🏔️", layout="wide")
st.title("🏔️ Генератор на тренировъчни програми (биатлон) — разширена версия")

st.markdown(
    "Въведи параметри, качи **base_calendar.xlsx** и натисни **Генерирай програма**. "
    "Ще получиш разширен Excel с листове: `Program`, `WeekPlan`, `Notes`, `Methods`."
)

# ---------------- ВХОД ----------------
col1, col2 = st.columns([1,1])
with col1:
    vo2max = st.number_input("VO₂max (ml/kg/min)", min_value=30.0, max_value=95.0, value=65.0, step=0.5)
with col2:
    seed = st.number_input("Seed (за възпроизводимост)", min_value=0, value=42, step=1)

st.subheader("Състезания (дата + тип)")
st.caption("Добавяй редове. Тип: Main start (основен) или Control start (контролен).")

default_rows = pd.DataFrame([{"date": pd.Timestamp.today().date(), "type": "Main start"}])
try:
    starts_df = st.data_editor(
        default_rows,
        num_rows="dynamic",
        column_config={
            "date": st.column_config.DateColumn("Дата"),
            "type": st.column_config.SelectboxColumn("Тип", options=["Main start", "Control start"]),
        },
    )
except Exception:
    starts_df = st.data_editor(default_rows, num_rows="dynamic")

base_file = st.file_uploader("Качи базовия Excel шаблон (напр. base_calendar.xlsx)", type=["xlsx"])
out_name = st.text_input("Име на изходния файл (без разширение)", value="generated_program_extended")

gen_btn = st.button("Генерирай програма", type="primary")

# ---------------- ПОМОЩНИ ФУНКЦИИ ----------------
def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
    if "Day" not in df.columns:
        if "Date" in df.columns:
            df["Day"] = df["Date"].dt.day_name()
        else:
            df["Day"] = ""
    if "Week" not in df.columns:
        if "Date" in df.columns:
            start = df["Date"].min()
            df["Week"] = ((df["Date"] - start).dt.days // 7) + 1
        else:
            df["Week"] = 1
    return df

def augment_with_notes(df: pd.DataFrame) -> pd.DataFrame:
    zone_to_label = {1: "КР", 2: "АР1", 3: "АР2", 4: "СР", 5: "АНП"}
    method_by_zone = {
        1: "Зона 1 (КР): възстановителна аеробна работа, ниска интензивност, разговорно темпо.",
        2: "Зона 2 (АР1): развитие на аеробна база; дълги равномерни натоварвания.",
        3: "Зона 3 (АР2): прагова зона; контролирани интервали 6–12 мин, стабилно темпо.",
        4: "Зона 4 (СР): близо до състезателна; интервали 3–6 мин, фокус върху икономичност.",
        5: "Зона 5 (АНП): висока интензивност/VO₂max; 30“–3’ интервали с пълно възстановяване.",
    }
    if "Strength" not in df.columns:
        df["Strength"] = ""
    if "Zone" in df.columns:
        df["ZoneLabel"] = df["Zone"].apply(lambda z: zone_to_label.get(int(z), str(z)) if pd.notna(z) else "")
    else:
        df["ZoneLabel"] = ""

    def build_note(row):
        z = int(row.get("Zone", 0)) if pd.notna(row.get("Zone", None)) else 0
        mins = int(row.get("Minutes", 0)) if pd.notna(row.get("Minutes", None)) else 0
        strength = row.get("Strength", "")
        base = method_by_zone.get(z, "Описание по зона не е дефинирано.")
        extra = []
        if mins: extra.append(f"~{mins} мин.")
        if strength: extra.append(f"Сила: {strength}.")
        return f"{base} " + " ".join(extra) if extra else base

    df["Note"] = df.apply(build_note, axis=1)
    return df

# ---------------- ИЗПЪЛНЕНИЕ ----------------
if gen_btn:
    if base_file is None:
        st.error("Моля, качи базовия Excel шаблон (.xlsx).")
    else:
        # Пишем качения файл във временен път, защото генераторът иска path
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(base_file.read())
            base_path = tmp.name

        try:
            starts: List[Dict] = []
            for _, row in starts_df.iterrows():
                d = pd.to_datetime(row.get("date")).date()
                t = str(row.get("type", "Main start"))
                starts.append({"date": d.isoformat(), "type": t})

            df = generate_program(vo2max=vo2max, starts=starts, seed=seed, base_path=base_path)
            df = ensure_columns(df)

            day_order = {
                "Monday":1,"Tuesday":2,"Wednesday":3,"Thursday":4,"Friday":5,"Saturday":6,"Sunday":7,
                "Mon":1,"Tue":2,"Wed":3,"Thu":4,"Fri":5,"Sat":6,"Sun":7
            }
            df["Day_order"] = df.get("Day", "").map(day_order) if "Day" in df.columns else 8
            df = df.sort_values(["Week","Day_order","Date"], ascending=[True, True, True], na_position="last")
            df = augment_with_notes(df)

            cols = ["Week","Date","Day","Zone","ZoneLabel","Minutes","Strength","Note"]
            week_plan = df[[c for c in cols if c in df.columns]].copy()

            methods = pd.DataFrame([
                {"Zone":"КР (1)", "Method":"Възстановителни L1; дължина според общия обем."},
                {"Zone":"АР1 (2)", "Method":"Аеробна база; дълги равномерни бягания/ролки; HR 60–75% HRmax."},
                {"Zone":"АР2 (3)", "Method":"Прагова работа; 3×10' / 4×8' с 2–3' пауза; HR 81–88% HRmax."},
                {"Zone":"СР (4)", "Method":"Състезателна; 5×4' / 6×3' с 2–3' пауза; HR 89–95% HRmax."},
                {"Zone":"АНП (5)", "Method":"VO₂max; 8×1' / 12×400м; пълна почивка; >95% HRmax."},
                {"Zone":"Сила", "Method":"ОСП/ССП 2–3x седмично; избягвай преди ключови интервали."},
                {"Zone":"Стрелба", "Method":"Суха/комплексна; отделен отчет по твоя стандарт."},
            ])

            st.success("Готово! Виж прегледа и свали Excel.")
            with st.expander("Преглед на седмичния план (първите 60 реда)"):
                st.dataframe(week_plan.head(60))

            # Сваляне на Excel (много листа) без запис на диск
            from pandas import ExcelWriter
            buf = io.BytesIO()
            with ExcelWriter(buf, engine="openpyxl") as writer:
                df.drop(columns=["Day_order"], errors="ignore").to_excel(writer, index=False, sheet_name="Program")
                week_plan.to_excel(writer, index=False, sheet_name="WeekPlan")
                pd.DataFrame({"Notes":[
                    "Бележки:",
                    "- Загрявка 15–20', разпускане 10–15'.",
                    "- Контрол на умора: HRV, RPE, сутрешен пулс; избягвай натрупване на висок лактат.",
                    "- Не подреждай тежки интервали 3 последователни дни.",
                    "- Сила: ОСП/ССП според фазата; не претоварвай при висок стрес в З4–З5.",
                ]}).to_excel(writer, index=False, sheet_name="Notes")
                methods.to_excel(writer, index=False, sheet_name="Methods")
            buf.seek(0)

            fname = (out_name or "generated_program_extended").strip().replace(" ", "_") + ".xlsx"
            st.download_button(
                "📥 Изтегли разширен Excel (много листа)",
                data=buf,
                file_name=fname,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        except Exception as e:
            st.error(f"Възникна грешка: {e}")
            st.exception(e)
# ---------------- DEMO: Модели (CS & ACWR) и комбиниране ----------------
import io

st.markdown("---")
with st.expander("🧪 Модели (CS & ACWR) – демо (комбиниране)", expanded=False):
    # Импорт на твоите нови модули
    from cs_model import compute_cs
    from acwr_model import compute_acwr
    from generator import generate_plan as gen_simple_plan

    st.subheader("Critical Speed от два TT теста")
    c1, c2, c3, c4 = st.columns(4)
    d1 = c1.number_input("TT1 дистанция (м)", min_value=100, max_value=20000, value=1200, step=100)
    t1 = c2.number_input("TT1 време (сек.)",  min_value=60,  max_value=7200,  value=240,  step=10)
    d2 = c3.number_input("TT2 дистанция (м)", min_value=200, max_value=50000, value=3000, step=100)
    t2 = c4.number_input("TT2 време (сек.)",  min_value=120, max_value=14400, value=720,  step=10)

    if st.button("Изчисли CS", key="btn_cs"):
        cs_calc = compute_cs([{"distance": d1, "time": t1}, {"distance": d2, "time": t2}])["cs"]
        st.session_state["demo_cs"] = cs_calc

    cs_val = st.session_state.get("demo_cs", None)
    if cs_val:
        st.metric("Critical Speed", f"{cs_val:.2f} km/h")

    st.subheader("ACWR от история (Excel с колона 'Minutes')")
    acwr_file = st.file_uploader("Качи история (.xlsx)", type=["xlsx"], key="acwr_hist")
    acwr_val = None
    if acwr_file:
        hist_df = pd.read_excel(acwr_file)
        if "Minutes" in hist_df.columns:
            acwr_val = compute_acwr(hist_df)["acwr"]
            st.metric("ACWR", f"{acwr_val:.2f}" if acwr_val else "n/a")
            st.caption("Показваме последните 28 реда (ако има):")
            st.dataframe(hist_df.tail(28))
        else:
            st.error("Файлът трябва да съдържа колона 'Minutes'.")

    st.subheader("Комбиниране CS + ACWR → демо план")
    if cs_val and acwr_val is not None:
        demo_base = pd.DataFrame({
            "Week": [1,1,1,1,1],
            "Day":  ["Mon","Tue","Wed","Thu","Fri"],
            "Zone": [1,2,3,4,5],
            "Minutes": [60,50,45,40,30]
        })
        plan = gen_simple_plan(cs_val, acwr_val, demo_base)
        st.dataframe(plan)

        buf = io.BytesIO()
        plan.to_excel(buf, index=False)
        buf.seek(0)
        st.download_button(
            "📥 Свали демо плана (Excel)",
            data=buf,
            file_name="demo_plan_cs_acwr.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.caption("Въведи CS (бутон „Изчисли CS“) и качи Excel история за ACWR, за да видиш комбиниран план.")
