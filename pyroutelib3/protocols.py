# © Copyright 2024 Mikołaj Kuranowski
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Callable, Iterable, Protocol, Tuple, TypeVar

Position = Tuple[float, float]
"""Position describes the physical location of a node.
For on-Earth positions, this should be WGS84 degrees, first latitude, then longitude.
"""

DistanceFunction = Callable[[Position, Position], float]
"""DistanceFunction describes a callable for determining the shortest
crow-flies distance between two points.
"""


class WithPosition(Protocol):
    """WithPosition describes any object with a ``position`` property of :py:obj:`Position` type."""

    @property
    def position(self) -> Position: ...


WithPositionT = TypeVar("WithPositionT", bound=WithPosition)


class NodeLike(WithPosition, Protocol):
    """NodeLike describes the protocol of a *node* in a *graph*."""

    @property
    def id(self) -> int:
        """id property must uniquely identify this *node* in its *graph*."""
        ...


class ExternalNodeLike(NodeLike, Protocol):
    """ExternalNodeLike is an extension of the :py:class:`NodeLike` protocol
    for describing nodes coming from external datasets.
    """

    @property
    def external_id(self) -> int:
        """external_id property should return the ID used to lookup this node
        in an external dataset, for example an OpenStreetMap node ID.

        external_id may be reused by multiple nodes, for example processing
        OpenStreetMap turn restrictions may create multiple graph nodes
        corresponding to a single OpenStreetMap node.

        Used by :py:func:`find_route_without_turn_around` to prevent
        turn restriction circumvention by forbidding A-B-A paths.
        """
        ...


NodeLikeT_co = TypeVar("NodeLikeT_co", bound=NodeLike, covariant=True)


class GraphLike(Protocol[NodeLikeT_co]):
    """GraphLike describes the protocol of a *graph*."""

    def get_node(self, id: int) -> NodeLikeT_co:
        """get_node must return a :py:class:`NodeLike` of a *node* by the provided ID.
        If such a node doesn't exist, must raise KeyError.
        """
        ...

    def get_edges(self, id: int) -> Iterable[Tuple[int, float]]:
        """get_edges must return all edges outgoing from a *node* with the provided ID.
        The edges are a pair of (node_id, cost). All returned neighbor nodes must
        exist in the graph.

        If there are no outgoing edges from the provided node, must return an empty iterable.
        If a node with the given ID, may return an empty iterable, or raise KeyError.
        """
        ...
