# BIPS Inquiry MIS Dashboard

Streamlit dashboard for live Google Sheet analysis using:
- Sheet: `Inquiry`
- Range: `A:AQ`
- Date filter (default): `2026-04-01`

## What this dashboard provides

### 1) Overall Summary
- Total Inquiries
- Total Relevant Leads
- Total Irrelevant Leads
- % Irrelevant Leads
- Remarks Relevancy >= 25%
- CR% (heuristic based on status text)

### 2) Agent Performance
- Total leads per agent
- Irrelevant leads per agent
- Relevancy %
- Top 5 / Bottom 5 agents

### 3) Audit Logic
Flags leads where:
- Irrelevant = Yes **OR**
- Remarks relevancy < 25%

### 4) Charts
- Agent-wise total vs irrelevant (bar)
- Relevant vs Irrelevant (pie)
- Daily trend (if multiple dates exist)

### 5) Output
- Clean MIS layout with tables + charts + key observations

## Setup
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Usage
1. Paste live CSV URL in sidebar (default already set):
   `https://docs.google.com/spreadsheets/d/16uZ_W0EVzxIsBUEzVch5UjD01E_Wzhj5D9tOTD61VnY/gviz/tq?tqx=out:csv&gid=341619939`
2. Set date to analyze: `2026-04-01`
3. Keep threshold at `25%` (or adjust)
4. Click **Fetch latest data & Analyze**

## Data mapping (expected)
- Column C: Inquiry Date & Time
- Column H: Update Remarks
- Column K: Sales Person Email/NAME
- Column O: Inquiry Status

The app auto-detects by header aliases and falls back to positional mapping above.
