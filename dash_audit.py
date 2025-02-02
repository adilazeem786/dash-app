import dash
from dash import dcc, html, Input, Output, State
import dash_table
import pandas as pd
import io
import base64


def load_and_clean_data(bulk_data, str_data):
    bulk_data = bulk_data.dropna(subset=["Entity"]).reset_index(drop=True)
    str_data = str_data.dropna(subset=["Campaign Name", "Customer Search Term"]).reset_index(drop=True)

    campaigns = bulk_data[bulk_data["Entity"] == "Campaign"]
    ad_groups = bulk_data[bulk_data["Entity"] == "Ad group"]
    keywords = bulk_data[bulk_data["Entity"] == "Keyword"]
    placements = bulk_data[bulk_data["Entity"] == "Placement"]

    return {
        "bulk_data": bulk_data,
        "campaigns": campaigns,
        "ad_groups": ad_groups,
        "keywords": keywords,
        "placements": placements,
        "search_terms": str_data,
    }


def calculate_metrics(data, target_acos):
    bulk_data = data["bulk_data"].copy()
    campaigns = data["campaigns"].copy()
    keywords = data["keywords"].copy()
    search_terms = data["search_terms"].copy()

    # Ensure necessary columns exist
    required_columns = {
        "campaigns": ["Sales", "Clicks", "Impressions", "Spend", "Orders"],
        "keywords": ["Sales", "Clicks", "Spend", "Orders", "Ad Group Name", "Campaign Name"],
        "search_terms": ["Sales", "Clicks", "Spend", "Orders", "Ad Group Name", "Campaign Name"],
    }

    for df_name, cols in required_columns.items():
        df = locals()[df_name]
        for col in cols:
            if col not in df.columns:
                df[col] = 0

    # Campaign-level metrics
    campaigns["CTR"] = (campaigns["Clicks"] / campaigns["Impressions"]).fillna(0)
    campaigns["CPC"] = campaigns["Spend"] / campaigns["Clicks"].replace(0, 1)
    campaigns["ACOS"] = campaigns["Spend"] / campaigns["Sales"].replace(0, 1)

    # Keyword-level metrics and actions
    keywords["Max Bid"] = (keywords["Sales"] / keywords["Clicks"].replace(0, 1)) * target_acos
    keywords["Action"] = keywords.apply(
        lambda row: "Increase Bid" if row["Max Bid"] > row["Spend"] else
        ("Reduce Bid" if row["Max Bid"] < row["Spend"] else
         ("Pause" if row["Clicks"] > 4 and row["Orders"] == 0 else "Do Nothing")),
        axis=1
    )

    # Search term-level actions
    search_terms["ACOS"] = search_terms["Spend"] / search_terms["Sales"].replace(0, 1)
    search_terms["Action"] = search_terms.apply(
        lambda row: "Graduate" if row["ACOS"] < target_acos and row["Orders"] > 2 else
        ("Negate" if row["Clicks"] > 3 and row["Orders"] == 0 else "Do Nothing"),
        axis=1
    )

    return {
        "bulk_data": bulk_data,
        "campaigns": campaigns,
        "keywords": keywords,
        "search_terms": search_terms,
    }


# Dash App Initialization
app = dash.Dash(__name__)

# App Layout
app.layout = html.Div([
    html.H1("Amazon Ads Audit Program"),
    dcc.Upload(id="bulk-file-upload", children=html.Button("Upload Bulk File"), multiple=False),
    dcc.Upload(id="str-file-upload", children=html.Button("Upload Search Term Report"), multiple=False),
    dcc.Input(id="target-acos", type="number", placeholder="Enter Target ACOS (%)", value=30, step=1),
    html.Div(id="audit-summary"),
    html.Hr(),
    html.H3("Campaign Metrics"),
    dash_table.DataTable(id="campaign-table", row_selectable="single"),
    html.H3("Keyword Metrics"),
    dash_table.DataTable(id="keyword-table", row_selectable="single"),
    html.H3("Search Term Metrics"),
    dash_table.DataTable(id="search-term-table"),
])


def parse_contents(contents):
    content_type, content_string = contents.split(",")
    decoded = base64.b64decode(content_string)
    return pd.ExcelFile(io.BytesIO(decoded))


@app.callback(
    [Output("audit-summary", "children"),
     Output("campaign-table", "data"),
     Output("campaign-table", "columns"),
     Output("keyword-table", "data"),
     Output("keyword-table", "columns"),
     Output("search-term-table", "data"),
     Output("search-term-table", "columns")],
    [Input("bulk-file-upload", "contents"),
     Input("str-file-upload", "contents"),
     Input("target-acos", "value"),
     Input("campaign-table", "selected_rows")],
    [State("campaign-table", "data")]
)
def update_output(bulk_content, str_content, target_acos, selected_campaign, campaign_data):
    if not bulk_content or not str_content:
        return "Please upload both files.", [], [], [], [], [], []

    bulk_file = parse_contents(bulk_content)
    str_file = parse_contents(str_content)

    bulk_data = bulk_file.parse("Sponsored Products Campaigns")
    str_data = str_file.parse("Sponsored_Products_Search_term_")

    data = load_and_clean_data(bulk_data, str_data)
    metrics = calculate_metrics(data, target_acos / 100)

    campaigns = metrics["campaigns"]
    keywords = metrics["keywords"]
    search_terms = metrics["search_terms"]

    # Audit Summary
    summary = {
        "Total Campaigns": len(campaigns),
        "Total Keywords": len(keywords),
        "Total Search Terms": len(search_terms),
        "Average ACOS": f"{round(campaigns['ACOS'].mean() * 100, 1)}%",
        "Total Revenue": f"${round(campaigns['Sales'].sum(), 2)}",
        "Total Clicks": int(campaigns["Clicks"].sum()),
        "Increase Bid Actions": len(keywords[keywords["Action"] == "Increase Bid"]),
        "Reduce Bid Actions": len(keywords[keywords["Action"] == "Reduce Bid"]),
        "Pause Keyword Actions": len(keywords[keywords["Action"] == "Pause"]),
        "Graduate Search Term Actions": len(search_terms[search_terms["Action"] == "Graduate"]),
        "Negate Search Term Actions": len(search_terms[search_terms["Action"] == "Negate"]),
    }

    summary_div = html.Div([
        html.H3("Audit Summary"),
        html.Ul([
            html.Li(f"{key}: {value}") for key, value in summary.items()
        ])
    ])

    # Filter keywords by selected campaign
    if selected_campaign and campaign_data:
        selected_campaign_name = campaign_data[selected_campaign[0]]['Campaign Name']
        keywords = keywords[keywords['Campaign Name'] == selected_campaign_name]

    # Prepare DataTables
    campaign_table = campaigns.to_dict("records")
    keyword_table = keywords.to_dict("records")
    search_term_table = search_terms.to_dict("records")

    campaign_columns = [{"name": col, "id": col} for col in campaigns.columns]
    keyword_columns = [{"name": col, "id": col} for col in keywords.columns]
    search_term_columns = [{"name": col, "id": col} for col in search_terms.columns]

    return summary_div, campaign_table, campaign_columns, keyword_table, keyword_columns, search_term_table, search_term_columns


# Run the app
if __name__ == "__main__":
    app.run_server(debug=True)
