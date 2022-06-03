## base python libraries
import json
from textwrap import dedent

## pip installed libraries
import pandas as pd
import snowflake.connector
import streamlit as st

## repo-local code
from coordinates import Coordinates


## connect to Snowflake
@st.experimental_singleton(show_spinner=False)
def sfconn(**secrets):
    return snowflake.connector.connect(**secrets)


## query Snowflake based on Streamlit input widgets
def get_feature_collection(
    _conn,
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

    data = pd.read_sql(query, _conn)

    st.sidebar.expander("Show generated query").code(dedent(query))

    return json.loads(data["GEOJSON"].iloc[0])


## Get the list of points with CAPITAL = 4 (state capitals)
@st.experimental_singleton(show_spinner=False)
def state_capitals(_conn) -> pd.DataFrame:
    df = pd.read_sql(
        """
        select
            name,
            way as location
        from ZWITCH_DEV_WORKSPACE.TESTSCHEMA.PLANET_OSM_POINT
        where CAPITAL = '4'
        order by name
        """,
        _conn,
    )
    return df


## get all possible values for a given column chosen
## limiting to more popular ones to avoid one-off and mistake values
@st.experimental_memo(show_spinner=False)
def get_fld_values(_conn, tbl, col):

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
        _conn,
    )

    return df[col]
