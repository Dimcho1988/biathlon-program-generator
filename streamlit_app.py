# Create an updated Streamlit app that adds weekly plan, notes, and methods (BG terminology).
from pathlib import Path
from textwrap import dedent

code = dedent('''
import streamlit as st
import pandas as pd
import io
import tempfile
from typing import List, Dict

# Импорт на твоя генератор (трябва да е в същата папка в репото)
from biathlon_program_generator_segments_taper_v2 import generate_program

st.set_page_config(page_title="onFlows Biathlon Generator", page_icon="🏔️", layout="wide")
st.title("🏔️ Генератор на тренировъчни програми (биатлон) — разширена версия")

st.markdown(
    "Въведи параметри, качи **base_calendar.xlsx** и натисни **Генерирай програма**. "
    "Ще получиш разширен Excel с няколко листа: `Program`, `WeekPlan`, `Notes`, `Methods`."
)

# ---------- ВХОД ----------
col1, col2 = st.columns([1,1])
with col1:
    vo2max = st.number_input("VO₂max (ml/kg/min)", min_value=30.0, max_value=95.0, value=65.0, step=0.5)
with col2:
    seed = st.number_input("Seed (за възпроизводимост)", min_value=0, value=42, step=1)

st.subheader("Състезания (дата + тип)")
st.caption("Добавяй редове. Тип: Main start (основен) или Control start (контролен).")

default_rows = pd.DataFrame([
    {"date": pd.Timestamp.today().date(), "type": "Main start"}
])

# За по-стар Streamlit правим защитен fall-back
try:
    starts_df = st.data_editor(
        default_rows,
        num_rows="dynamic",
        column_config={
            "date": st.column_config.DateColumn("Дата"),
            "type": st.column_config.SelectboxColumn("Тип", options=["Main start", "Control start"])
        }
    )
except Exception:
    starts_df = st.data_editor(default_rows, num_rows="dynamic")

base_file = st.file_uploader("Качи базовия Excel шаблон (напр. base_calendar.xlsx)", type=["xlsx"])
out_name = st.text_input("Име на изходния файл (без разширение)", value="generated_program_extended")

gen_btn = st.button("Генерирай програма", type="primary")

# ---------- ЛОГИКА ----------

def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    # Пре-парсване на Date
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
    else:
        # ако няма Date, опитваме да построим от Week/Day, но в общия случай generator очаква Date в base
        # тук само създаваме placeholder (ще е валиден ако generator вече е създал Date)
        pass

    # Day (Mon..Sun)
    if "Day" not in df.columns:
        if "Date" in df.columns:
            df["Day"] = df["Date"].dt.day_name()
        else:
            df["Day"] = ""

    # Week (1..N)
    if "Week" not in df.columns:
        if "Date" in df.columns:
            start = df["Date"].min()
            df["Week"] = ((df["Date"] - start).dt.days // 7) + 1
        else:
            df["Week"] = 1

    return df

def augment_with_notes(df: pd.DataFrame) -> pd.DataFrame:
    # Мапинг на зони към твоята терминология
    # 1: КР, 2: АР1, 3: АР2, 4: СР, 5: АНП
    zone_to_label = {1: "КР", 2: "АР1", 3: "АР2", 4: "СР", 5: "АНП"}

    method_by_zone = {
        1: "Зона 1 (КР): възстановителна аеробна работа, ниска интензивност, разговорно темпо.",
        2: "Зона 2 (АР1): развитие на аеробна база; дълги равномерни натоварвания.",
        3: "Зона 3 (АР2): прагова зона; контролирани интервали 6–12 мин, стабилно темпо.",
        4: "Зона 4 (СР): близо до състезателна; интервали 3–6 мин, фокус върху икономичност.",
        5: "Зона 5 (АНП): висока интензивност/VO₂max; 30\"–3' интервали с пълно възстановяване.",
    }

    # Силова компонента – по избор може да дойде от генератора; тук добавяме default колона ако липсва
    if "Strength" not in df.columns:
        df["Strength"] = ""  # пример: "ОСП" / "ССП" / ""

    # Създаваме четим етикет за зона
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
        if mins:
            extra.append(f"~{mins} мин.")
        if strength:
            extra.append(f"Сила: {strength}.")
        extra_txt = " " + " ".join(extra) if extra else ""
        return f"{base}{extra_txt}"

    df["Note"] = df.apply(build_note, axis=1)
    return df

if gen_btn:
    if base_file is None:
        st.error("Моля, качи базовия Excel шаблон (.xlsx).")
    else:
        # временно записваме качения Excel, защото generator очаква път до файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(base_file.read())
            base_path = tmp.name

        try:
            # подготовка на стартовете
            starts: List[Dict] = []
            for _, row in starts_df.iterrows():
                d = pd.to_datetime(row.get("date")).date()
                t = str(row.get("type", "Main start"))
                starts.append({"date": d.isoformat(), "type": t})

            # генериране на програма
            df = generate_program(vo2max=vo2max, starts=starts, seed=seed, base_path=base_path)
            df = ensure_columns(df)

            # сортировка
            day_order = {"Monday":1,"Tuesday":2,"Wednesday":3,"Thursday":4,"Friday":5,"Saturday":6,"Sunday":7,
                         "Mon":1,"Tue":2,"Wed":3,"Thu":4,"Fri":5,"Sat":6,"Sun":7}
            if "Day" in df.columns:
                df["Day_order"] = df["Day"].map(day_order).fillna(8)
            else:
                df["Day_order"] = 8

            df = df.sort_values(["Week","Day_order","Date"], ascending=[True,True,True])
            df = augment_with_notes(df)

            # седмичен план (четим вид)
            cols = ["Week","Date","Day","Zone","ZoneLabel","Minutes","Strength","Note"]
            week_plan = df[[c for c in cols if c in df.columns]].copy()

            # каталог с методи
            methods = pd.DataFrame([
                {"Zone":"КР (1)", "Method":"Възстановителни L1 сесии; дължина според общия обем."},
                {"Zone":"АР1 (2)", "Method":"Аеробна база; дълги равномерни бягания/ролки; HR 60–75% HRmax."},
                {"Zone":"АР2 (3)", "Method":"Прагова работа; 3×10' / 4×8' с 2–3' пауза; HR 81–88% HRmax."},
                {"Zone":"СР (4)", "Method":"Състезателна скорост; 5×4' / 6×3' с 2–3' пауза; HR 89–95% HRmax."},
                {"Zone":"АНП (5)", "Method":"VO₂max интервали; 8×1' / 12×400м; пълна почивка; над 95% HRmax."},
                {"Zone":"Сила", "Method":"ОСП/ССП 2–3x седмично; избягвай в деня преди ключови интервали."},
                {"Zone":"Стрелба", "Method":"Суха/комплексна според деня; отделен отчет по твоя стандарт."},
            ])

            # Показване
            st.success("Готово! Виж прегледа и свали Excel.")
            with st.expander("Преглед на седмичния план (първите 60 реда)"):
                st.dataframe(week_plan.head(60))

            # генериране на Excel с много листа
            from pandas import ExcelWriter
            buf = io.BytesIO()
            with ExcelWriter(buf, engine="openpyxl") as writer:
                df.drop(columns=["Day_order"], errors="ignore").to_excel(writer, index=False, sheet_name="Program")
                week_plan.to_excel(writer, index=False, sheet_name="WeekPlan")
                pd.DataFrame({"Notes":[
                    "Бележки:",
                    "- Загрявка 15–20', разпускане 10–15'.",
                    "- Контрол на умора: HRV, RPE, сутрешен пулс; избегни натрупване на висок лактат.",
                    "- Не подреждай тежки интервали 3 последователни дни.",
                    "- Сила: ОСП/ССП според фазата; не претоварвай при висок стрес в З4–З5."
                ]}).to_excel(writer, index=False, sheet_name="Notes")
                methods.to_excel(writer, index=False, sheet_name="Methods")
            buf.seek(0)

            safe_name = (out_name or "generated_program_extended").strip().replace(" ","_")
            st.download_button(
                "📥 Изтегли разширен Excel (много листа)",
                data=buf,
                file_name=f"{safe_name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        except Exception as e:
            st.error(f"Възникна грешка: {e}")
            st.exception(e)
''')

out_path = Path("/mnt/data/streamlit_app_extended.py")
out_path.write_text(code, encoding="utf-8")
out_path.as_posix()
