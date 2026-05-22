import calendar
import datetime

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials


SHEET_URL = "https://docs.google.com/spreadsheets/d/1rvc8juySIft-YPNu5X5VQ4-0ksei9XSEktqJoQBEhCc/edit?usp=sharing"
WORKSHEET_NAME = "StockV2"
OPERATORS = ["DTN", "AWN", "TUC", "CAT"]
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]


def authorize_google_sheets():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPE)
        return gspread.authorize(creds)
    except Exception:
        try:
            creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPE)
            return gspread.authorize(creds)
        except FileNotFoundError:
            st.error("🚨 ไม่พบไฟล์รหัสผ่าน กรุณาตั้งค่า Secrets หรือวางไฟล์ credentials.json")
            st.stop()


def open_stock_sheet(client):
    spreadsheet = client.open_by_url(SHEET_URL)
    try:
        return spreadsheet.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        st.error(f"ไม่พบ worksheet ชื่อ {WORKSHEET_NAME}")
        st.stop()


def load_sheet_dataframe(worksheet):
    values = worksheet.get("A:K")
    if not values:
        return pd.DataFrame()

    headers = [header.strip() for header in values[0]]
    row_width = len(headers)
    rows = []
    sheet_rows = []

    for sheet_row, row in enumerate(values[1:], start=2):
        padded_row = row + [""] * (row_width - len(row))
        padded_row = padded_row[:row_width]
        if any(str(cell).strip() for cell in padded_row):
            rows.append(padded_row)
            sheet_rows.append(sheet_row)

    dataframe = pd.DataFrame(rows, columns=headers)
    if not dataframe.empty:
        dataframe["sheet_row"] = sheet_rows
    return dataframe


def find_column(columns, *names):
    normalized_columns = {column.strip().lower(): column for column in columns}
    for name in names:
        column = normalized_columns.get(name.strip().lower())
        if column:
            return column
    return None


def parse_expired_dates(series):
    parsed = pd.to_datetime(series, format="%m/%d/%y", errors="coerce")
    missing = parsed.isna()
    parsed.loc[missing] = pd.to_datetime(series.loc[missing], format="%m/%d/%Y", errors="coerce")
    missing = parsed.isna()
    parsed.loc[missing] = pd.to_datetime(series.loc[missing], format="%d/%m/%Y", errors="coerce")
    return parsed


def require_columns(column_map, required_names, section_name):
    missing = [name for name in required_names if not column_map.get(name)]
    if missing:
        st.error(f"ไม่พบคอลัมน์ที่จำเป็นสำหรับ{section_name}: {', '.join(missing)}")
        return False
    return True


def build_withdraw_updates(sheet_rows, withdraw_date, requester, job_no):
    updates = []
    for sheet_row in sheet_rows:
        updates.extend(
            [
                {"range": f"H{sheet_row}", "values": [[True]]},
                {"range": f"I{sheet_row}", "values": [[withdraw_date]]},
                {"range": f"J{sheet_row}", "values": [[requester]]},
                {"range": f"K{sheet_row}", "values": [[job_no]]},
            ]
        )
    return updates


def build_column_map(df):
    return {
        "Status": find_column(df.columns, "Status"),
        "Operator": find_column(df.columns, "Operator"),
        "Price": find_column(df.columns, "Price"),
        "ID": find_column(df.columns, "ID", "Card ID", "Card No", "Card Number"),
        "Expired date": find_column(df.columns, "Expired date", "Expired Date"),
        "Day(s) left": find_column(df.columns, "Day(s) left", "Days left", "Day left"),
    }


def render_stock_summary(df, columns):
    st.subheader("📊 ยอดบัตรคงเหลือในระบบ")
    if df.empty:
        st.info("ยังไม่มีข้อมูลบัตรในระบบ")
        return

    if not require_columns(columns, ["Status", "Operator", "Price"], "สรุปยอด"):
        return

    available_cards = (
        df[df[columns["Status"]].isin(["ปกติ", "ใกล้หมดอายุ"])]
        .groupby([columns["Operator"], columns["Price"]])
        .size()
        .reset_index(name="คงเหลือ (ใบ)")
    )
    st.dataframe(available_cards, use_container_width=True)


def render_add_card_form(sheet):
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
        if not submitted:
            return

        if not card_id:
            st.error("กรุณากรอกเลขที่บัตร")
            return

        next_row = len(sheet.col_values(1)) + 1
        today = datetime.date.today().strftime("%m/%d/%y")
        last_day = calendar.monthrange(expiry_year, expiry_month)[1]
        expired_date = f"{expiry_month:02d}/{last_day:02d}/{expiry_year % 100:02d}"

        new_row_data = [
            operator,
            price,
            today,
            expired_date,
            card_id,
            f'=IF(H{next_row}=TRUE, "ใช้งานแล้ว", IF(D{next_row}="", "", IF(D{next_row}<TODAY(), "หมดอายุแล้ว", IF(D{next_row}-TODAY()<=30, "ใกล้หมดอายุ", "ปกติ"))))',
            f'=IF(F{next_row}="ใช้งานแล้ว", "-", D{next_row}-TODAY())',
            "FALSE",
            "",
            "",
            "",
        ]

        sheet.append_row(new_row_data, value_input_option="USER_ENTERED", table_range="A1:A")
        sheet.spreadsheet.batch_update(
            {
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
            }
        )

        st.success(f"บันทึกบัตรเลขที่ {card_id} เรียบร้อยแล้ว พร้อมสูตรและ Checkbox!")
        st.rerun()


def render_withdraw(df, sheet, columns):
    st.subheader("🧾 หน้าต่างเบิกใช้บัตรเติมเงิน")

    if df.empty:
        st.info("ยังไม่มีข้อมูลบัตรในระบบ")
        return

    required = ["Status", "Operator", "Price", "ID", "Expired date", "Day(s) left"]
    if not require_columns(columns, required, "หน้าเบิก"):
        return

    active_cards = df[df[columns["Status"]].isin(["ปกติ", "ใกล้หมดอายุ"])].copy()
    if active_cards.empty:
        st.success("🎉 บัตรในสต็อกถูกเบิกหมดแล้ว")
        return

    active_cards.insert(0, "เลือกเบิก", False)
    display_df = active_cards[
        [
            "เลือกเบิก",
            columns["Operator"],
            columns["Price"],
            columns["ID"],
            columns["Expired date"],
            columns["Day(s) left"],
            "sheet_row",
        ]
    ]

    col1, col2 = st.columns(2)
    with col1:
        requester = st.text_input("👤 ชื่อผู้ขอเบิก", placeholder="กรอกชื่อ-นามสกุล")
    with col2:
        job_no = st.text_input("💼 Job No.", placeholder="เช่น QoS, 42/69")

    edited_df = st.data_editor(
        display_df,
        hide_index=True,
        disabled=[
            columns["Operator"],
            columns["Price"],
            columns["ID"],
            columns["Expired date"],
            columns["Day(s) left"],
            "sheet_row",
        ],
        column_config={
            "เลือกเบิก": st.column_config.CheckboxColumn("เลือกเบิก"),
            "sheet_row": st.column_config.NumberColumn("แถวในชีต"),
        },
        use_container_width=True,
        key="withdraw_editor",
    )

    selected_rows = edited_df[edited_df["เลือกเบิก"] == True]
    if selected_rows.empty:
        st.warning("⚠️ กรุณาเลือกบัตรที่ต้องการเบิกจากตารางด้านบนอย่างน้อย 1 ใบ")
    else:
        selected_operators = ", ".join(selected_rows[columns["Operator"]].astype(str).unique())
        st.info(f"👉 ท่านกำลังเลือกบัตรค่าย **{selected_operators}** รวมทั้งหมด **{len(selected_rows)}** ใบ")

    if st.button("🚀 ยืนยันการเบิกบัตรที่เลือก", type="primary"):
        if not requester or not job_no:
            st.error("❌ ไม่สามารถเบิกได้: กรุณากรอกชื่อผู้ขอเบิกและ Job No. ให้ครบถ้วน")
            return
        if selected_rows.empty:
            st.error("❌ ไม่สามารถเบิกได้: ยังไม่ได้เลือกบัตร")
            return

        today_str = datetime.date.today().strftime("%d/%m/%Y")
        sheet_rows = [int(row["sheet_row"]) for _, row in selected_rows.iterrows()]
        updates = build_withdraw_updates(sheet_rows, today_str, requester, job_no)

        with st.spinner("กำลังทำการเบิกบัตรและอัปเดตข้อมูลลง Google Sheets..."):
            sheet.batch_update(updates, value_input_option="USER_ENTERED")

        st.success(f"ทำการเบิกบัตรเติมเงินจำนวน {len(selected_rows)} ใบให้คุณ {requester} เรียบร้อยแล้ว")
        st.rerun()


def render_nearest_expiry(df, columns):
    st.subheader("🧾 บัตรที่ใกล้หมดอายุที่สุดแยกตามเครือข่าย")

    if df.empty:
        st.info("ยังไม่มีข้อมูลบัตรในระบบ")
        return

    if not require_columns(columns, ["Status", "Operator", "Price", "Expired date"], "สรุปวันหมดอายุ"):
        return

    available_df = df[df[columns["Status"]] != "ใช้งานแล้ว"].copy()
    if available_df.empty:
        st.info("ยังไม่มีบัตรที่พร้อมใช้งานในระบบ")
        return

    available_df["Expired Date Parsed"] = parse_expired_dates(available_df[columns["Expired date"]])
    available_df[columns["Price"]] = pd.to_numeric(available_df[columns["Price"]], errors="coerce")
    available_df = available_df.dropna(subset=["Expired Date Parsed", columns["Price"]])
    available_df = available_df[available_df["Expired Date Parsed"].dt.date >= datetime.date.today()]

    if available_df.empty:
        st.warning("ยังไม่มีบัตรที่พร้อมใช้งานและอ่านวันหมดอายุได้")
        return

    nearest_expiry = available_df.groupby(columns["Operator"])["Expired Date Parsed"].transform("min")
    nearest_cards = available_df[available_df["Expired Date Parsed"] == nearest_expiry].copy()

    detail_summary = (
        nearest_cards.groupby([columns["Operator"], "Expired Date Parsed", columns["Price"]])
        .size()
        .reset_index(name="จำนวน (ใบ)")
        .sort_values([columns["Operator"], "Expired Date Parsed", columns["Price"]])
    )
    detail_summary["มูลค่ารวม"] = detail_summary[columns["Price"]] * detail_summary["จำนวน (ใบ)"]
    detail_summary["จำนวนวันที่เหลือ"] = (
        detail_summary["Expired Date Parsed"].dt.date - datetime.date.today()
    ).apply(lambda days: days.days)
    detail_summary["วันหมดอายุใกล้สุด"] = detail_summary["Expired Date Parsed"].dt.strftime("%d/%m/%y")

    operator_summary = (
        detail_summary.groupby([columns["Operator"], "วันหมดอายุใกล้สุด", "จำนวนวันที่เหลือ"])
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
            รายละเอียด=lambda data: data[columns["Price"]].astype(int).astype(str)
            + " บาท x "
            + data["จำนวน (ใบ)"].astype(str)
            + " ใบ"
        )
        .groupby(columns["Operator"])["รายละเอียด"]
        .apply(", ".join)
        .reset_index()
    )
    operator_summary = operator_summary.merge(price_details, on=columns["Operator"], how="left")

    st.dataframe(operator_summary, use_container_width=True)
    st.caption("แจกแจงตามมูลค่าบัตรของวันหมดอายุที่ใกล้ที่สุด")
    st.dataframe(
        detail_summary[
            [
                columns["Operator"],
                "วันหมดอายุใกล้สุด",
                "จำนวนวันที่เหลือ",
                columns["Price"],
                "จำนวน (ใบ)",
                "มูลค่ารวม",
            ]
        ],
        use_container_width=True,
    )


st.set_page_config(page_title="ระบบบริหารจัดการบัตรเติมเงิน", layout="wide")

client = authorize_google_sheets()
sheet = open_stock_sheet(client)

st.title("ระบบบริหารจัดการบัตรเติมเงิน")
st.caption(f"เชื่อมต่อข้อมูลจาก worksheet: {WORKSHEET_NAME}")

df = load_sheet_dataframe(sheet)
if not df.empty:
    df.columns = df.columns.str.strip()
columns = build_column_map(df)

overview_tab, add_tab, withdraw_tab, expiry_tab = st.tabs(
    ["ภาพรวม", "เพิ่มบัตร", "เบิกบัตร", "ใกล้หมดอายุ"]
)

with overview_tab:
    render_stock_summary(df, columns)

with add_tab:
    render_add_card_form(sheet)

with withdraw_tab:
    render_withdraw(df, sheet, columns)

with expiry_tab:
    render_nearest_expiry(df, columns)
