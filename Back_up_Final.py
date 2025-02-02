import dash
from dash import dcc, html, Input, Output, State
import dash_table
import pandas as pd
import io
import base64
import os

# File paths for local debugging
bulk_file_path = os.path.join(os.getcwd(), 'Bulk File 30 Days.xlsx')
str_file_path = os.path.join(os.getcwd(), 'STR 30 Days.xlsx')

def load_and_clean_data(bulk_data, str_data):
    bulk_data = bulk_data.dropna(subset=["Entity"]).reset_index(drop=True)
    str_data = str_data.dropna(subset=["Campaign Name", "Customer Search Term"]).reset_index(drop=True)

    campaigns = bulk_data[bulk_data["Entity"] == "Campaign"]
    ad_groups = bulk_data[bulk_data["Entity"] == "Ad group"]
    keywords = bulk_data[bulk_data["Entity"] == "Keyword"]

    # Match "Campaign Name (Informational only)" for both campaigns and keywords
    keywords = keywords.merge(campaigns[["Campaign Name", "Campaign Name (Informational only)"]],
                              left_on="Campaign Name (Informational only)",
                              right_on="Campaign Name (Informational only)",
                              how="left")

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

    # ✅ Convert to percentage and round to 2 decimal places
    if "Click-Thru Rate (CTR)" in search_terms.columns:
        search_terms["Click-Thru Rate (CTR)"] = (search_terms["Click-Thru Rate (CTR)"] * 100).round(2)

    if "Total Advertising Cost of Sales (ACOS) " in search_terms.columns:
        search_terms["Total Advertising Cost of Sales (ACOS) "] = (search_terms["Total Advertising Cost of Sales (ACOS) "] * 100).round(2)

    if "7 Day Conversion Rate" in search_terms.columns:
        search_terms["7 Day Conversion Rate"] = (search_terms["7 Day Conversion Rate"] * 100).round(2)

    # ✅ Round numeric values to 2 decimal places
    if "Cost Per Click (CPC)" in search_terms.columns:
        search_terms["Cost Per Click (CPC)"] = search_terms["Cost Per Click (CPC)"].round(2)

    if "Spend" in search_terms.columns:
        search_terms["Spend"] = search_terms["Spend"].round(2)

    if "7 Day Total Sales " in search_terms.columns:
        search_terms["7 Day Total Sales "] = search_terms["7 Day Total Sales "].round(2)
        
    # Ensure necessary columns exist
    required_columns = {
        "campaigns": ["Sales", "Clicks", "Impressions", "Spend", "Orders", "Daily Budget", "Bidding Strategy"],
        "keywords": ["Sales", "Clicks", "Spend", "Orders", "Ad Group Name", "Campaign Name"],
        "search_terms": ["Sales", "Clicks", "Spend", "Orders", "Ad Group Name", "Campaign Name"],
    }

    for df_name, cols in required_columns.items():
        df = locals()[df_name]
        for col in cols:
            if col not in df.columns:
                df[col] = 0

    # Campaign-level metrics
    campaigns["CTR"] = ((campaigns["Clicks"] / campaigns["Impressions"]).fillna(0) * 100).round(2)
    campaigns["CPC"] = (campaigns["Spend"] / campaigns["Clicks"].replace(0, 1) * 100).round(2)
    campaigns["ACOS"] = (campaigns["Spend"] / campaigns["Sales"].replace(0, 1) * 100).round(2)
    campaigns["Conversion Rate"] = ((campaigns["Orders"] / campaigns["Clicks"]).fillna(0) * 100).round(2)
    campaigns["Spend"] = campaigns["Spend"].round(2)

    # Keyword-level metrics and actions
    keywords["Max Bid"] = (keywords["Sales"] / keywords["Clicks"].replace(0, 1)) * target_acos
    keywords["Action"] = keywords.apply(
        lambda row: "Increase Bid" if row["Max Bid"] > row["Spend"] else
        ("Reduce Bid" if row["Max Bid"] < row["Spend"] else
         ("Pause" if row["Clicks"] > 4 and row["Orders"] == 0 else "Do Nothing")),
        axis=1
    )
    # ✅ Convert to percentage and round to 2 decimal places
    keywords["Click-through Rate"] = (keywords["Click-through Rate"] * 100).round(2)
    keywords["Conversion Rate"] = (keywords["Conversion Rate"] * 100).round(2)
    keywords["ACOS"] = (keywords["ACOS"] * 100).round(2)

    # ✅ Round Max Bid to 2 decimal places (without recalculating)
    keywords["Max Bid"] = keywords["Max Bid"].round(2)

    
    # Search term-level actions
    search_terms["ACOS"] = search_terms["Spend"] / search_terms["7 Day Total Sales "]
    search_terms["Action"] = search_terms.apply(
        lambda row: "Graduate" if row["ACOS"] < target_acos and row["7 Day Total Orders (#)"] >= 2 else
        ("Negate" if row["Clicks"] > 3 and row["7 Day Total Orders (#)"] == 0 else "Do Nothing"),
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
    dcc.Dropdown(
        id="campaign-dropdown",
        multi=True,
        placeholder="Select Campaign(s)",
    ),
    dash_table.DataTable(id="campaign-table"),
    html.H3("Keyword Metrics"),
    dcc.Dropdown(
        id="keyword-dropdown",
        multi=True,
        placeholder="Select Keyword(s)",
    ),
    dash_table.DataTable(id="keyword-table"),
    html.H3("Search Term Metrics"),
    dcc.Dropdown(
        id="search-term-dropdown",
        multi=True,
        placeholder="Select Search Term(s)",
    ),
    dash_table.DataTable(id="search-term-table"),
])

def parse_contents(contents):
    content_type, content_string = contents.split(",")
    decoded = base64.b64decode(content_string)
    return pd.ExcelFile(io.BytesIO(decoded))

@app.callback(
    [Output("audit-summary", "children"),
     Output("campaign-dropdown", "options"),
     Output("campaign-table", "data"),
     Output("campaign-table", "columns"),
     Output("keyword-dropdown", "options"),
     Output("keyword-table", "data"),
     Output("keyword-table", "columns"),
     Output("search-term-dropdown", "options"),
     Output("search-term-table", "data"),
     Output("search-term-table", "columns")],
    [Input("bulk-file-upload", "contents"),
     Input("str-file-upload", "contents"),
     Input("target-acos", "value"),
     Input("campaign-dropdown", "value"),
     Input("keyword-dropdown", "value"),
     Input("search-term-dropdown", "value")]
)
def update_output(bulk_content, str_content, target_acos, selected_campaigns, selected_keywords, selected_search_terms):
    if not bulk_content or not str_content:
        return "Please upload both files.", [], [], [], [], [], [], [], [], []

    bulk_file = parse_contents(bulk_content)
    str_file = parse_contents(str_content)

    bulk_data = bulk_file.parse("Sponsored Products Campaigns")
    str_data = str_file.parse("Sponsored_Products_Search_term_")

    data = load_and_clean_data(bulk_data, str_data)
    metrics = calculate_metrics(data, target_acos / 100)

    campaigns = metrics["campaigns"]
    keywords = metrics["keywords"]
    search_terms = metrics["search_terms"]

    # ✅ Generate search term dropdown options
    search_term_options = [{"label": term, "value": term} for term in search_terms["Customer Search Term"].unique()]

    # ✅ If a search term is selected, filter the keywords and campaigns accordingly
    if selected_search_terms:
       search_terms = search_terms[search_terms["Customer Search Term"].isin(selected_search_terms)]

    # ✅ Filter keywords based on search terms
       filtered_keywords = search_terms["Targeting"].unique()
       keywords = keywords[keywords["Keyword Text"].isin(filtered_keywords)]

    # ✅ Filter campaigns based on keywords
       filtered_campaigns = keywords["Campaign Name (Informational only)"].unique()
       campaigns = campaigns[campaigns["Campaign Name (Informational only)"].isin(filtered_campaigns)]

    # ✅ Filter campaigns dynamically based on selected campaign
    campaign_options = [{"label": name, "value": name} for name in campaigns["Campaign Name (Informational only)"].unique()]
    if selected_campaigns:
       campaigns = campaigns[campaigns["Campaign Name (Informational only)"].isin(selected_campaigns)]

       # ✅ Filter keywords linked to the selected campaigns
       keywords = keywords[keywords["Campaign Name (Informational only)"].isin(selected_campaigns)]

       # ✅ Filter search terms linked to the selected campaigns
       search_terms = search_terms[search_terms["Campaign Name"].isin(selected_campaigns)]

    # ✅ Filter keywords dynamically based on selected keyword
    keyword_options = [{"label": name, "value": name} for name in keywords["Keyword Text"].unique()]
    if selected_keywords:
       keywords = keywords[keywords["Keyword Text"].isin(selected_keywords)]

       # ✅ Filter search terms linked to the selected keywords
       search_terms = search_terms[search_terms["Targeting"].isin(selected_keywords)]

       # ✅ Filter campaigns linked to the selected keywords
       filtered_campaigns = keywords["Campaign Name (Informational only)"].unique()
       campaigns = campaigns[campaigns["Campaign Name (Informational only)"].isin(filtered_campaigns)]



    # ✅ Prepare DataTables
    search_term_table = search_terms.to_dict("records")
    search_term_columns = [{"name": col, "id": col} for col in search_terms.columns]

    keyword_table = keywords.to_dict("records")
    keyword_columns = [{"name": col, "id": col} for col in keywords.columns]

    campaign_table = campaigns.to_dict("records")
    campaign_columns = [{"name": col, "id": col} for col in campaigns.columns]


    # Select only relevant columns for campaigns
    campaign_columns_to_show = [
        "Campaign Name", "Daily Budget", "Bidding Strategy", "Impressions", "Clicks", "CTR", "Spend", "CPC", "Sales", "ACOS", "Orders", "Conversion Rate"
    ]
    campaigns = campaigns[campaign_columns_to_show]

    # ✅ Select only the required columns for search term metrics
    search_term_columns_to_show = [
    "Campaign Name", "Ad Group Name", "Targeting", "Match Type", "Customer Search Term",
    "Impressions", "Clicks", "Click-Thru Rate (CTR)", "Cost Per Click (CPC)", "Spend",
    "7 Day Total Sales ", "Total Advertising Cost of Sales (ACOS) ", 
    "7 Day Total Orders (#)", "7 Day Conversion Rate", "Action"
    ]

    # ✅ Ensure only these columns are displayed in the Search Term Metrics table
    search_terms = search_terms[search_term_columns_to_show]


    # Select only relevant columns for keywords
    keyword_columns_to_show = [
        "Campaign Name (Informational only)", "Ad Group Name (Informational only)", "Bid", "Keyword Text",
    "Match Type", "Impressions", "Clicks", "Click-through Rate", "Spend", "Sales", "Orders", "Units",
    "Conversion Rate", "ACOS", "CPC", "Max Bid", "Action"
    ]
    keywords = keywords[keyword_columns_to_show]
	
    # ✅ Calculate ACOS as (Total Spend / Total Sales) * 100
    total_spend = campaigns["Spend"].sum()
    total_sales = campaigns["Sales"].sum()

    # ✅ Avoid division by zero
    average_acos = (total_spend / total_sales * 100) if total_sales > 0 else 0
	
	# Audit Summary
    summary = {
        "Total Campaigns": len(campaigns),
        "Total Keywords": len(keywords),
        "Total Search Terms": len(search_terms),
        "ACOS": f"{round(average_acos, 2)}%",
        "Total Revenue": f"${round(campaigns['Sales'].sum(), 2)}",
        "Total Clicks": int(campaigns["Clicks"].sum()),
    }

    summary_div = html.Div([
        html.H3("Audit Summary"),
        html.Ul([
            html.Li(f"{key}: {value}") for key, value in summary.items()
        ])
    ])

    # Prepare DataTables
    campaign_table = campaigns.to_dict("records")
    keyword_table = keywords.to_dict("records")
    search_term_table = search_terms.to_dict("records")

    campaign_columns = [{"name": col, "id": col} for col in campaigns.columns]
    keyword_columns = [{"name": col, "id": col} for col in keywords.columns]
    search_term_columns = [{"name": col, "id": col} for col in search_terms.columns]

    return summary_div, campaign_options, campaign_table, campaign_columns, keyword_options, keyword_table, keyword_columns, search_term_options, search_term_table, search_term_columns

# Run the app
if __name__ == "__main__":
    app.run_server(debug=True)
