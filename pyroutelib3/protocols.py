from typing import Callable, Tuple

Position = Tuple[float, float]
"""Position describes the physical location of a node.
For on-Earth positions, this should be WGS84 degrees, first latitude, then longitude.
"""

DistanceFunction = Callable[[Position, Position], float]
"""DistanceFunction describes a callable for determining the shortest
crow-flies distance between two points.
"""
