import re
from datetime import date
from typing import Optional

import pandas as pd
import plotly.express as px
import streamlit as st

DEFAULT_LIVE_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/16uZ_W0EVzxIsBUEzVch5UjD01E_Wzhj5D9tOTD61VnY/"
    "gviz/tq?tqx=out:csv&gid=341619939"
)

ADMISSION_KEYWORDS = {
    "admission", "admissions", "apply", "application", "enroll", "enrollment",
    "school", "class", "fee", "fees", "curriculum", "seat", "seats", "bips",
    "grade", "nursery", "kg", "transport", "hostel", "campus", "syllabus",
}


# ---------- Data loading ----------
def load_live_sheet(csv_url: str) -> pd.DataFrame:
    df = pd.read_csv(csv_url)
    if df.empty:
        raise ValueError("Sheet returned no rows.")
    return df


def _find_column(df: pd.DataFrame, aliases: list[str], fallback_idx: int) -> str:
    lookup = {str(c).strip().lower(): c for c in df.columns}
    for alias in aliases:
        if alias.lower() in lookup:
            return lookup[alias.lower()]
    if fallback_idx >= len(df.columns):
        raise ValueError(f"Missing required column at index {fallback_idx}.")
    return df.columns[fallback_idx]


def prepare_dataset(df_raw: pd.DataFrame) -> pd.DataFrame:
    date_col = _find_column(df_raw, ["Inquiry Date & Time", "Inquiry Date", "Date"], 2)   # C
    remarks_col = _find_column(df_raw, ["Update Remarks", "Remarks"], 7)                    # H
    agent_col = _find_column(df_raw, ["Sales Person Email/NAME", "Sales Person", "Agent"], 10)  # K
    status_col = _find_column(df_raw, ["Inquiry Status", "Status"], 14)                      # O

    df = pd.DataFrame({
        "inquiry_datetime": pd.to_datetime(df_raw[date_col], errors="coerce", dayfirst=True),
        "remarks": df_raw[remarks_col].fillna("").astype(str).str.strip(),
        "agent": df_raw[agent_col].fillna("Unknown").astype(str).str.strip(),
        "status": df_raw[status_col].fillna("Unknown").astype(str).str.strip(),
    })

    df = df.dropna(subset=["inquiry_datetime"]).copy()
    df["agent"] = df["agent"].replace("", "Unknown")
    df["status_normalized"] = df["status"].str.lower()
    df["is_irrelevant"] = df["status_normalized"].str.contains("irrelevant", na=False)
    df["is_relevant"] = ~df["is_irrelevant"]
    df["remarks_relevancy_pct"] = df["remarks"].apply(score_remarks_relevancy)
    df["inquiry_date"] = df["inquiry_datetime"].dt.date
    return df


# ---------- Business logic ----------
def score_remarks_relevancy(text: str) -> float:
    tokens = set(re.findall(r"[a-zA-Z]+", str(text).lower()))
    if not tokens:
        return 0.0
    hits = len(tokens.intersection(ADMISSION_KEYWORDS))
    return round((hits / len(ADMISSION_KEYWORDS)) * 100, 2)


def compute_mis(df_day: pd.DataFrame, relevancy_threshold: float = 25.0) -> dict:
    total = len(df_day)
    irrelevant = int(df_day["is_irrelevant"].sum())
    relevant = total - irrelevant
    irrelevant_pct = (irrelevant / total * 100) if total else 0.0

    high_remarks = int((df_day["remarks_relevancy_pct"] >= relevancy_threshold).sum())

    # Optional CR% heuristic
    converted = int(df_day["status_normalized"].str.contains("admission|admitted|enrolled|converted", na=False).sum())
    cr_pct = (converted / total * 100) if total else 0.0

    return {
        "total_inquiries": total,
        "total_relevant": relevant,
        "total_irrelevant": irrelevant,
        "irrelevant_pct": round(irrelevant_pct, 2),
        "remarks_ge_threshold": high_remarks,
        "conversion_count": converted,
        "cr_pct": round(cr_pct, 2),
    }


def agent_performance(df_day: pd.DataFrame) -> pd.DataFrame:
    perf = (
        df_day.groupby("agent", as_index=False)
        .agg(
            total_leads=("agent", "size"),
            irrelevant_leads=("is_irrelevant", "sum"),
            avg_remarks_relevancy=("remarks_relevancy_pct", "mean"),
        )
    )
    perf["relevancy_pct"] = ((perf["total_leads"] - perf["irrelevant_leads"]) / perf["total_leads"] * 100).round(2)
    perf["avg_remarks_relevancy"] = perf["avg_remarks_relevancy"].round(2)
    return perf.sort_values(["relevancy_pct", "total_leads"], ascending=[False, False])


def flagged_audit(df_day: pd.DataFrame, threshold: float = 25.0) -> pd.DataFrame:
    flagged = df_day[(df_day["is_irrelevant"]) | (df_day["remarks_relevancy_pct"] < threshold)].copy()
    flagged["audit_reason"] = flagged.apply(
        lambda r: "Irrelevant status" if r["is_irrelevant"] else f"Remarks relevancy < {threshold:.0f}%", axis=1
    )
    return flagged.sort_values("inquiry_datetime", ascending=False)


def key_insights(mis: dict, perf: pd.DataFrame, flagged: pd.DataFrame) -> list[str]:
    insights = []
    insights.append(
        f"Irrelevant share is {mis['irrelevant_pct']}% ({mis['total_irrelevant']}/{mis['total_inquiries']})."
    )
    insights.append(
        f"Leads with remarks relevancy >= 25%: {mis['remarks_ge_threshold']} of {mis['total_inquiries']}."
    )
    if not perf.empty:
        top_agent = perf.iloc[0]
        low_agent = perf.iloc[-1]
        insights.append(
            f"Top agent by relevancy%: {top_agent['agent']} ({top_agent['relevancy_pct']}%)."
        )
        insights.append(
            f"Lowest agent by relevancy%: {low_agent['agent']} ({low_agent['relevancy_pct']}%)."
        )
    insights.append(f"Flagged leads for audit: {len(flagged)}.")
    return insights


# ---------- UI ----------
def render_dashboard(df_full: pd.DataFrame, selected_date: date, threshold: float) -> None:
    df_day = df_full[df_full["inquiry_date"] == selected_date].copy()

    if df_day.empty:
        st.warning(f"No rows found for {selected_date}.")
        return

    mis = compute_mis(df_day, threshold)
    perf = agent_performance(df_day)
    flagged = flagged_audit(df_day, threshold)

    st.subheader(f"MIS Dashboard — {selected_date}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Inquiries", mis["total_inquiries"])
    c2.metric("Total Relevant Leads", mis["total_relevant"])
    c3.metric("Total Irrelevant Leads", mis["total_irrelevant"])
    c4.metric("% Irrelevant Leads", f"{mis['irrelevant_pct']}%")

    c5, c6 = st.columns(2)
    c5.metric("Remarks Relevancy >= 25%", mis["remarks_ge_threshold"])
    c6.metric("CR% (heuristic)", f"{mis['cr_pct']}%")

    st.subheader("Agent Performance")
    st.dataframe(perf, use_container_width=True)

    st.markdown("**Top 5 Agents**")
    st.dataframe(perf.head(5), use_container_width=True)

    st.markdown("**Bottom 5 Agents**")
    st.dataframe(perf.tail(5), use_container_width=True)

    st.subheader("Audit — Flagged Leads")
    st.dataframe(
        flagged[["inquiry_datetime", "agent", "status", "remarks_relevancy_pct", "audit_reason", "remarks"]],
        use_container_width=True,
    )

    st.subheader("Charts")
    bar = px.bar(
        perf.sort_values("total_leads", ascending=False),
        x="agent",
        y=["total_leads", "irrelevant_leads"],
        barmode="group",
        title="Agent-wise Total vs Irrelevant Leads",
    )
    st.plotly_chart(bar, use_container_width=True)

    pie_data = pd.DataFrame(
        {
            "category": ["Relevant", "Irrelevant"],
            "count": [mis["total_relevant"], mis["total_irrelevant"]],
        }
    )
    pie = px.pie(pie_data, values="count", names="category", title="Relevant vs Irrelevant")
    st.plotly_chart(pie, use_container_width=True)

    daily = (
        df_full.groupby("inquiry_date", as_index=False)
        .agg(total=("agent", "size"), irrelevant=("is_irrelevant", "sum"))
        .sort_values("inquiry_date")
    )
    if len(daily) > 1:
        trend = px.line(daily, x="inquiry_date", y=["total", "irrelevant"], title="Daily Trend")
        st.plotly_chart(trend, use_container_width=True)

    st.subheader("Key Observations")
    for note in key_insights(mis, perf, flagged):
        st.write(f"- {note}")


def main() -> None:
    st.set_page_config(page_title="BIPS MIS Dashboard", layout="wide")
    st.title("BIPS Inquiry MIS Dashboard")
    st.caption("Live Google Sheet analysis for Inquiry!A:AQ with date filter and audit logic.")

    with st.sidebar:
        st.header("Source")
        csv_url = st.text_input("Live CSV URL", value=DEFAULT_LIVE_CSV_URL)
        selected_date = st.date_input("Date to analyze", value=date(2026, 4, 1))
        threshold = st.slider("Remarks relevancy threshold (%)", 5, 80, 25, 5)
        run = st.button("Fetch latest data & Analyze", type="primary")

    if run:
        try:
            raw = load_live_sheet(csv_url)
            prepared = prepare_dataset(raw)
            render_dashboard(prepared, selected_date, float(threshold))
        except Exception as exc:
            st.exception(exc)


if __name__ == "__main__":
    main()
