# © Copyright 2024 Mikołaj Kuranowski
# SPDX-License-Identifier: GPL-3.0-or-later

from dataclasses import dataclass
from typing import Generic, Iterable, List, Optional, Tuple

from typing_extensions import Self

from .distance import haversine_earth_distance
from .protocols import DistanceFunction, Position, WithPositionT


@dataclass(frozen=True)
class KDTree(Generic[WithPositionT]):
    """KDTree implements the `k-d tree data structure <https://en.wikipedia.org/wiki/K-d_tree>`_,
    which can be used to speed up nearest-neighbor search for large datasets. Practice shows
    that :py:meth:`osm.Graph.find_nearest_neighbor` takes significantly more time than
    :py:func:`find_route` when generating multiple routes with ``pyroutelib3``. A k-d tree
    can help with that, trading memory usage for CPU time.

    This implementation assumes euclidean geometry, even though the default distance function
    used is :py:func:`haversine_earth_distance`. This results in undefined behavior when
    points are close to the ante meridian (180°/-180° longitude) or poles (90°/-90° latitude),
    or when the data spans multiple continents.
    """

    pivot: WithPositionT
    left: Optional["KDTree[WithPositionT]"] = None
    right: Optional["KDTree[WithPositionT]"] = None

    def _find_nearest_neighbor_impl(
        self,
        root: Position,
        distance: DistanceFunction = haversine_earth_distance,
        axis: int = 0,
    ) -> Tuple[WithPositionT, float]:
        # Start by assuming that pivot is the closest
        best = self.pivot
        best_distance = distance(root, self.pivot.position)

        # Select which branch to recurse into first
        first_left = root[0] < best.position[0] if axis == 0 else root[1] < best.position[1]
        first = self.left if first_left else self.right
        second = self.right if first_left else self.left

        # Recurse into the first branch
        if first:
            alt, alt_distance = first._find_nearest_neighbor_impl(root, distance, axis ^ 1)
            if alt_distance < best_distance:
                best = alt
                best_distance = alt_distance

        # (Optionally) recurse into the second branch
        if second:
            # A closer node is possible in the second branch if and only if
            # the splitting axis (as determined by pivot[axis]) is closer than
            # the current best candidate
            pt_on_axis = (
                (self.pivot.position[0], root[1])
                if axis == 0
                else (root[0], self.pivot.position[1])
            )
            dist_to_axis = distance(root, pt_on_axis)

            if dist_to_axis < best_distance:
                alt, alt_distance = second._find_nearest_neighbor_impl(root, distance, axis ^ 1)
                if alt_distance < best_distance:
                    best = alt
                    best_distance = alt_distance

        return best, best_distance

    def find_nearest_neighbor(
        self,
        root: Position,
        distance: DistanceFunction = haversine_earth_distance,
    ) -> WithPositionT:
        """Find the closest node to ``root``, as determined by the provided distance function."""
        return self._find_nearest_neighbor_impl(root, distance, 0)[0]

    @classmethod
    def _build_impl(cls, points: List[WithPositionT], axis: int = 0) -> Optional[Self]:
        if not points:
            return None
        elif len(points) == 1:
            return cls(points[0])
        else:
            points.sort(key=lambda pt: pt.position[axis])
            median = len(points) // 2
            return cls(
                points[median],
                cls._build_impl(points[:median], axis ^ 1),
                cls._build_impl(points[median + 1 :], axis ^ 1),
            )

    @classmethod
    def build(cls, points: Iterable[WithPositionT]) -> Optional[Self]:
        """Creates a new K-D tree with all of the provided objects with a :py:obj:`Position`.

        Note that the type-complaint usage of class methods on generic types requires
        explicitly providing the type argument, e.g.::

            tree = KDTree[Node].build(nodes)
        """
        return cls._build_impl(list(points), 0)
