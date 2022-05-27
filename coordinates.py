from typing import NamedTuple
from constants import ROUND_TO


class Coordinates(NamedTuple):
    x1: float
    y1: float
    x2: float
    y2: float

    @classmethod
    def from_dict(cls, coordinates: dict) -> "Coordinates":
        shift = 10 ** (-ROUND_TO)
        x1 = round(float(coordinates["_southWest"]["lng"]) - shift, ROUND_TO)
        y1 = round(float(coordinates["_southWest"]["lat"]) - shift, ROUND_TO)
        x2 = round(float(coordinates["_northEast"]["lng"]) + shift, ROUND_TO)
        y2 = round(float(coordinates["_northEast"]["lat"]) + shift, ROUND_TO)

        return cls(x1, y1, x2, y2)

    @classmethod
    def get_center(cls, map_data: dict = None):
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
