## base python libraries
from typing import Optional
import json

## pip installed libraries
import folium
import streamlit as st

## repo-local code
from constants import COLORS
from sfdb import state_capitals

## from Snowflake query results, add data to Folium map
def add_data_to_map(
    col_selected, geojson_data: dict, map: folium.Map, table: str, column: str
):
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

    if len(geojson_data["features"]) == 0:
        return

    gj = folium.GeoJson(
        data=geojson_data, style_function=get_color, marker=folium.Circle()
    )
    folium.GeoJsonPopup(fields=["NAME", column], labels=True).add_to(gj)
    gj.add_to(map)


def get_order(key) -> int:
    # Don't ever sort by keys with None as their value
    if st.session_state[key] is None:
        return -1

    return len(str(key))


def get_capital_data(conn, capital: str) -> Optional[dict]:
    if capital == "--NONE--":
        return None

    df = state_capitals(conn)
    location = json.loads(df[df["NAME"] == capital]["LOCATION"].iloc[0])["coordinates"]
    center = {
        "lat": location[1],
        "lng": location[0],
    }
    zoom = 11

    return {
        "center": center,
        "zoom": zoom,
    }
