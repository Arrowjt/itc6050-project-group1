import streamlit as st
import pandas as pd
import psycopg2
import os
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine

# ---- Page config ----
st.set_page_config(page_title="Global Air Quality Monitor", layout="wide")

# ---- DB connection ----
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

# ---- Title ----
st.title("🌍 Global Air Quality Monitor")
st.caption("Tracking pollution trends across the world's capitals")

# ---- KPI row ----
@st.cache_data(ttl=600)
def get_kpis():
    return pd.read_sql("SELECT * FROM analytics.kpi_summary", conn)

kpi_df = get_kpis()
kpis = kpi_df.iloc[0]

col1, col2, col3 = st.columns(3)
col1.metric("Cities Monitored", int(kpis["cities_monitored"]))
col2.metric("Total Readings", f"{int(kpis['total_readings']):,}")
col3.metric("Date Range", f"{kpis['earliest_date']} → {kpis['latest_date']}")

# ---- Bar chart: top 10 most polluted cities (avg PM2.5) ----
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

# ---- Line chart: pollutant trend over time for a selected city ----
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

# ---- Filters (sidebar) ----
st.sidebar.header("Filters")

@st.cache_data(ttl=600)
def get_available_countries():
    query = "SELECT DISTINCT country FROM analytics.city_daily_avg ORDER BY country"
    return pd.read_sql(query, conn)["country"].tolist()

countries = get_available_countries()
selected_countries = st.sidebar.multiselect("Country", countries, default=[])

parameters = get_available_parameters()
default_pollutant_idx = parameters.index("pm25") if "pm25" in parameters else 0
map_pollutant = st.sidebar.selectbox("Pollutant (map)", parameters, index=default_pollutant_idx)

date_range = st.sidebar.date_input(
    "Date range",
    value=(kpis["earliest_date"], kpis["latest_date"]),
)

# ---- Alert table: cities where PM2.5 > WHO limit ----
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


# ======================================================================
# GLOBAL MAP SECTION
# ======================================================================

st.divider()
st.subheader("🗺️ Global Air Quality Map")
st.caption("Average pollution by capital city — dot colour and size show the level. "
           "Controlled by the Pollutant filter in the sidebar.")

LAND = "rgb(233, 225, 205)"
OCEAN = "rgb(160, 200, 225)"
BORDER = "rgb(150, 140, 120)"
COAST = "rgb(120, 120, 110)"


@st.cache_resource
def get_engine():
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "air_quality")
    user = os.getenv("POSTGRES_USER", "postgres")
    pw = os.getenv("POSTGRES_PASSWORD", "")
    return create_engine(f"postgresql://{user}:{pw}@{host}:{port}/{db}")


@st.cache_data
def map_get_coords() -> pd.DataFrame:
    return pd.read_sql(
        "SELECT capital_name AS city, AVG(latitude) AS lat, AVG(longitude) AS lon "
        "FROM raw.locations GROUP BY capital_name",
        get_engine(),
    )


@st.cache_data
def map_load_alltime(pollutant: str) -> pd.DataFrame:
    df = pd.read_sql(
        "SELECT city, country, overall_avg_value AS avg_value "
        "FROM analytics.city_pollution_ranking WHERE parameter = %(p)s",
        get_engine(), params={"p": pollutant},
    )
    return df.merge(map_get_coords(), on="city", how="inner")


@st.cache_data
def map_load_monthly(pollutant: str) -> pd.DataFrame:
    df = pd.read_sql(
        """
        SELECT city, country,
               to_char(date_trunc('month', reading_date), 'YYYY-MM') AS ym,
               AVG(avg_value) AS avg_value
        FROM analytics.city_daily_avg WHERE parameter = %(p)s
        GROUP BY city, country, date_trunc('month', reading_date)
        """,
        get_engine(), params={"p": pollutant},
    )
    return df.merge(map_get_coords(), on="city", how="inner")


def map_geo_layout():
    return dict(
        projection_type="natural earth",
        showland=True, landcolor=LAND,
        showocean=True, oceancolor=OCEAN,
        showcountries=True, countrycolor=BORDER,
        showcoastlines=True, coastlinecolor=COAST,
        showlakes=True, lakecolor=OCEAN,
        bgcolor="rgba(0,0,0,0)",
        domain=dict(x=[0.03, 0.97], y=[0.32, 1.0]),
    )


map_view = st.radio("Map view", ["All-time average", "Monthly explorer"],
                    horizontal=True, key="map_view")

unit = "µg/m³"

if map_view == "All-time average":
    df = map_load_alltime(map_pollutant)
    if df.empty:
        st.warning(f"No map data for {map_pollutant}.")
    else:
        cmax = float(df["avg_value"].quantile(0.95))
        fig = px.scatter_geo(
            df, lat="lat", lon="lon", color="avg_value", size="avg_value", size_max=28,
            hover_name="city",
            hover_data={"country": True, "avg_value": ":.1f", "lat": False, "lon": False},
            color_continuous_scale="RdYlGn_r", range_color=(0, cmax),
            labels={"avg_value": f"{map_pollutant.upper()} ({unit})"},
        )
        fig.update_geos(**{k: v for k, v in map_geo_layout().items() if k != "domain"})
        fig.update_layout(height=620, margin={"r": 0, "t": 10, "l": 0, "b": 0},
                          paper_bgcolor="rgba(0,0,0,0)", font_color="#e0e0e0")
        st.plotly_chart(fig, use_container_width=True)

        ranking = df.sort_values("avg_value", ascending=False)
        st.subheader(f"Most polluted capitals (all-time) — {map_pollutant.upper()}")
        st.dataframe(
            ranking[["city", "country", "avg_value"]].head(15)
            .rename(columns={"avg_value": f"avg {map_pollutant} ({unit})"}),
            use_container_width=True, hide_index=True,
        )

else:
    monthly = map_load_monthly(map_pollutant)
    if monthly.empty:
        st.warning(f"No map data for {map_pollutant}.")
    else:
        months = sorted(monthly["ym"].unique())
        cmax = float(monthly["avg_value"].quantile(0.95))
        xmax = float(monthly["avg_value"].quantile(0.98)) * 1.05

        st.caption(
            "Drag the slider or press ▶ Play — the map and the ranking below update "
            "together, live. Monthly view can reveal seasonal patterns (winter PM2.5 "
            "heating spikes, summer O₃). Earlier years have fewer stations and 2026 is "
            "partial, so some change reflects coverage, not only pollution."
        )

        def frame_traces(m):
            d = monthly[monthly["ym"] == m]
            map_trace = go.Scattergeo(
                lat=d["lat"], lon=d["lon"],
                text=d["city"] + " (" + d["country"] + "): "
                + d["avg_value"].round(1).astype(str),
                marker=dict(
                    size=(d["avg_value"].clip(upper=cmax) / cmax * 26 + 4),
                    color=d["avg_value"], cmin=0, cmax=cmax, colorscale="RdYlGn_r",
                    colorbar=dict(
                        title=dict(text=f"{map_pollutant.upper()} ({unit})", side="right"),
                        len=0.45, y=0.75, yanchor="middle",
                        thickness=14, x=1.0, outlinewidth=0,
                    ),
                    line=dict(width=0.5, color="rgba(60,60,60,0.5)"),
                ),
                hoverinfo="text", name="",
            )
            top = d.sort_values("avg_value", ascending=False).head(15).iloc[::-1]
            bar_trace = go.Bar(
                x=top["avg_value"], y=top["city"], orientation="h",
                marker=dict(color=top["avg_value"], cmin=0, cmax=cmax,
                            colorscale="RdYlGn_r", showscale=False),
                text=top["avg_value"].round(1), textposition="outside",
                hoverinfo="x+y", xaxis="x2", yaxis="y2", name="",
            )
            return map_trace, bar_trace

        init = months[-1]
        m0, b0 = frame_traces(init)

        fig = go.Figure(
            data=[m0, b0],
            layout=go.Layout(
                geo=map_geo_layout(),
                xaxis2=dict(domain=[0.16, 0.97], anchor="y2", range=[0, xmax],
                            title=dict(text=f"{map_pollutant.upper()} ({unit})",
                                       standoff=8, font=dict(size=11)),
                            side="top", gridcolor="rgba(255,255,255,0.1)",
                            tickfont=dict(size=10)),
                yaxis2=dict(domain=[0.00, 0.258], anchor="x2",
                            automargin=True, tickfont=dict(size=10)),
                height=860,
                margin={"r": 10, "t": 6, "l": 10, "b": 60},
                paper_bgcolor="rgba(0,0,0,0)", font_color="#e0e0e0",
            ),
        )

        frames = []
        for m in months:
            mt, bt = frame_traces(m)
            frames.append(go.Frame(data=[mt, bt], name=m))
        fig.frames = frames

        fig.update_layout(
            updatemenus=[dict(
                type="buttons", showactive=False, x=0.0, y=-0.10, xanchor="left",
                direction="right", pad=dict(t=0, r=6),
                buttons=[
                    dict(label="▶ Play", method="animate",
                         args=[None, {"frame": {"duration": 500, "redraw": True},
                                      "fromcurrent": True,
                                      "transition": {"duration": 250}}]),
                    dict(label="⏸ Pause", method="animate",
                         args=[[None], {"frame": {"duration": 0, "redraw": False},
                                        "mode": "immediate"}]),
                ],
            )],
            sliders=[dict(
                active=len(months) - 1,
                steps=[dict(method="animate", label="",
                            args=[[m], {"frame": {"duration": 0, "redraw": True},
                                        "mode": "immediate"}]) for m in months],
                x=0.16, len=0.81, y=-0.10, xanchor="left",
                currentvalue=dict(prefix="Month: ", font=dict(size=13)),
                pad=dict(t=0),
            )],
        )

        st.plotly_chart(fig, use_container_width=True)