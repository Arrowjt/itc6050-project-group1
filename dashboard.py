import streamlit as st
import pandas as pd
import psycopg2
import os

# Page config 
st.set_page_config(page_title="Global Air Quality Monitor", layout="wide")

# DB connection
@st.cache_resource
def get_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )

conn = get_connection()

# Title 
st.title("🌍 Global Air Quality Monitor")
st.caption("Tracking pollution trends across the world's capitals")

# KPI row
@st.cache_data(ttl=600)
def get_kpis():
    return pd.read_sql("SELECT * FROM analytics.kpi_summary", conn)

kpi_df = get_kpis()
kpis = kpi_df.iloc[0]

col1, col2, col3 = st.columns(3)
col1.metric("Cities Monitored", int(kpis["cities_monitored"]))
col2.metric("Total Readings", f"{int(kpis['total_readings']):,}")
col3.metric("Date Range", f"{kpis['earliest_date']} → {kpis['latest_date']}")

#Bar chart: top 10 most polluted cities (avg PM2.5) 
st.subheader("🏭 Top 10 Most Polluted Cities (Avg PM2.5)")

@st.cache_data(ttl=600)
def get_top_polluted_cities():
    query = """
        SELECT city, overall_avg_value
        FROM analytics.city_pollution_ranking
        WHERE parameter = 'pm25'
        ORDER BY pollution_rank
        LIMIT 10
    """
    return pd.read_sql(query, conn)

top_cities_df = get_top_polluted_cities()

# Force the category order to match ranking (not alphabetical)
top_cities_df["city"] = pd.Categorical(
    top_cities_df["city"],
    categories=top_cities_df["city"],
    ordered=True
)

chart_data = top_cities_df.set_index("city")["overall_avg_value"]
st.bar_chart(chart_data)

#Line chart: pollutant trend over time for a selected city
st.subheader("📈 Pollutant Trend Over Time")

@st.cache_data(ttl=600)
def get_available_cities():
    query = "SELECT DISTINCT city FROM analytics.city_daily_avg ORDER BY city"
    return pd.read_sql(query, conn)["city"].tolist()

@st.cache_data(ttl=600)
def get_available_parameters():
    query = "SELECT DISTINCT parameter FROM analytics.city_daily_avg ORDER BY parameter"
    return pd.read_sql(query, conn)["parameter"].tolist()

col_a, col_b = st.columns(2)
with col_a:
    selected_city = st.selectbox("Select a city", get_available_cities())
with col_b:
    selected_parameter = st.selectbox("Select a pollutant", get_available_parameters())

@st.cache_data(ttl=600)
def get_city_trend(city, parameter):
    query = """
        SELECT reading_date, avg_value
        FROM analytics.city_daily_avg
        WHERE city = %(city)s AND parameter = %(parameter)s
        ORDER BY reading_date
    """
    return pd.read_sql(query, conn, params={"city": city, "parameter": parameter})

trend_df = get_city_trend(selected_city, selected_parameter)

if not trend_df.empty:
    trend_chart_data = trend_df.set_index("reading_date")["avg_value"]
    st.line_chart(trend_chart_data)
else:
    st.info(f"No data available for {selected_city} — {selected_parameter}")

# Filters (sidebar)
st.sidebar.header("Filters")

@st.cache_data(ttl=600)
def get_available_countries():
    query = "SELECT DISTINCT country FROM analytics.city_daily_avg ORDER BY country"
    return pd.read_sql(query, conn)["country"].tolist()

countries = get_available_countries()
selected_countries = st.sidebar.multiselect("Country", countries, default=[])

parameters = get_available_parameters()
selected_params_filter = st.sidebar.multiselect("Pollutant", parameters, default=[])

date_range = st.sidebar.date_input(
    "Date range",
    value=(kpis["earliest_date"], kpis["latest_date"]),
)

# Alert table: cities where PM2.5 > WHO limit
st.subheader("🚨 WHO PM2.5 Alerts (> 25 µg/m³)")

@st.cache_data(ttl=600)
def get_alerts():
    return pd.read_sql("SELECT * FROM analytics.who_pm25_alerts ORDER BY pm25_avg_value DESC", conn)

alerts_df = get_alerts()

# Apply sidebar filters if selected
filtered_alerts = alerts_df.copy()
if selected_countries:
    filtered_alerts = filtered_alerts[filtered_alerts["country"].isin(selected_countries)]

if len(date_range) == 2:
    start_date, end_date = date_range
    filtered_alerts = filtered_alerts[
        (filtered_alerts["reading_date"] >= start_date) &
        (filtered_alerts["reading_date"] <= end_date)
    ]

st.dataframe(filtered_alerts, use_container_width=True, height=400)
st.caption(f"Showing {len(filtered_alerts):,} of {len(alerts_df):,} alert records")