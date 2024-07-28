# © Copyright 2024 Mikołaj Kuranowski
# SPDX-License-Identifier: GPL-3.0-or-later

"""Simple routing over OpenStreetMap data"""

__title__ = "pyroutelib3"
__description__ = "Simple routing over OpenStreetMap data"
__url__ = "https://github.com/MKuranowski/pyroutelib3"
__author__ = "Mikołaj Kuranowski"
__copyright__ = "© Copyright 2024 Mikołaj Kuranowski"
__license__ = "GPL-3.0-or-later"
__version__ = "2.0.0"
__email__ = "mkuranowski+pypackages@gmail.com"

from . import nx, osm, protocols
from .distance import euclidean_distance, haversine_earth_distance, taxicab_distance
from .kd import KDTree
from .router import (
    DEFAULT_STEP_LIMIT,
    StepLimitExceeded,
    find_route,
    find_route_without_turn_around,
)
from .simple_graph import SimpleExternalNode, SimpleGraph, SimpleNode

__all__ = [
    "DEFAULT_STEP_LIMIT",
    "euclidean_distance",
    "find_route_without_turn_around",
    "find_route",
    "haversine_earth_distance",
    "KDTree",
    "nx",
    "osm",
    "protocols",
    "SimpleExternalNode",
    "SimpleGraph",
    "SimpleNode",
    "StepLimitExceeded",
    "taxicab_distance",
]
