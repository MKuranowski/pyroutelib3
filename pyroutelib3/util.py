# ---------------------------------------------------------------------------
# Loading OSM data and doing routing with it
# ---------------------------------------------------------------------------
# Copyright 2007, Oliver White
# Modifications: Copyright 2017-2021, Mikolaj Kuranowski -
# Based on https://github.com/gaulinmp/pyroutelib2
# ---------------------------------------------------------------------------
# This file is part of pyroutelib3.
#
# pyroutelib3 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pyroutelib3 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pyroutelib3. If not, see <http://www.gnu.org/licenses/>.
# ---------------------------------------------------------------------------
# Changelog:
#  2020-10-23  MK   Refactor code
# ---------------------------------------------------------------------------

"""Contains other useful junk"""

from typing import Callable, List, Tuple
from dataclasses import dataclass, field
import math


Position = Tuple[float, float]
DistFunction = Callable[[Position, Position], float]

SEARCH_LIMIT: int = 1_000_000
TILES_ZOOM: int = 15


def distHaversine(n1: Position, n2: Position) -> float:
    """Calculate distance in km between two nodes using haversine forumla"""
    lat1, lon1 = map(math.radians, n1)
    lat2, lon2 = map(math.radians, n2)
    dlathalf = (lat2 - lat1) * 0.5
    dlonhalf = (lon2 - lon1) * 0.5

    sqrth = math.sqrt(
        (math.sin(dlathalf) ** 2)
        + (math.cos(lat1) * math.cos(lat2) * (math.sin(dlonhalf) ** 2))
    )

    return math.asin(sqrth) * 2 * 6371


def distEuclidian(n1: Position, n2: Position) -> float:
    """Calculates the distance in units between two nodes as an Euclidian 2D distance"""
    dx = n1[0] - n2[0]
    dy = n1[1] - n2[1]
    return dx ** 2 + dy ** 2


@dataclass(eq=True, order=True, frozen=False)
class _AStarQueueItem:
    node: int = field(compare=False)
    routeTo: List[int] = field(compare=False)
    costTo: float = field(compare=False)
    heuristic: float = field(compare=True)
    forceNext: List[int] = field(compare=False, default_factory=list)
