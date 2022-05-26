import json
import folium
import pandas as pd
import snowflake.connector
import streamlit as st

from streamlit_folium import st_folium
from constants import COLORS
from coordinates import Coordinates

st.set_page_config("OpenStreetMap", layout="wide")

## functions
@st.experimental_singleton
def sfconn():
    return snowflake.connector.connect(**st.secrets["sfdevrel"])


@st.experimental_memo(max_entries=128, show_spinner=False)
def _get_data(query: str) -> pd.DataFrame:
    df = pd.read_sql(
        query,
        conn,
    )
    return df


def get_data(
    coordinates: Coordinates,
    table: str = "POINT",
    column: str = "ACCESS",
    num_rows: int = 1000,
) -> pd.DataFrame:
    x1 = coordinates.x1
    y1 = coordinates.y1
    x2 = coordinates.x2
    y2 = coordinates.y2

    linestring = f"LINESTRING({x1} {y1}, {x2} {y1}, {x2} {y2}, {x1} {y2}, {x1} {y1})"

    polygon = f"st_makepolygon(to_geography('{linestring}'))"

    query = f"""
        select
            *
        from ZWITCH_DEV_WORKSPACE.TESTSCHEMA.PLANET_OSM_{table}
        where NAME is not null
        and {column} is not null
        and st_within(WAY, {polygon})
        limit {num_rows}
        """
    return _get_data(query)


@st.experimental_singleton
def get_flds_in_table(tbl):

    df = pd.read_sql(
        f"show columns in ZWITCH_DEV_WORKSPACE.TESTSCHEMA.planet_osm_{tbl.lower()}",
        conn,
    )
    remove_fields = [
        "OSM_ID",
        "WAY",
        "ADDR_HOUSENAME",
        "ADDR_HOUSENUMBER",
        "ADDR_INTERPOLATION",
        "POPULATION",
        "WIDTH",
        "WOOD",
        "Z_ORDER",
        "TAGS",
        "LAYER",
        "REF",
    ]
    if tbl.lower() == "point":
        remove_fields.extend(
            [
                "AREA",
                "BRIDGE",
                "CUTTING",
                "ELE",
                "EMBANKMENT",
                "HARBOUR",
                "LOCK",
                "POWER_SOURCE",
                "ROUTE",
                "TOLL",
            ]
        )
    elif tbl.lower() == "line":
        remove_fields.extend(
            [
                "AREA",
                "BRAND",
                "BUILDING",
                "DENOMINATION",
                "HARBOUR",
                "OFFICE",
                "POWER_SOURCE",
                "RELIGION",
                "SHOP",
                "TOWER_TYPE",
            ]
        )
    elif tbl.lower() == "polygon":
        remove_fields.extend(
            ["CULVERT", "CUTTING", "LOCK", "POWER_SOURCE", "ROUTE", "WAY_AREA"]
        )

    return df[~df["column_name"].isin(remove_fields)]["column_name"]


@st.experimental_memo(show_spinner=False)
def get_fld_values(tbl, col):

    df = pd.read_sql(
        f"""
        select * from (
        select
        {col},
        count(*) as inst
        from ZWITCH_DEV_WORKSPACE.TESTSCHEMA.planet_osm_{tbl}
        where {col} is not NULL
        group by 1
        order by 2 desc)
        where inst >= 10
        """,
        conn,
    )

    return df[col]


def get_color(feature: dict) -> dict:
    return {
        #'fillColor': '#ffaf00',
        "color": feature["properties"]["color"],
        # "fillColor": feature["properties"]["color"],
        #'weight': 1.5,
        #'dashArray': '5, 5'
    }


def add_data_to_map(geojson_data: dict, map: folium.Map):
    gj = folium.GeoJson(data=geojson_data, style_function=get_color)
    folium.GeoJsonPopup(fields=["NAME", col_selected], labels=True).add_to(gj)
    gj.add_to(m)


def get_data_from_map_data(
    map_data: dict, tbl: str, col_selected: str, num_rows: int, rerun: bool = True
):
    try:
        coordinates = Coordinates.from_dict(map_data["bounds"])
    except TypeError:
        return

    df = get_data(coordinates, column=col_selected, table=tbl, num_rows=num_rows)

    # st.expander("Show data").write(df)

    if not df.equals(pd.DataFrame(st.session_state["points"])):
        st.session_state["points"] = df

    # st.expander("Show session state").write(st.session_state)
    st.session_state["map_data"] = map_data

    if rerun:
        st.experimental_rerun()


def selector_updated():
    tbl = st.session_state["table"]
    col_selected = st.session_state["col_selected"]
    num_rows = st.session_state["num_rows"]
    map_data = st.session_state["map_data"]

    get_data_from_map_data(map_data, tbl, col_selected, num_rows, rerun=False)


def get_center(map_data: dict = None):
    if map_data is None:
        return (39.8, -86.1)

    try:
        y1 = float(map_data["bounds"]["_southWest"]["lat"])
        y2 = float(map_data["bounds"]["_northEast"]["lat"])
        x1 = float(map_data["bounds"]["_southWest"]["lng"])
        x2 = float(map_data["bounds"]["_northEast"]["lng"])

        return ((y2 + y1) / 2, (x2 + x1) / 2)
    except (KeyError, TypeError):
        return (39.8, -86.1)


def get_feature_collection(df: pd.DataFrame, tags: list, col_selected: str) -> dict:
    if df.empty:
        return {}

    unique_vals = df[col_selected].unique()

    color_map = {val: COLORS[idx % len(COLORS)] for idx, val in enumerate(unique_vals)}

    features: list[dict] = []

    for _, point in df.iterrows():
        if tags and point[col_selected] not in tags:
            continue

        color = color_map[point[col_selected]]

        features.append(
            {
                "type": "Feature",
                "geometry": json.loads(point.WAY),
                "properties": {
                    "color": color,
                    "NAME": point["NAME"],
                    col_selected: point[col_selected],
                },
            }
        )

    feature_collection = {
        "type": "FeatureCollection",
        "features": features,
        "properties": {"color": "purple"},
    }

    # st.expander("Show features").json(feature_collection)

    return feature_collection


if "points" not in st.session_state:
    st.session_state["points"] = pd.DataFrame()


## streamlit app code below
"### OpenStreetMap - North America"

conn = sfconn()

zoom = st.session_state.get("map_data", {"zoom": 13})["zoom"]


location = get_center(st.session_state.get("map_data"))

m = folium.Map(location=location, zoom_start=zoom)


tbl = st.sidebar.selectbox(
    "1. Choose a geometry type",
    ["Point", "Line", "Polygon"],
    key="table",
    on_change=selector_updated,
)

flds = get_flds_in_table(tbl)
col_selected = st.sidebar.selectbox(
    "2. Choose a column", flds, key="col_selected", on_change=selector_updated
)

tgs = get_fld_values(tbl, col_selected)
tags = st.sidebar.multiselect(
    "3. Choose tags to visualize",
    tgs,
    help="Tags listed by frequency high-to-low",
    on_change=selector_updated,
)

num_rows = st.sidebar.select_slider(
    "How many rows?",
    [10, 100, 1000, 10_000],
    value=1000,
    key="num_rows",
    on_change=selector_updated,
)


feature_collection = get_feature_collection(
    st.session_state["points"], tags, col_selected
)

if feature_collection:
    add_data_to_map(feature_collection, m)

map_data = st_folium(m, width=1000, key="hard_coded_key")

if (
    "map_data" not in st.session_state
    or st.session_state["map_data"]["bounds"]["_southWest"]["lat"] is None
):
    st.session_state["map_data"] = map_data

# st.expander("Show map data").json(map_data)

if st.session_state["points"].empty:
    get_data_from_map_data(map_data, tbl, col_selected, num_rows)


if st.sidebar.button("Update data"):
    get_data_from_map_data(map_data, tbl, col_selected, num_rows)

# st.expander("Show session state").write(st.session_state)
