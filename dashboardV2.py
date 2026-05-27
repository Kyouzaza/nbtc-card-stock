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

OPERATOR_COLORS = {
    "AWN": {"bg": "#DCFCE7", "border": "#22C55E", "text": "#166534"},
    "DTN": {"bg": "#DBEAFE", "border": "#3B82F6", "text": "#1D4ED8"},
    "TUC": {"bg": "#FEE2E2", "border": "#EF4444", "text": "#991B1B"},
    "CAT": {"bg": "#FFEDD5", "border": "#F97316", "text": "#9A3412"},
}
DEFAULT_OPERATOR_COLOR = {"bg": "#F1F5F9", "border": "#94A3B8", "text": "#334155"}


def inject_styles():
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2rem;
        }
        .dashboard-header {
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            background: #ffffff;
            padding: 18px 20px;
            margin-bottom: 12px;
        }
        .dashboard-header h1 {
            margin: 0 0 4px 0;
            font-size: 1.7rem;
            line-height: 1.2;
            color: #111827;
        }
        .dashboard-header p {
            margin: 0;
            color: #64748b;
        }
        .operator-legend {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 8px 0 16px 0;
        }
        .operator-chip {
            display: inline-flex;
            align-items: center;
            border: 1px solid var(--operator-border);
            background: var(--operator-bg);
            color: var(--operator-text);
            border-radius: 999px;
            padding: 5px 11px;
            font-weight: 800;
            font-size: 0.86rem;
        }
        .operator-card {
            border: 1px solid var(--operator-border);
            border-left: 7px solid var(--operator-border);
            border-radius: 8px;
            background: var(--operator-bg);
            padding: 13px 14px;
            min-height: 88px;
        }
        .operator-card .operator-name {
            color: var(--operator-text);
            font-weight: 900;
            font-size: 1rem;
        }
        .operator-card .operator-count {
            color: #111827;
            font-weight: 900;
            font-size: 1.55rem;
            line-height: 1.1;
            margin-top: 6px;
        }
        .operator-card .operator-value {
            color: #475569;
            font-size: 0.84rem;
            margin-top: 5px;
        }
        div[data-testid="stMetric"] {
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            background: #ffffff;
            padding: 10px 12px;
        }
        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] [data-testid="stMetricLabel"],
        div[data-testid="stMetric"] [data-testid="stMetricValue"],
        div[data-testid="stMetric"] [data-testid="stMetricDelta"],
        div[data-testid="stMetric"] p {
            color: #111827 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def operator_style(operator):
    return OPERATOR_COLORS.get(str(operator).strip().upper(), DEFAULT_OPERATOR_COLOR)


def render_operator_legend():
    chips = []
    for operator in OPERATORS:
        colors = operator_style(operator)
        chips.append(
            f"<span class=\"operator-chip\" style=\"--operator-bg:{colors['bg']};--operator-border:{colors['border']};--operator-text:{colors['text']};\">"
            f"{operator}"
            "</span>"
        )
    st.markdown(f"<div class='operator-legend'>{''.join(chips)}</div>", unsafe_allow_html=True)


def render_operator_card(operator, count, value):
    colors = operator_style(operator)
    st.markdown(
        f"""
        <div class="operator-card" style="--operator-bg:{colors['bg']};--operator-border:{colors['border']};--operator-text:{colors['text']};">
            <div class="operator-name">{operator}</div>
            <div class="operator-count">{count:,.0f} ใบ</div>
            <div class="operator-value">มูลค่ารวม {value:,.0f} บาท</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def style_operator_rows(dataframe, operator_column):
    def row_style(row):
        colors = operator_style(row.get(operator_column, ""))
        return [f"background-color: {colors['bg']}; color: #111827;" for _ in row]

    return dataframe.style.apply(row_style, axis=1)


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
    st.subheader("ยอดบัตรคงเหลือในระบบ")
    if df.empty:
        st.info("ยังไม่มีข้อมูลบัตรในระบบ")
        return

    if not require_columns(columns, ["Status", "Operator", "Price"], "สรุปยอด"):
        return

    available_df = df[df[columns["Status"]].isin(["ปกติ", "ใกล้หมดอายุ"])].copy()
    available_df[columns["Price"]] = pd.to_numeric(available_df[columns["Price"]], errors="coerce").fillna(0)

    total_cards = len(available_df)
    total_value = available_df[columns["Price"]].sum()
    near_expiry = (available_df[columns["Status"]] == "ใกล้หมดอายุ").sum()

    metric1, metric2, metric3 = st.columns(3)
    metric1.metric("พร้อมเบิก", f"{total_cards:,.0f} ใบ")
    metric2.metric("มูลค่ารวม", f"{total_value:,.0f} บาท")
    metric3.metric("ใกล้หมดอายุ", f"{near_expiry:,.0f} ใบ")

    operator_summary = (
        available_df.groupby(columns["Operator"])
        .agg(
            card_count=(columns["Operator"], "size"),
            total_value=(columns["Price"], "sum"),
        )
        .reset_index()
    )

    card_columns = st.columns(4)
    for index, operator in enumerate(OPERATORS):
        operator_rows = operator_summary[
            operator_summary[columns["Operator"]].astype(str).str.upper() == operator
        ]
        count = int(operator_rows["card_count"].sum()) if not operator_rows.empty else 0
        value = float(operator_rows["total_value"].sum()) if not operator_rows.empty else 0
        with card_columns[index]:
            render_operator_card(operator, count, value)

    available_cards = (
        available_df
        .groupby([columns["Operator"], columns["Price"]])
        .size()
        .reset_index(name="คงเหลือ (ใบ)")
        .sort_values([columns["Operator"], columns["Price"]])
    )
    st.dataframe(
        style_operator_rows(available_cards, columns["Operator"]),
        width="stretch",
        hide_index=True,
    )


def render_add_card_form(sheet):
    st.subheader("เพิ่มบัตรใหม่เข้าสต็อก")
    with st.form("add_card_form", clear_on_submit=True):
        col1, col2, col3, col4 = st.columns([1.1, 1, 1, 1.1])
        with col1:
            operator = st.selectbox("ผู้ให้บริการ", OPERATORS)
        with col2:
            price = st.number_input("ราคาบัตร", min_value=0, step=10)
        with col3:
            expiry_month = st.selectbox(
                "เดือนหมดอายุ",
                list(range(1, 13)),
                format_func=lambda month: f"{month:02d}",
            )
        with col4:
            expiry_year = st.number_input(
                "ปีหมดอายุ",
                min_value=datetime.date.today().year,
                max_value=2100,
                value=datetime.date.today().year,
                step=1,
            )
        card_id = st.text_input("เลขที่บัตร")

        submitted = st.form_submit_button("บันทึกเข้าสต็อก", type="primary")
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
    st.subheader("เบิกใช้บัตรเติมเงิน")

    if df.empty:
        st.info("ยังไม่มีข้อมูลบัตรในระบบ")
        return

    required = ["Status", "Operator", "Price", "ID", "Expired date", "Day(s) left"]
    if not require_columns(columns, required, "หน้าเบิก"):
        return

    active_cards = df[df[columns["Status"]].isin(["ปกติ", "ใกล้หมดอายุ"])].copy()
    active_cards[columns["Price"]] = pd.to_numeric(active_cards[columns["Price"]], errors="coerce").fillna(0)
    active_cards[columns["Day(s) left"]] = pd.to_numeric(active_cards[columns["Day(s) left"]], errors="coerce")
    if active_cards.empty:
        st.success("🎉 บัตรในสต็อกถูกเบิกหมดแล้ว")
        return

    filter1, filter2, filter3 = st.columns([1, 1, 1.4])
    with filter1:
        operator_filter = st.selectbox("เครือข่าย", ["ทั้งหมด"] + OPERATORS)
    with filter2:
        prices = sorted(active_cards[columns["Price"]].astype(int).unique().tolist())
        price_filter = st.selectbox("ราคา", ["ทั้งหมด"] + prices)
    with filter3:
        status_filter = st.multiselect(
            "สถานะ",
            ["ปกติ", "ใกล้หมดอายุ"],
            default=["ปกติ", "ใกล้หมดอายุ"],
        )

    if operator_filter != "ทั้งหมด":
        active_cards = active_cards[active_cards[columns["Operator"]].astype(str).str.upper() == operator_filter]
    if price_filter != "ทั้งหมด":
        active_cards = active_cards[active_cards[columns["Price"]] == price_filter]
    if status_filter:
        active_cards = active_cards[active_cards[columns["Status"]].isin(status_filter)]

    if active_cards.empty:
        st.info("ไม่พบบัตรที่ตรงกับเงื่อนไข")
        return

    active_cards = active_cards.sort_values(
        [columns["Day(s) left"], "sheet_row"],
        na_position="last",
    ).reset_index(drop=True)
    active_cards.insert(0, "เลือกเบิก", False)
    display_df = active_cards[
        [
            "เลือกเบิก",
            columns["Operator"],
            columns["Price"],
            columns["ID"],
            columns["Expired date"],
            columns["Day(s) left"],
            columns["Status"],
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
            columns["Status"],
            "sheet_row",
        ],
        column_config={
            "เลือกเบิก": st.column_config.CheckboxColumn("เลือกเบิก"),
            columns["Day(s) left"]: st.column_config.NumberColumn(columns["Day(s) left"]),
            "sheet_row": st.column_config.NumberColumn("แถวในชีต"),
        },
        width="stretch",
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
    st.subheader("บัตรที่ใกล้หมดอายุที่สุดแยกตามเครือข่าย")

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

    st.dataframe(
        style_operator_rows(operator_summary, columns["Operator"]),
        width="stretch",
        hide_index=True,
    )
    st.caption("แจกแจงตามมูลค่าบัตรของวันหมดอายุที่ใกล้ที่สุด")
    st.dataframe(
        style_operator_rows(
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
            columns["Operator"],
        ),
        width="stretch",
        hide_index=True,
    )


def render_dashboard_header():
    st.markdown(
        f"""
        <div class="dashboard-header">
            <h1>ระบบบริหารจัดการบัตรเติมเงิน</h1>
            <p>เชื่อมต่อข้อมูลจาก worksheet: {WORKSHEET_NAME}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_operator_legend()


def render_raw_table(df, columns):
    if df.empty:
        st.info("ยังไม่มีข้อมูลบัตรในระบบ")
        return

    if columns.get("Operator"):
        st.dataframe(
            style_operator_rows(df.drop(columns=["sheet_row"], errors="ignore"), columns["Operator"]),
            width="stretch",
            hide_index=True,
        )
    else:
        st.dataframe(df.drop(columns=["sheet_row"], errors="ignore"), width="stretch", hide_index=True)


st.set_page_config(page_title="ระบบบริหารจัดการบัตรเติมเงิน", layout="wide")
inject_styles()

client = authorize_google_sheets()
sheet = open_stock_sheet(client)

render_dashboard_header()

df = load_sheet_dataframe(sheet)
if not df.empty:
    df.columns = df.columns.str.strip()
columns = build_column_map(df)

overview_tab, add_tab, withdraw_tab, expiry_tab, data_tab = st.tabs(
    ["ภาพรวม", "เพิ่มบัตร", "เบิกบัตร", "ใกล้หมดอายุ", "ข้อมูลทั้งหมด"]
)

with overview_tab:
    render_stock_summary(df, columns)

with add_tab:
    render_add_card_form(sheet)

with withdraw_tab:
    render_withdraw(df, sheet, columns)

with expiry_tab:
    render_nearest_expiry(df, columns)

with data_tab:
    render_raw_table(df, columns)
