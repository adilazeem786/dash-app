import pandas as pd
import streamlit as st


def load_and_clean_data(bulk_file_path, str_file_path):
    """
    Load and clean bulk file and search term report.

    Parameters:
    bulk_file_path (str): Path to the bulk file.
    str_file_path (str): Path to the search term report.

    Returns:
    dict: Cleaned dataframes for further processing.
    """
    # Load the bulk file (Sponsored Products Campaigns sheet)
    bulk_file = pd.ExcelFile(bulk_file_path)
    bulk_data = bulk_file.parse("Sponsored Products Campaigns")

    # Load the search term report
    str_file = pd.ExcelFile(str_file_path)
    str_data = str_file.parse("Sponsored_Products_Search_term_")

    # Clean bulk data: Remove unnecessary rows/columns
    bulk_data = bulk_data.dropna(subset=["Entity"])
    bulk_data = bulk_data.reset_index(drop=True)

    # Clean search term report: Basic cleanup
    str_data = str_data.dropna(subset=["Campaign Name", "Customer Search Term"])
    str_data = str_data.reset_index(drop=True)

    # Extract hierarchies from the bulk file
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
        "search_terms": str_data
    }


def calculate_metrics(data, target_acos):
    """
    Calculate essential metrics for analysis.

    Parameters:
    data (dict): Dictionary containing cleaned dataframes.
    target_acos (float): Target ACOS defined by the user.

    Returns:
    dict: Dataframes with calculated metrics and actions.
    """
    campaigns = data["campaigns"].copy()
    keywords = data["keywords"].copy()
    search_terms = data["search_terms"].copy()
    placements = data["placements"].copy()

    # Ensure necessary columns exist
    for df, col in [(campaigns, "Sales"), (keywords, "Sales"), (search_terms, "Sales"), (search_terms, "Orders")]:
        if col not in df.columns:
            df[col] = 0

    # Campaign-level metrics
    campaigns["CTR"] = (campaigns["Clicks"] / campaigns["Impressions"]).fillna(0)
    campaigns["CPC"] = campaigns["Spend"] / campaigns["Clicks"].replace(0, 1)
    campaigns["ACOS"] = campaigns["Spend"] / campaigns["Sales"].replace(0, 1)

    # Placement-level actions
    placements["Percentage"] = placements["Percentage"].fillna(0).astype(float)
    placements["ACOS"] = placements["ACOS"].fillna(0).astype(float)
    placements["Action"] = placements.apply(
        lambda row: "Increase Placement Percentage" if row["ACOS"] < target_acos and row["Percentage"] > 0 else
        ("Decrease Placement Percentage" if row["ACOS"] > target_acos and row["Percentage"] > 0 else "Do Nothing"),
        axis=1
    )

    # Keyword-level metrics and actions
    keywords["Max Bid"] = (keywords["Sales"] / keywords["Clicks"].replace(0, 1)) * target_acos
    keywords["Action"] = keywords.apply(
        lambda row: "Increase Bid" if row["Max Bid"] > row["CPC"] else
        ("Reduce Bid" if row["Max Bid"] < row["CPC"] else
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
        "campaigns": campaigns,
        "keywords": keywords,
        "search_terms": search_terms,
        "placements": placements
    }


def generate_audit_summary(metrics):
    """
    Generate a summary of the audit.

    Parameters:
    metrics (dict): Dictionary containing calculated metrics.

    Returns:
    dict: Summary metrics.
    """
    campaigns = metrics["campaigns"]
    keywords = metrics["keywords"]
    search_terms = metrics["search_terms"]
    placements = metrics["placements"]

    summary = {
        "Total Campaigns": len(campaigns),
        "Total Keywords": len(keywords),
        "Total Search Terms": len(search_terms),
        "ACOS": f"{round(campaigns['ACOS'].mean() * 100, 1)}%",
        "Total Revenue": f"${round(campaigns['Sales'].sum(), 2)}",
        "Total Spend": f"${round(campaigns['Spend'].sum(), 2)}",
        "Total Clicks": int(campaigns["Clicks"].sum()),
        "Total Orders": int(campaigns["Orders"].sum()),
        "Conversion Rate": f"{round((campaigns['Orders'].sum() / campaigns['Clicks'].sum()) * 100, 1) if campaigns['Clicks'].sum() > 0 else 0}%",
        "Increase Placement Percentage Actions": len(placements[placements["Action"] == "Increase Placement Percentage"]),
        "Decrease Placement Percentage Actions": len(placements[placements["Action"] == "Decrease Placement Percentage"]),
        "Increase Bid Actions": len(keywords[keywords["Action"] == "Increase Bid"]),
        "Reduce Bid Actions": len(keywords[keywords["Action"] == "Reduce Bid"]),
        "Pause Keyword Actions": len(keywords[keywords["Action"] == "Pause"]),
        "Graduate Search Term Actions": len(search_terms[search_terms["Action"] == "Graduate"]),
        "Negate Search Term Actions": len(search_terms[search_terms["Action"] == "Negate"])
    }
    return summary


# Streamlit App
st.title("Amazon Ads Audit Program")

bulk_file = st.file_uploader("Upload Bulk File (Excel)", type="xlsx")
str_file = st.file_uploader("Upload Search Term Report (Excel)", type="xlsx")
target_acos = st.number_input("Enter Target ACOS (%)", min_value=0.0, max_value=100.0, value=30.0, step=1.0) / 100

if bulk_file and str_file:
    data = load_and_clean_data(bulk_file, str_file)
    metrics = calculate_metrics(data, target_acos)
    summary = generate_audit_summary(metrics)

    # Audit Summary
    st.subheader("Audit Summary")
    cols = st.columns(3)
    summary_items = list(summary.items())
    for i, (key, value) in enumerate(summary_items):
        with cols[i % 3]:
            st.metric(label=key, value=value)

    # Campaign Metrics
    st.subheader("Campaign Metrics")
    st.dataframe(metrics["campaigns"])

    # Keyword Metrics
    st.subheader("Keyword Metrics")
    st.dataframe(metrics["keywords"])

    # Search Term Metrics
    st.subheader("Search Term Metrics")
    st.dataframe(metrics["search_terms"])
