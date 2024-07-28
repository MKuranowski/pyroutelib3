# © Copyright 2024 Mikołaj Kuranowski
# SPDX-License-Identifier: GPL-3.0-or-later

from dataclasses import dataclass
from operator import itemgetter
from typing import Any, Callable, Iterable, Mapping, Optional, Protocol, Tuple

from .protocols import GraphLike as OurGraphLike
from .protocols import Position

"""The ``nx`` module contains helpers for adapting
`networkx graphs <https://networkx.org/documentation/stable/reference/introduction.html#graphs>`_
into the interfaces expected by pyroutelib3.

To adapt a graph, use :py:class:`ExternalGraphAdaptor` or :py:class:`GraphAdaptor` with
the appropriate attribute getters. The networkx graph must use integers as nodes.
"""

Data = Mapping[str, Any]
"""Data represents arbitrary networkx data held in a dictionary."""


class NodeViewLike(Protocol):
    """NodeViewLike describes the minimal set of features required from
    `nx.Graph.nodes <https://networkx.org/documentation/stable/reference/classes/generated/networkx.Graph.nodes.html#networkx.Graph.nodes>`_
    to adapt the nodes of a networkx graph.
    """

    def __getitem__(self, __o: int) -> Data: ...


class AtlasViewLike(Protocol):
    """AtlasViewLike describes the minimal set of features required from the return value of
    calling ``get`` on
    `nx.Graph.adj <https://networkx.org/documentation/stable/reference/classes/generated/networkx.Graph.adj.html#networkx.Graph.adj>`_
    to adapt the edges of a networkx graph.
    """

    def items(self) -> Iterable[Tuple[int, Data]]: ...


class AdjacencyViewLike(Protocol):
    """AdjacencyViewLike describes the minimal set of features required from
    `nx.Graph.adj <https://networkx.org/documentation/stable/reference/classes/generated/networkx.Graph.adj.html#networkx.Graph.adj>`_
    to adapt the edges of a networkx graph.
    """

    def get(self, __o: int) -> Optional[AtlasViewLike]: ...


class GraphLike(Protocol):
    """GraphLike describes the minimal set of features required from a
    `nx.Graph <https://networkx.org/documentation/stable/reference/classes/graph.html>`_
    to adapt it into the :py:class:`pyroutelib3.GraphLike` protocol.
    """

    @property
    def nodes(self) -> NodeViewLike: ...

    @property
    def adj(self) -> AdjacencyViewLike: ...


@dataclass
class NodeAdaptor:
    """NodeAdaptor adapts a networkx node into the :py:class:`pyroutelib3.NodeLike`
    protocol.
    """

    id: int
    data: Data

    position_getter: Callable[[Data], Position] = itemgetter("lat", "lon")
    """position_getter is used to extract the :py:obj:`Position` of a node
    from its networkx data dictionary. Defaults to returning ``(data["lat"], data["lon"])``.

    Usage of `operator.itemgetter <https://docs.python.org/3/library/operator.html#operator.itemgetter>`_
    is highly recommended.
    """

    @property
    def position(self) -> Position:
        return self.position_getter(self.data)


@dataclass
class GraphAdaptor(OurGraphLike[NodeAdaptor]):
    """GraphAdaptor adapts a networkx graph into the :py:class:`pyroutelib3.GraphLike`
    protocol, with plain nodes **without** external ids.
    """

    g: GraphLike

    edge_cost_getter: Callable[[Data], float] = itemgetter("weight")
    """node_position_getter is used to extract the cost/weight of an edge
    from its networkx data dictionary. Defaults to returning ``data["weight"]``.

    Usage of `operator.itemgetter <https://docs.python.org/3/library/operator.html#operator.itemgetter>`_
    is highly recommended.
    """

    node_position_getter: Callable[[Data], Position] = itemgetter("lat", "lon")
    """node_position_getter is used to extract the :py:obj:`Position` of a node
    from its networkx data dictionary. Defaults to returning ``(data["lat"], data["lon"])``.

    Usage of `operator.itemgetter <https://docs.python.org/3/library/operator.html#operator.itemgetter>`_
    is highly recommended.
    """

    def get_node(self, id: int) -> NodeAdaptor:
        return NodeAdaptor(
            id=id,
            data=self.g.nodes[id],
            position_getter=self.node_position_getter,
        )

    def get_edges(self, id: int) -> Iterable[Tuple[int, float]]:
        if atlas := self.g.adj.get(id):
            for to_id, edge_data in atlas.items():
                yield to_id, self.edge_cost_getter(edge_data)


@dataclass
class ExternalNodeAdaptor(NodeAdaptor):
    """NodeAdaptor adapts a networkx node into the :py:class:`pyroutelib3.ExternalNodeLike`
    protocol.
    """

    external_id_getter: Callable[[Data], int] = itemgetter("external_id")
    """external_id_getter is used to extract the external ID of a node from its networkx data
    dictionary. Defaults to returning ``data["external_id"]``.

    Usage of `operator.itemgetter <https://docs.python.org/3/library/operator.html#operator.itemgetter>`_
    is highly recommended.
    """

    @property
    def external_id(self) -> int:
        return self.external_id_getter(self.data)


@dataclass
class ExternalGraphAdaptor(GraphAdaptor, OurGraphLike[ExternalNodeAdaptor]):
    """ExternalGraphAdaptor adapts a networkx graph into the :py:class:`pyroutelib3.GraphLike`
    protocol, with nodes containing external IDs.
    """

    node_external_id_getter: Callable[[Data], int] = itemgetter("external_id")
    """node_external_id_getter is used to extract the external ID of a node from its networkx data
    dictionary. Defaults to returning ``data["external_id"]``.

    Usage of `operator.itemgetter <https://docs.python.org/3/library/operator.html#operator.itemgetter>`_
    is highly recommended.
    """

    def get_node(self, id: int) -> ExternalNodeAdaptor:
        return ExternalNodeAdaptor(
            id=id,
            data=self.g.nodes[id],
            position_getter=self.node_position_getter,
            external_id_getter=self.node_external_id_getter,
        )
