# © Copyright 2024 Mikołaj Kuranowski
# SPDX-License-Identifier: GPL-3.0-or-later

from dataclasses import dataclass, field
from typing import Dict, Iterable, Tuple

from typing_extensions import Self

from .protocols import GraphLike, NodeLikeT_co, Position


@dataclass
class SimpleNode:
    """SimpleNode provides a base class and a simple implementation of
    the :py:class:`NodeLike` protocol."""

    id: int
    position: Position


@dataclass
class SimpleExternalNode:
    """SimpleExternalNode provides a base class and a simple implementation of
    the :py:class:`ExternalNodeLike` protocol."""

    id: int
    position: Position
    external_id: int

    @classmethod
    def with_same_external_id(cls, id: int, position: Position) -> Self:
        """with_same_external_id instantiates a SimpleExternalNode with
        :py:attr:`external_id` set to the same value as :py:attr:`id`.
        """
        return cls(id=id, position=position, external_id=id)


@dataclass
class SimpleGraph(GraphLike[NodeLikeT_co]):
    """SimpleGraph provides a base class and a simple implementation of
    the :py:class:`GraphLike` protocol over two dictionaries: one holding nodes,
    and another holding edge costs."""

    nodes: Dict[int, NodeLikeT_co] = field(default_factory=dict)
    edges: Dict[int, Dict[int, float]] = field(default_factory=dict)

    def get_node(self, id: int) -> NodeLikeT_co:
        return self.nodes[id]

    def get_edges(self, id: int) -> Iterable[Tuple[int, float]]:
        return self.edges.get(id, {}).items()
