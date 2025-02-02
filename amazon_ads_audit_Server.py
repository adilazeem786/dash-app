import dash
from dash import dcc, html, Input, Output, State
from dash import dash_table
import pandas as pd
import io
import base64
import os

# File paths for local debugging
bulk_file_path = os.path.join(os.getcwd(), 'Bulk File 30 Days.xlsx')
str_file_path = os.path.join(os.getcwd(), 'STR 30 Days.xlsx')

def load_and_clean_data(bulk_data, str_data):
    # ✅ Strip leading and trailing spaces from all column names
    bulk_data.columns = bulk_data.columns.str.strip()
    str_data.columns = str_data.columns.str.strip()
    
    # ✅ Rename columns based on your preferences
    bulk_column_renames = {
        "Campaign Name": "Campaign",
        "Campaign Name (Informational only)": "Campaign_1",
        "Ad Group Name": "Ad Group",
        "Ad Group Name (Informational only)": "Ad Group_1",
        "Keyword Text": "Keyword",
        "Impressions": "Imp",
        "Click-through Rate": "CTR",
        "Conversion Rate": "CVR"
    }

    search_term_column_renames = {
        "Campaign Name": "Campaign",
        "Ad Group Name": "Ad Group",
        "Targeting": "Keyword",
        "Customer Search Term": "CST",
        "Impressions": "Imp",
        "Click-Thru Rate (CTR)": "CTR",
        "Cost Per Click (CPC)": "CPC",
        "7 Day Total Sales": "Sales",
        "Total Advertising Cost of Sales (ACOS)": "ACOS",
        "7 Day Total Orders (#)": "Orders",
        "7 Day Total Units (#)": "Units",
        "7 Day Conversion Rate": "CVR"
    }
    
    
    # ✅ Apply renaming
    bulk_data.rename(columns=bulk_column_renames, inplace=True)
    str_data.rename(columns=search_term_column_renames, inplace=True)
    
    bulk_data = bulk_data.dropna(subset=["Entity"]).reset_index(drop=True)
    str_data = str_data.dropna(subset=["Campaign", "CST"]).reset_index(drop=True)

    campaigns = bulk_data[bulk_data["Entity"] == "Campaign"]
    ad_groups = bulk_data[bulk_data["Entity"] == "Ad group"]
    keywords = bulk_data[bulk_data["Entity"] == "Keyword"]
    placements = bulk_data[bulk_data["Entity"] == "Placement"]

    # ✅ Ensure `keywords` always exists
    if "Keyword" in bulk_data.columns:
        keywords = bulk_data[bulk_data["Entity"] == "Keyword"]
        print("Available columns in keywords:", keywords.columns)
    else:
        keywords = pd.DataFrame()  # Empty DataFrame to prevent crashes
        print("No 'Keyword' column found in bulk_data")

    # ✅ Merge "Campaign_1" for keywords only if keywords is not empty
    if not keywords.empty:
        keywords = keywords.merge(
            campaigns[["Campaign", "Campaign_1"]],
            left_on="Campaign_1",
            right_on="Campaign_1",
            how="left"
        )


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
    if "CTR" in keywords.columns:
        keywords["CTR"] = (keywords["CTR"] * 100).round(2)

    if "CVR" in keywords.columns:
        keywords["CVR"] = (keywords["CVR"] * 100).round(2)

    if "ACOS" in keywords.columns:
        keywords["ACOS"] = (keywords["ACOS"] * 100).round(2)

    if "CTR" in search_terms.columns:
        search_terms["CTR"] = (search_terms["CTR"] * 100).round(2)

    # ✅ Convert ACOS to percentage and round to 2 decimal places
    if "Sales" in search_terms.columns and "Spend" in search_terms.columns:
        search_terms["ACOS"] = ((search_terms["Spend"] / search_terms["Sales"]).replace([float('inf'), -float('inf')], 0) * 100).round(2)
    else:
        search_terms["ACOS"] = 0  # Prevents error if Sales column is missing

    if "CVR" in search_terms.columns:
        search_terms["CVR"] = (search_terms["CVR"] * 100).round(2)

    # ✅ Round numeric values to 2 decimal places
    if "CPC" in search_terms.columns:
        search_terms["CPC"] = search_terms["CPC"].round(2)

    if "Spend" in search_terms.columns:
        search_terms["Spend"] = search_terms["Spend"].round(2)

    if "Sales" in search_terms.columns:
        search_terms["Sales"] = search_terms["Sales"].round(2)

    if "Max Bid" in keywords.columns:
        keywords["Max Bid"] = keywords["Max Bid"].round(2)
        
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
    keywords["RPC"] = (keywords["Sales"] / keywords["Clicks"].replace(0, 1))
    keywords["Max Bid"] = keywords["RPC"] * target_acos
    keywords["Action"] = keywords.apply(
        lambda row: "Increase Bid" if row["Max Bid"] > row["CPC"] else
        ("Reduce Bid" if row["Max Bid"] < row["CPC"] else
         ("Pause" if row["Clicks"] > 4 and row["Orders"] == 0 else "Do Nothing")),
        axis=1
    )

    # ✅ Round Max Bid to 2 decimal places (without recalculating)
    keywords["Max Bid"] = keywords["Max Bid"].round(2)
    keywords["RPC"] = keywords["RPC"].round(2)

    
    # Search term-level actions
    search_terms["Action"] = search_terms.apply( 
        lambda row: "Graduate" if row["ACOS"] < (target_acos * 100) and row["Orders"] >= 2 and row["Match Type"].strip().lower() != "exact" else
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
    html.Div([
    html.Label("Enter Target ACOS as a percentage (e.g., 35 for 35%)", style={"font-weight": "bold", "margin-bottom": "5px"}),
    dcc.Input(id="target-acos", type="number", placeholder="Enter Target ACOS (%)", value=35, step=1),
    ]),
    # ✅ Reset Filter Button First
    html.Div([
        html.Button("Reset Filters", id="reset-btn", n_clicks=0, style={"background-color": "red", "color": "white", "margin-bottom": "10px"}),
    ], style={"margin-bottom": "20px"}),

    # ✅ Then Add the Keyword Action Filters Below
    html.H3("Filter by Keyword Actions"),
    html.Div([
        html.Button("Increase Bid", id="increase-bid-btn", n_clicks=0, style={"margin-right": "10px"}),
        html.Button("Reduce Bid", id="reduce-bid-btn", n_clicks=0, style={"margin-right": "10px"}),
        html.Button("Pause", id="pause-btn", n_clicks=0, style={"margin-right": "10px"}),
        html.Button("Do Nothing", id="do-nothing-btn", n_clicks=0),
    ], style={"margin-bottom": "20px"}),
    
    html.H3("Filter by Search Term Actions"),
    html.Div([
        html.Button("Graduate", id="graduate-btn", n_clicks=0, style={"margin-right": "10px"}),
        html.Button("Negate", id="negate-btn", n_clicks=0, style={"margin-right": "10px"}),
        html.Button("Do Nothing", id="do-nothing-search-btn", n_clicks=0),
        html.Button("Find Duplicates", id="duplicate-btn", n_clicks=0, style={"margin-left": "20px", "background-color": "orange", "color": "white"}),
    ], style={"margin-bottom": "20px"}),


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
     Input("search-term-dropdown", "value"),
     Input("increase-bid-btn", "n_clicks"),  # ✅ Add button inputs
     Input("reduce-bid-btn", "n_clicks"),
     Input("pause-btn", "n_clicks"),
     Input("do-nothing-btn", "n_clicks"),
     Input("reset-btn", "n_clicks"),
     Input("graduate-btn", "n_clicks"),
     Input("negate-btn", "n_clicks"),
     Input("do-nothing-search-btn", "n_clicks"),
     Input("duplicate-btn", "n_clicks")]  # ✅ Find Duplicates button
     
     # ✅ Add Reset Button as Input]
)
def update_output(bulk_content, str_content, target_acos, selected_campaigns, selected_keywords, selected_search_terms,
                  increase_bid_clicks, reduce_bid_clicks, pause_clicks, do_nothing_clicks, reset_clicks,
                  graduate_clicks, negate_clicks, do_nothing_search_clicks, duplicate_clicks):
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
    
    ctx = dash.callback_context
    action_filter = None

    if ctx.triggered:
        button_id = ctx.triggered[0]["prop_id"].split(".")[0]

        if button_id == "increase-bid-btn":
            action_filter = "Increase Bid"
        elif button_id == "reduce-bid-btn":
            action_filter = "Reduce Bid"
        elif button_id == "pause-btn":
            action_filter = "Pause"
        elif button_id == "do-nothing-btn":
            action_filter = "Do Nothing"
        elif button_id == "reset-btn":
            action_filter = None

    # ✅ Apply keyword action filter if a button was clicked
    if action_filter:
        keywords = keywords[keywords["Action"] == action_filter]

        # ✅ Filter search terms based on keywords
        filtered_keywords = keywords["Keyword"].unique()
        search_terms = search_terms[search_terms["Keyword"].isin(filtered_keywords)]

        # ✅ Filter campaigns based on keywords
        filtered_campaigns = keywords["Campaign_1"].unique()
        campaigns = campaigns[campaigns["Campaign_1"].isin(filtered_campaigns)]
    else:
        # ✅ Reset keywords, campaigns, and search terms to original state
        keywords = metrics["keywords"]
        search_terms = metrics["search_terms"]
        campaigns = metrics["campaigns"]

    # ✅ Generate search term dropdown options
    search_term_options = [{"label": term, "value": term} for term in search_terms["CST"].unique()]

    # ✅ If a search term is selected, filter the keywords and campaigns accordingly
    if selected_search_terms:
       search_terms = search_terms[search_terms["CST"].isin(selected_search_terms)]

       # ✅ Filter keywords based on search terms
       filtered_keywords = search_terms["Keyword"].unique()
       keywords = keywords[keywords["Keyword"].isin(filtered_keywords)]

       # ✅ Filter campaigns based on keywords
       filtered_campaigns = keywords["Campaign_1"].unique()
       campaigns = campaigns[campaigns["Campaign_1"].isin(filtered_campaigns)]


    # ✅ Determine which button was clicked
    ctx = dash.callback_context
    search_term_filter = None
    find_duplicates = False

    if ctx.triggered:
        button_id = ctx.triggered[0]["prop_id"].split(".")[0]

        # ✅ Search Term Action Filters
        if button_id == "graduate-btn":
            search_term_filter = "Graduate"
        elif button_id == "negate-btn":
            search_term_filter = "Negate"
        elif button_id == "do-nothing-search-btn":
            search_term_filter = "Do Nothing"
        elif button_id == "duplicate-btn":
            find_duplicates = True  # ✅ Flag to filter duplicate search terms

    # ✅ Apply search term action filter
    if search_term_filter:
        search_terms = search_terms[search_terms["Action"] == search_term_filter]

        # ✅ Filter relevant keywords and campaigns
        filtered_keywords = search_terms["Keyword"].unique()
        keywords = keywords[keywords["Keyword"].isin(filtered_keywords)]

        filtered_campaigns = keywords["Campaign_1"].unique()
        campaigns = campaigns[campaigns["Campaign_1"].isin(filtered_campaigns)]

    # ✅ Find and filter duplicate search terms
    if find_duplicates:
        duplicate_terms = search_terms[search_terms.duplicated(subset=["CST"], keep=False)]
        search_terms = duplicate_terms.sort_values(by="CST", ascending=True)  # ✅ Sort by CST in ascending order


        # ✅ Filter relevant keywords and campaigns
        filtered_keywords = search_terms["Keyword"].unique()
        keywords = keywords[keywords["Keyword"].isin(filtered_keywords)]

        filtered_campaigns = keywords["Campaign_1"].unique()
        campaigns = campaigns[campaigns["Campaign_1"].isin(filtered_campaigns)]

    
    # ✅ Filter campaigns dynamically based on selected campaign
    campaign_options = [{"label": name, "value": name} for name in campaigns["Campaign_1"].unique()]
    if selected_campaigns:
       campaigns = campaigns[campaigns["Campaign_1"].isin(selected_campaigns)]
       keywords = keywords[keywords["Campaign_1"].isin(selected_campaigns)]
       search_terms = search_terms[search_terms["Campaign"].isin(selected_campaigns)]

    # ✅ Filter keywords dynamically based on selected keyword
    keyword_options = [{"label": name, "value": name} for name in keywords["Keyword"].unique()]
    if selected_keywords:
       keywords = keywords[keywords["Keyword"].isin(selected_keywords)]
       search_terms = search_terms[search_terms["Keyword"].isin(selected_keywords)]
       filtered_campaigns = keywords["Campaign_1"].unique()
       campaigns = campaigns[campaigns["Campaign_1"].isin(filtered_campaigns)]


    # ✅ Prepare DataTables
    search_term_table = search_terms.to_dict("records")
    search_term_columns = [{"name": col, "id": col} for col in search_terms.columns]

    keyword_table = keywords.to_dict("records")
    keyword_columns = [{"name": col, "id": col} for col in keywords.columns]

    campaign_table = campaigns.to_dict("records")
    campaign_columns = [{"name": col, "id": col} for col in campaigns.columns]


    # ✅ Select only relevant columns for campaigns
    campaign_columns_to_show = [
         "Campaign", "Daily Budget", "Bidding Strategy", "Imp", "Clicks", "CTR", "Spend", "CPC", "Sales", "ACOS", "Orders", "CVR"
    ]
    campaigns = campaigns[campaign_columns_to_show]

    # ✅ Select only the required columns for search term metrics
    search_term_columns_to_show = [
         "Campaign", "Ad Group", "Keyword", "Match Type", "CST",
         "Imp", "Clicks", "CTR", "CPC", "Spend",
         "Sales", "ACOS", "Orders", "CVR", "Action"
    ]
    search_terms = search_terms[search_term_columns_to_show]

    # ✅ Select only relevant columns for keywords
    keyword_columns_to_show = [
         "Campaign_1", "Ad Group_1", "Bid", "Keyword",
         "Match Type", "Imp", "Clicks", "CTR", "Spend", "Sales", "Orders", "Units",
         "CVR", "ACOS", "CPC", "Max Bid", "RPC", "Action"
    ]
    keywords = keywords[keyword_columns_to_show]
    # ✅ Calculate ACOS as (Total Spend / Total Sales) * 100
    total_spend = campaigns["Spend"].sum()
    total_sales = campaigns["Sales"].sum()

    # ✅ Avoid division by zero
    average_acos = (total_spend / total_sales * 100) if total_sales > 0 else 0

    # ✅ Use this new `average_acos` calculation inside the summary
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

    # ✅ Add this line above the `if __name__ == "__main__"` block
    server = app.server  # Required for deployment on Render

    # Run the app
   import os

   if __name__ == "__main__":
       port = int(os.environ.get("PORT", 8080))  # Default to port 8080 if PORT is not set
       app.run(host="0.0.0.0", port=port, debug=False)
