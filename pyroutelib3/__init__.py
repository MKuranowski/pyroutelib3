# © Copyright 2024 Mikołaj Kuranowski
# SPDX-License-Identifier: GPL-3.0-or-later

"""Simple routing over OSM data"""

__title__ = "pyroutelib3"
__description__ = "Simple routing over OSM data"
__url__ = "https://github.com/MKuranowski/pyroutelib3"
__author__ = "Mikołaj Kuranowski"
__copyright__ = "© Copyright 2024 Mikołaj Kuranowski"
__license__ = "GPL-3.0-or-later"
__version__ = "2.0.0-pre1"
__email__ = "mkuranowski+pypackages@gmail.com"

from . import osm, protocols
from .distance import euclidean_distance, haversine_earth_distance, taxicab_distance
from .router import find_route, find_route_without_turn_around

__all__ = [
    "euclidean_distance",
    "find_route_without_turn_around",
    "find_route",
    "haversine_earth_distance",
    "osm",
    "protocols",
    "taxicab_distance",
]
