import sqlite3
import pandas as pd
import streamlit as st
import plotly.express as px

# Configure the web page
st.set_page_config(page_title="Invoice Analytics", page_icon="📊", layout="wide")
st.title("📊 GST Invoice Analytics Dashboard")
st.markdown("Automated insights extracted from OCR-processed PDF invoices.")

# 1. Securely load data from the SQLite Database
@st.cache_data
def load_data():
    conn = sqlite3.connect("data/finance_system.db")
    query = """
        SELECT invoice_id, invoice_date, vendor_name, 
               subtotal, tax_amount, grand_total, validation_passed
        FROM processed_invoices
        WHERE validation_passed = 1
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Convert string dates to actual datetime objects for graphing
    df['invoice_date'] = pd.to_datetime(df['invoice_date'], format='%d-%m-%Y', errors='coerce')
    return df

df = load_data()

if df.empty:
    st.warning("No validated invoice data found. Please run the OCR pipeline first.")
else:
    # 2. Top-Level KPIs
    st.markdown("### Executive Summary")
    total_spend = df['grand_total'].sum()
    total_tax = df['tax_amount'].sum()
    invoice_count = len(df)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Expenditure", f"Rs. {total_spend:,.2f}")
    col2.metric("Total GST Paid (18%)", f"Rs. {total_tax:,.2f}")
    col3.metric("Valid Invoices Processed", invoice_count)

    st.divider()

    # 3. Interactive Charts
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.markdown("#### Spend by Vendor")
        # Group data by vendor
        vendor_spend = df.groupby('vendor_name')['grand_total'].sum().reset_index()
        vendor_spend = vendor_spend.sort_values(by='grand_total', ascending=False).head(10)
        
        fig_vendor = px.bar(
            vendor_spend, 
            x='grand_total', 
            y='vendor_name', 
            orientation='h',
            color='grand_total',
            color_continuous_scale='Blues'
        )
        fig_vendor.update_layout(xaxis_title="Total Spend (Rs.)", yaxis_title="Vendor", showlegend=False)
        st.plotly_chart(fig_vendor, use_container_width=True)

    with col_chart2:
        st.markdown("#### Expenditure Timeline")
        # Group data by date
        daily_spend = df.groupby('invoice_date')['grand_total'].sum().reset_index()
        daily_spend = daily_spend.sort_values(by='invoice_date')
        
        fig_timeline = px.line(
            daily_spend, 
            x='invoice_date', 
            y='grand_total',
            markers=True
        )
        fig_timeline.update_layout(xaxis_title="Date", yaxis_title="Daily Spend (Rs.)")
        st.plotly_chart(fig_timeline, use_container_width=True)

    st.divider()

    # 4. Raw Data Explorer
    st.markdown("#### Database Explorer")
    st.dataframe(
        df.sort_values(by='invoice_date', ascending=False), 
        use_container_width=True,
        hide_index=True
    )