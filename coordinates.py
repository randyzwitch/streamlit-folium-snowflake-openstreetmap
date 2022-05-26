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
