## base python libraries
from typing import cast

## pip installed libraries
import folium
import streamlit as st
from streamlit_folium import st_folium

## repo-local code
from constants import COLUMN_VALS
from coordinates import Coordinates
from sfdb import sfconn, get_feature_collection, state_capitals, get_fld_values
from utils import add_data_to_map, get_order, get_capital_data

## Set Streamlit app to wide, change title
st.set_page_config("OpenStreetMap", layout="wide", page_icon=":world-map:")


def clear_state():
    del st.session_state[autostate]


## connect to snowflake
conn = sfconn(**st.secrets["sfdevrel"])

## put sidebar widgets up as high as possible in code to avoid flickering
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

tgs = get_fld_values(conn, tbl, col_selected)
tags = st.sidebar.multiselect(
    "3. Choose tags to visualize",
    tgs,
    key="tags",
    help="Tags listed by frequency high-to-low",
)

capitals = ["--NONE--"] + list(state_capitals(conn)["NAME"].values)

capital = st.sidebar.selectbox(
    "(Optional) Zoom map to capital?",
    options=capitals,
    key="capital",
    on_change=clear_state,
)

## visual divider between less important input
st.sidebar.write("---")
num_rows = st.sidebar.select_slider(
    "Maximum number of rows",
    [100, 1000, 10_000, 100_000],
    value=1000,
    key="num_rows",
)

## figure out key of automatically written state
## this is slightly hacky
autostate = cast(str, sorted(st.session_state.keys(), key=get_order)[-1])

capital_data = get_capital_data(conn, capital)

## initialize starting value of zoom if it doesn't exist
## otherwise, get it from session_state
try:
    zoom = st.session_state[autostate]["zoom"]
except (TypeError, KeyError):
    if capital_data is None:
        zoom = 4
    else:
        zoom = capital_data["zoom"]

## initialize starting value of center if it doesn't exist
## otherwise, get it from session_state
try:
    center = st.session_state[autostate]["center"]
except (TypeError, KeyError):
    if capital_data is None:
        center = {"lat": 37.97, "lng": -96.12}
    else:
        center = capital_data["center"]

"### 🗺️ OpenStreetMap - North America"

"---"
## Initialize Folium
m = folium.Map(location=(center["lat"], center["lng"]), zoom_start=zoom)

## defines initial case, prior to map being rendered
try:
    coordinates = Coordinates.from_dict(st.session_state[autostate]["bounds"])
except TypeError:
    coordinates = Coordinates.from_dict(
        {
            "_southWest": {"lat": 10.31491928581316, "lng": -140.09765625000003},
            "_northEast": {"lat": 58.17070248348609, "lng": -52.20703125000001},
        }
    )

## get data from Snowflake
st.session_state["features"] = get_feature_collection(
    conn, coordinates, column=col_selected, table=tbl, num_rows=num_rows, tags=tags
)

add_data_to_map(
    col_selected, st.session_state["features"], m, table=tbl, column=col_selected
)

## display map on app
map_data = st_folium(m, width=1000)
