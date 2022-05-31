import json
from typing import Optional

import folium
import pandas as pd
import snowflake.connector
import streamlit as st
from streamlit_folium import st_folium

from constants import COLORS, COLUMN_VALS
from coordinates import Coordinates

## Set Streamlit app to wide, change title
st.set_page_config("OpenStreetMap", layout="wide", page_icon=":world-map:")

#### functions ####
## connect to Snowflake
@st.experimental_singleton
def sfconn():
    return snowflake.connector.connect(**st.secrets["sfdevrel"])


## get all possible values for a given column chosen
## limiting to more popular ones to avoid one-off and mistake values
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


## query Snowflake based on Streamlit input widgets
def get_feature_collection(
    coordinates: Coordinates,
    table: str = "POINT",
    tags: list = None,
    column: str = "ACCESS",
    num_rows: int = 1000,
) -> dict:
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

    data = pd.read_sql(query, conn)

    features = json.loads(data["GEOJSON"].iloc[0])
    return features


## from Snowflake query results, add data to Folium map
def add_data_to_map(geojson_data: dict, map: folium.Map, table: str, column: str):
    unique_vals = set(
        [feature["properties"][col_selected] for feature in geojson_data["features"]]
    )

    color_map = {val: COLORS[idx % len(COLORS)] for idx, val in enumerate(unique_vals)}

    for feature in geojson_data["features"]:
        feature["properties"]["color"] = color_map[feature["properties"][column]]

    def get_color(feature: dict) -> dict:
        styles = {
            "color": feature["properties"]["color"],
            "fillColor": feature["properties"]["color"],
        }
        if table == "Point":
            styles["weight"] = 10

        return styles

    gj = folium.GeoJson(
        data=geojson_data, style_function=get_color, marker=folium.Circle()
    )
    folium.GeoJsonPopup(fields=["NAME", column], labels=True).add_to(gj)
    gj.add_to(map)


#### streamlit app code below ####

## connect to snowflake
conn = sfconn()

# put sidebar widgets up as high as possible in code to avoid flickering
tbl = st.sidebar.selectbox(
    "1. Choose a geometry type",
    ["Point", "Line", "Polygon"],
    key="table",
)

col_selected = st.sidebar.selectbox(
    "2. Choose a column",
    COLUMN_VALS[tbl.lower()],
    key="col_selected",
)

tgs = get_fld_values(tbl, col_selected)
tags = st.sidebar.multiselect(
    "3. Choose tags to visualize",
    tgs,
    key="tags",
    help="Tags listed by frequency high-to-low",
)

num_rows = st.sidebar.select_slider(
    "Maximum number of rows?",
    [100, 1000, 10_000, 100_000],
    value=1000,
    key="num_rows",
)

## figure out key of automatically written state
## this is slightly hacky
autostate = sorted(list(st.session_state.keys()), key=len)[-1]

## initialize starting value of zoom if it doesn't exist
## otherwise, get it from session_state
zoom = st.session_state.get(autostate, {"zoom": 4})["zoom"]

## initialize starting value of center if it doesn't exist
## otherwise, get it from session_state
center = st.session_state.get(autostate, {"center": {"lat": 37.97, "lng": -96.12}})[
    "center"
]

"### 🗺️ OpenStreetMap - North America"

## Initialize Folium
m = folium.Map(location=(center["lat"], center["lng"]), zoom_start=zoom)

## defines initial case, prior to map being rendered
if autostate in st.session_state and len(autostate) == 64:
    coordinates = Coordinates.from_dict(st.session_state[autostate]["bounds"])
else:
    coordinates = Coordinates.from_dict(
        {
            "_southWest": {"lat": 10.290060240659766, "lng": -140.07046669721603},
            "_northEast": {"lat": 58.15737472780594, "lng": -52.17984169721604},
        }
    )

## get data from Snowflake
st.session_state["features"] = get_feature_collection(
    coordinates, column=col_selected, table=tbl, num_rows=num_rows, tags=tags
)

add_data_to_map(st.session_state["features"], m, table=tbl, column=col_selected)


## display map on app
map_data = st_folium(m, width=1000)
