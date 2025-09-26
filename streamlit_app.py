
import streamlit as st
import pandas as pd
import io
import tempfile
from datetime import date
from typing import List, Dict

# Импорт от твоя файл (трябва да е в същата папка или да посочиш правилен път)
from biathlon_program_generator_segments_taper_v2 import generate_program

st.set_page_config(page_title="Biathlon Program Generator", page_icon="🏃‍♂️", layout="centered")
st.title("🏃‍♂️ Генератор на тренировъчни програми (биатлон)")
st.markdown("Въведи параметри и натисни **Генерирай програма**. Ще получиш Excel за изтегляне.")

# --- ВХОДНИ ДАННИ ---
vo2max = st.number_input("VO₂max (ml/kg/min)", min_value=30.0, max_value=95.0, value=65.0, step=0.5)

st.subheader("Състезания (дата + тип)")
st.caption("Добавяй редове. Тип: Main start (основен) или Control start (контролен).")

default_rows = pd.DataFrame([
    {"date": pd.to_datetime(date.today()).date(), "type": "Main start"}
])

# Използваме data_editor за лесно добавяне/редакция на редове.
# column_config е налично в по-новите версии на Streamlit.
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
    # Фолбек за по-стари версии на Streamlit
    starts_df = st.data_editor(default_rows, num_rows="dynamic")

base_file = st.file_uploader("Качи базовия Excel шаблон (напр. base_calendar.xlsx)", type=["xlsx"])
seed = st.number_input("Seed (за възпроизводимост)", min_value=0, value=42, step=1)

gen_btn = st.button("Генерирай програма")

if gen_btn:
    if base_file is None:
        st.error("Моля, качи базовия Excel шаблон (.xlsx).")
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(base_file.read())
            base_path = tmp.name

        try:
            # Преобразуваме стартовете към формат за generate_program
            starts: List[Dict] = []
            for _, row in starts_df.iterrows():
                d = pd.to_datetime(row.get("date")).date()
                t = str(row.get("type", "Main start"))
                starts.append({"date": d.isoformat(), "type": t})

            # Генерираме програмата
            df = generate_program(vo2max=vo2max, starts=starts, seed=seed, base_path=base_path)

            st.success("Готово! Изтегли Excel файла отдолу.")
            buf = io.BytesIO()
            df.to_excel(buf, index=False)
            buf.seek(0)
            st.download_button(
                "📥 Изтегли програмата (Excel)",
                data=buf,
                file_name="generated_program.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            with st.expander("Преглед (първите 30 реда)"):
                st.dataframe(df.head(30))

        except Exception as e:
            st.error(f"Възникна грешка: {e}")
            st.exception(e)
