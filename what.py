import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import datetime
import calendar

OPERATORS = ["DTN", "AWN", "TUC", "CAT"]

# 1. ตั้งค่าการเชื่อมต่อ Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# เปลี่ยนมาใช้วิธีอ่านไฟล์ credentials.json โดยตรง (แก้ Error st.secrets)
try:
    creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    client = gspread.authorize(creds)
    
    # อย่าลืมเปลี่ยนชื่อไฟล์ตรงนี้ให้ตรงกับชื่อ Google Sheets ของคุณนะครับ
    sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1rvc8juySIft-YPNu5X5VQ4-0ksei9XSEktqJoQBEhCc/edit?usp=sharing").sheet1 
    
except FileNotFoundError:
    st.error("🚨 ไม่พบไฟล์ 'credentials.json' ในโฟลเดอร์ กรุณานำไฟล์กุญแจมาวางไว้ที่เดียวกับไฟล์ what.py ครับ")
    st.stop()

st.title("ระบบบริหารจัดการบัตรเติมเงิน")

# ดึงข้อมูลทั้งหมดจาก Sheet มาแสดงใน Dashboard
data = sheet.get_all_records()
import pandas as pd
df = pd.DataFrame(data)

# ---- ส่วนที่ 1: สรุปยอดคงเหลือ ----
st.subheader("📊 ยอดบัตรคงเหลือในระบบ")
if not df.empty:
    # กรองเฉพาะบัตรที่สถานะเป็น "ปกติ" แล้วนับจำนวน
    available_cards = df[df['Status'] == 'ปกติ'].groupby(['Operator', 'Price']).size().reset_index(name='คงเหลือ (ใบ)')
    st.dataframe(available_cards, use_container_width=True)

# ---- ส่วนที่ 2: ฟอร์มเพิ่มบัตรใหม่ ----
st.subheader("➕ เพิ่มบัตรใหม่เข้าสต็อก")
with st.form("add_card_form", clear_on_submit=True):
    operator = st.selectbox("ผู้ให้บริการ", OPERATORS)
    price = st.number_input("ราคาบัตร", min_value=0, step=10)
    expiry_month = st.selectbox(
        "เดือนหมดอายุ",
        list(range(1, 13)),
        format_func=lambda month: f"{month:02d}",
    )
    expiry_year = st.number_input(
        "ปีหมดอายุ",
        min_value=datetime.date.today().year,
        max_value=2100,
        value=datetime.date.today().year,
        step=1,
    )
    card_id = st.text_input("เลขที่บัตร")
    
    submitted = st.form_submit_button("บันทึกเข้าสต็อก")
    if submitted:
        if card_id:
            # 1. เช็คก่อนว่าข้อมูลในคอลัมน์ A มีกี่บรรทัด เพื่อหา "บรรทัดถัดไป" ที่จะเขียนสูตร
            col_a_data = sheet.col_values(1)
            next_row = len(col_a_data) + 1 
            
            today = datetime.date.today().strftime("%m/%d/%y")
            last_day = calendar.monthrange(expiry_year, expiry_month)[1]
            expired_date = f"{expiry_month:02d}/{last_day:02d}/{expiry_year % 100:02d}"
            
            # 2. เตรียมข้อมูล 11 คอลัมน์ (A ถึง K)
            new_row_data = [
                operator,                  # A: เครือข่าย
                price,                     # B: ราคา
                today,                     # C: วันนำเข้า
                expired_date,              # D: วันหมดอายุ (แก้ไขตามจริงได้)
                card_id,                   # E: เลขบัตร
                
                # F: ⭐️ ให้ Python เขียนสูตรเช็คเงื่อนไขจาก Checkbox คอลัมน์ H
                f'=IF(H{next_row}=TRUE, "ใช้งานแล้ว", IF(D{next_row}="", "", IF(D{next_row}<TODAY(), "หมดอายุแล้ว", IF(D{next_row}-TODAY()<=30, "ใกล้หมดอายุ", "ปกติ"))))', 
                f'=IF(F{next_row}="ใช้งานแล้ว", "-", D{next_row}-TODAY())',   # G: Day(s) left
                "",                        # H: Used? เว้นว่างไว้ แล้วสร้าง Checkbox หลังบันทึกแถว
                "", "", ""                 # I, J, K: เว้นว่างไว้
            ]
            
            # 3. บันทึกลง Sheet (เพิ่มคำสั่ง table_range เพื่อป้องกันข้อมูลกระโดดไปบรรทัดล่างสุด)
            sheet.append_row(new_row_data, value_input_option="USER_ENTERED", table_range="A1:A")
            sheet.spreadsheet.batch_update({
                "requests": [
                    {
                        "setDataValidation": {
                            "range": {
                                "sheetId": sheet.id,
                                "startRowIndex": next_row - 1,
                                "endRowIndex": next_row,
                                "startColumnIndex": 7,
                                "endColumnIndex": 8,
                            },
                            "rule": {
                                "condition": {"type": "BOOLEAN"},
                                "strict": True,
                                "showCustomUi": True,
                            },
                        }
                    }
                ]
            })
            
            st.success(f"บันทึกบัตรเลขที่ {card_id} เรียบร้อยแล้ว พร้อมสูตรและ Checkbox!")
            st.rerun()
        else:
            st.error("กรุณากรอกเลขที่บัตร")

# ---- ส่วนที่ 3: สรุปบัตรที่ใกล้หมดอายุที่สุด ----
st.subheader("🧾 บัตรที่ใกล้หมดอายุที่สุดแยกตามเครือข่าย")

required_columns = {"Operator", "Price", "Expired date", "Status"}
if df.empty:
    st.info("ยังไม่มีข้อมูลบัตรในระบบ")
elif not required_columns.issubset(df.columns):
    missing_columns = sorted(required_columns - set(df.columns))
    st.error(f"ไม่พบคอลัมน์ที่จำเป็น: {', '.join(missing_columns)}")
else:
    available_df = df[df["Status"] != "ใช้งานแล้ว"].copy()

    if available_df.empty:
        st.info("ยังไม่มีบัตรที่พร้อมใช้งานในระบบ")
    else:
        available_df["Expired Date Parsed"] = pd.to_datetime(available_df["Expired date"], format="%m/%d/%y", errors="coerce")
        missing_dates = available_df["Expired Date Parsed"].isna()
        available_df.loc[missing_dates, "Expired Date Parsed"] = pd.to_datetime(
            available_df.loc[missing_dates, "Expired date"],
            format="%m/%d/%Y",
            errors="coerce",
        )
        missing_dates = available_df["Expired Date Parsed"].isna()
        available_df.loc[missing_dates, "Expired Date Parsed"] = pd.to_datetime(
            available_df.loc[missing_dates, "Expired date"],
            format="%d/%m/%Y",
            errors="coerce",
        )
        available_df["Price"] = pd.to_numeric(available_df["Price"], errors="coerce")
        available_df = available_df.dropna(subset=["Expired Date Parsed", "Price"])
        available_df = available_df[available_df["Expired Date Parsed"].dt.date >= datetime.date.today()]

        if available_df.empty:
            st.warning("ยังไม่มีบัตรที่พร้อมใช้งานและอ่านวันหมดอายุได้")
        else:
            nearest_expiry = available_df.groupby("Operator")["Expired Date Parsed"].transform("min")
            nearest_cards = available_df[available_df["Expired Date Parsed"] == nearest_expiry].copy()

            detail_summary = (
                nearest_cards.groupby(["Operator", "Expired Date Parsed", "Price"])
                .size()
                .reset_index(name="จำนวน (ใบ)")
                .sort_values(["Operator", "Expired Date Parsed", "Price"])
            )
            detail_summary["มูลค่ารวม"] = detail_summary["Price"] * detail_summary["จำนวน (ใบ)"]
            detail_summary["จำนวนวันที่เหลือ"] = (
                detail_summary["Expired Date Parsed"].dt.date - datetime.date.today()
            ).apply(lambda days: days.days)
            detail_summary["วันหมดอายุใกล้สุด"] = detail_summary["Expired Date Parsed"].dt.strftime("%d/%m/%y")

            operator_summary = (
                detail_summary.groupby(["Operator", "วันหมดอายุใกล้สุด", "จำนวนวันที่เหลือ"])
                .agg(
                    **{
                        "จำนวนรวม (ใบ)": ("จำนวน (ใบ)", "sum"),
                        "มูลค่ารวม": ("มูลค่ารวม", "sum"),
                    }
                )
                .reset_index()
            )

            price_details = (
                detail_summary.assign(
                    รายละเอียด=lambda data: data["Price"].astype(int).astype(str)
                    + " บาท x "
                    + data["จำนวน (ใบ)"].astype(str)
                    + " ใบ"
                )
                .groupby("Operator")["รายละเอียด"]
                .apply(", ".join)
                .reset_index()
            )
            operator_summary = operator_summary.merge(price_details, on="Operator", how="left")

            st.dataframe(operator_summary, use_container_width=True)
            st.caption("แจกแจงตามมูลค่าบัตรของวันหมดอายุที่ใกล้ที่สุด")
            st.dataframe(
                detail_summary[
                    ["Operator", "วันหมดอายุใกล้สุด", "จำนวนวันที่เหลือ", "Price", "จำนวน (ใบ)", "มูลค่ารวม"]
                ],
                use_container_width=True,
            )
