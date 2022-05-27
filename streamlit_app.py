import json
from typing import Optional

import folium
import pandas as pd
import snowflake.connector
import streamlit as st
from streamlit_folium import st_folium

from constants import COLORS, COLUMN_VALS
from coordinates import Coordinates

st.set_page_config("OpenStreetMap", layout="wide", page_icon=":world-map:")

## functions
@st.experimental_singleton
def sfconn():
    return snowflake.connector.connect(**st.secrets["sfdevrel"])


def get_data(
    coordinates: Coordinates,
    table: str = "POINT",
    tags: list = None,
    column: str = "ACCESS",
    num_rows: int = 1000,
) -> pd.DataFrame:
    x1 = coordinates.x1
    y1 = coordinates.y1
    x2 = coordinates.x2
    y2 = coordinates.y2

    linestring = f"LINESTRING({x1} {y1}, {x2} {y1}, {x2} {y2}, {x1} {y2}, {x1} {y1})"

    polygon = f"st_makepolygon(to_geography('{linestring}'))"

    if tags is not None:
        tags = [tag.replace("'", "''") for tag in tags]
        tag_string = ",".join(f"'{tag}'" for tag in tags)

    # In order to store and keep properties around, manually construct json, rather than
    # using st_collect
    query = f"""
        with points as (
            select
                NAME,
                {column},
                object_construct(
                    'type', 'Feature',
                    'geometry', ST_ASGEOJSON(WAY),
                    'properties',
                        object_construct(
                            'NAME', NAME,
                            '{column}', {column}
                        )
                ) as geojson_obj
            from ZWITCH_DEV_WORKSPACE.TESTSCHEMA.PLANET_OSM_{table}
            where NAME is not null
            and {column} is not null
            and st_within(WAY, {polygon})
            {f"and {column} in ({tag_string})" if tags else ""}
            limit {num_rows}
        )

        select
            object_construct('type', 'FeatureCollection', 'features', array_agg(geojson_obj)) as geojson
        from points;
        """

    print(query)
    # st.expander("Show query").code(query)

    data = pd.read_sql(query, conn)
    # st.expander("Show data").write(data)
    return data


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


def add_data_to_map(geojson_data: str, map: folium.Map, table: str, column: str):
    geojson = json.loads(geojson_data)

    unique_vals = set(
        [feature["properties"][col_selected] for feature in geojson["features"]]
    )

    color_map = {val: COLORS[idx % len(COLORS)] for idx, val in enumerate(unique_vals)}

    for feature in geojson["features"]:
        feature["properties"]["color"] = color_map[feature["properties"][column]]

    def get_color(feature: dict) -> dict:
        styles = {
            "color": feature["properties"]["color"],
            "fillColor": feature["properties"]["color"],
        }
        if table == "Point":
            styles["weight"] = 10

        return styles

    gj = folium.GeoJson(data=geojson, style_function=get_color, marker=folium.Circle())
    folium.GeoJsonPopup(fields=["NAME", column], labels=True).add_to(gj)
    gj.add_to(map)


def get_data_from_map_data(
    map_data: dict,
    tbl: str,
    col_selected: str,
    num_rows: int,
    tags: list = None,
    rerun: bool = True,
):
    try:
        coordinates = Coordinates.from_dict(map_data["bounds"])
    except TypeError:
        return

    df = get_data(
        coordinates, column=col_selected, table=tbl, num_rows=num_rows, tags=tags
    )

    if not df.equals(pd.DataFrame(st.session_state["points"])):
        st.session_state["points"] = df

    # st.expander("Show session state").write(st.session_state)
    st.session_state["map_data"] = map_data

    if rerun:
        st.experimental_rerun()


def selector_updated():
    tbl = st.session_state["table"]
    col_selected = st.session_state["col_selected"]
    tags = st.session_state["tags"]
    num_rows = st.session_state["num_rows"]
    map_data = st.session_state["map_data"]

    get_data_from_map_data(
        map_data, tbl, col_selected, num_rows=num_rows, tags=tags, rerun=False
    )


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


def get_feature_collection(df: pd.DataFrame) -> Optional[str]:
    if df.empty:
        return None

    geojson_str = df["GEOJSON"].iloc[0]

    return geojson_str


if "points" not in st.session_state:
    st.session_state["points"] = pd.DataFrame()


## streamlit app code below
"### 🗺️ OpenStreetMap - North America"

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

col_selected = st.sidebar.selectbox(
    "2. Choose a column",
    COLUMN_VALS[tbl.lower()],
    key="col_selected",
    on_change=selector_updated,
)

tgs = get_fld_values(tbl, col_selected)
tags = st.sidebar.multiselect(
    "3. Choose tags to visualize",
    tgs,
    key="tags",
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


feature_collection = get_feature_collection(st.session_state["points"])

if feature_collection:
    add_data_to_map(feature_collection, m, table=tbl, column=col_selected)

map_data = st_folium(m, width=1000, key="hard_coded_key")

if (
    "map_data" not in st.session_state
    or st.session_state["map_data"]["bounds"]["_southWest"]["lat"] is None
):
    st.session_state["map_data"] = map_data

# st.expander("Show map data").json(map_data)

if st.sidebar.button("Update data") or st.session_state["points"].empty:
    get_data_from_map_data(map_data, tbl, col_selected, tags=tags, num_rows=num_rows)

# st.expander("Show session state").write(st.session_state)
