# © Copyright 2024 Mikołaj Kuranowski
# SPDX-License-Identifier: GPL-3.0-or-later

import gc
import sys
from dataclasses import dataclass, field
from logging import getLogger
from math import isfinite
from typing import IO, Dict, Iterable, List, Optional, Set, Tuple

from typing_extensions import Self

from ..distance import haversine_earth_distance
from ..protocols import Position
from ..simple_graph import SimpleExternalNode, SimpleGraph
from . import reader
from .profile import Profile, TurnRestriction

osm_logger = getLogger("pyroutelib3.osm")

_MAX_NODE_ID = 0x0008_0000_0000_0000
"""_MAX_NODE_ID is the maximum permitted ID of a node coming from OpenStreetMap.
Values of _MAX_NODE_ID and above are used for phantom nodes created by turn restrictions.
"""

if sys.version_info < (3, 10):
    from typing import TypeVar, cast

    _T = TypeVar("_T")

    def pairwise(iterable: Iterable[_T]) -> Iterable[Tuple[_T, _T]]:
        it = iter(iterable)
        a = next(it, None)
        for b in it:
            yield cast(_T, a), b
            a = b

else:
    from itertools import pairwise


class GraphNode(SimpleExternalNode):
    """GraphNode is a *node* in a :py:class:`Graph`."""

    @property
    def osm_id(self) -> int:
        return self.external_id


class Graph(SimpleGraph[GraphNode]):
    """Graph implements :py:class:`GraphLike` over OpenStreetMap data."""

    profile: Profile

    _phantom_node_id_counter: int
    """_phantom_node_id_counter is a counter used for generating IDs for phantom nodes
    created when processing turn restriction. Used by :py:class:`_GraphBuilder` and
    :py:class:`_GraphChange`.
    """

    def __init__(self, profile: Profile) -> None:
        super().__init__()
        self.profile = profile
        self._phantom_node_id_counter = _MAX_NODE_ID

    def find_nearest_node(self, position: Position) -> GraphNode:
        """find_nearest_node finds the closest node to the provided :py:obj:`Position`.
        Phantom nodes ``nd.id != nd.osm_id`` created by turn restrictions are not considered.

        This function iterates over every contained :py:class:`GraphNode`, and can be
        very slow for big graphs. Use a helper data structure (like a K-D tree) if this function
        becomes a performance bottleneck.
        """

        return min(
            (nd for nd in self.nodes.values() if nd.id == nd.osm_id),
            key=lambda nd: haversine_earth_distance(position, nd.position),
        )

    def add_features(self, features: Iterable[reader.Feature]) -> None:
        """add_features adds OpenStreetMap data to the graph.

        While it is permitted to call this function multiple times on the same graph,
        each call must be made with a complete, self-contained dataset. That is,
        ways may only refer to nodes from the ``features`` iterable, and relations as well may only
        refer to ways and nodes from the ``features`` iterable.

        If called on a non-empty graph the data is merged:

        * for duplicate nodes - the already-existing data takes precedence,
        * for duplicate edges between two nodes - the incoming data takes precedence,
        * for duplicate turn restrictions - the incoming restriction is processed,
            which should be a no-op, as the restriction was already applied.


        Due to linear processing of the provided iterable, a feature may only refer to features
        that were defined beforehand. The easiest way to satisfy this condition is to ensure
        that features are listed grouped by type, first nodes, followed by ways,
        followed by relations. Most OSM XML files exported by other tools follow this ordering.

        Any issues with incoming OSM data are reported as warnings through the
        ``pyroutelib3.osm`` logger.
        """
        _GraphBuilder.add_features_to(self, features)

    @classmethod
    def from_features(cls, profile: Profile, features: Iterable[reader.Feature]) -> Self:
        """Creates a :py:class:`Graph` based on the provided ``profile`` and ``features``."""
        g = cls(profile)
        g.add_features(features)
        return g

    @classmethod
    def from_file(
        cls,
        profile: Profile,
        buf: IO[bytes],
        format: reader.FILE_FORMAT_T = reader.DEFAULT_FILE_FORMAT,
        chunk_size: int = reader.DEFAULT_CHUNK_SIZE,
    ) -> Self:
        """Creates a :py:class:`Graph` based on the provided :py:class:`Profile` and features
        from the provided possibly-compressed
        `OSM XML <https://wiki.openstreetmap.org/wiki/OSM_XML>`_ or a
        `OSM PBF <https://wiki.openstreetmap.org/wiki/PBF_Format>`_ file.

        ``format`` and ``chunk_size`` are passed through to :py:func:`osm.reader.read_features`.
        """
        return cls.from_features(profile, reader.read_features(buf, format, chunk_size))


@dataclass
class _GraphBuilder:
    """_GraphBuilder is responsible for adding a self-contained batch of features to
    a :py:class:`Graph`.

    See the restrictions on :py:meth:`Graph.add_features` for underlying data assumptions.

    Usage::
        _GraphBuilder.add_features_to(graph, features)
    """

    g: Graph

    unused_nodes: Set[int] = field(default_factory=set)
    """unused_nodes is a set of nodes added to the graph which weren't used
    by any way - and should be removed once all features have been processed.
    """

    way_nodes: Dict[int, List[int]] = field(default_factory=dict)
    """way_nodes maps way_ids to its sequence of nodes, required for relation processing."""

    @classmethod
    def add_features_to(cls, graph: Graph, features: Iterable[reader.Feature]) -> None:
        self = cls(graph)
        self.add_features(features)
        self.cleanup()

    def add_features(self, features: Iterable[reader.Feature]) -> None:
        for feature in features:
            self.add_feature(feature)

    def add_feature(self, feature: reader.Feature) -> None:
        if isinstance(feature, reader.Node):
            self.add_node(feature)
        elif isinstance(feature, reader.Way):
            self.add_way(feature)
        else:
            self.add_relation(feature)

    def add_node(self, node: reader.Node) -> None:
        if node.id >= _MAX_NODE_ID:
            raise ValueError(
                f"OpenStreetMap node uses a very big ID ({node.id}). "
                "Such big ids are used internally for phantom nodes created when handling turn "
                "restrictions, and therefore not permitted, as it could create ID conflicts."
            )

        if node.id not in self.g.nodes:
            self.g.nodes[node.id] = GraphNode(
                id=node.id,
                position=node.position,
                external_id=node.id,
            )
            self.unused_nodes.add(node.id)

    def add_way(self, way: reader.Way) -> None:
        penalty = self._get_way_penalty(way)
        if penalty is None:
            return

        nodes = self._get_way_nodes(way)
        if nodes is None:
            return

        forward, backward = self.g.profile.way_direction(way.tags)
        self._create_edges(nodes, penalty, forward, backward)
        self._update_state_after_adding_way(way.id, nodes)

    def _get_way_penalty(self, way: reader.Way) -> Optional[float]:
        """_get_way_penalty gets the penalty for using this way from the
        graph's :py:class:`Profile` and validates it.

        Returns ``None`` if way is unroutable, a penalty ≥ 1, or raises ValueError.
        """
        penalty = self.g.profile.way_penalty(way.tags)
        if penalty is not None and (not isfinite(penalty) or penalty < 1.0):
            raise ValueError(
                f"{self.g.profile} returned invalid way penalty {penalty}. "
                "Penalties must be finite and not smaller than 1.0."
            )
        return penalty

    def _get_way_nodes(self, way: reader.Way) -> Optional[List[int]]:
        """_get_way_nodes removes any unknown references from ``way.nodes``
        and emits warnings for them. Returns the filtered list, or ``None``
        if the way is too short to be usable after reference validation.
        """

        # Remove references to unknown nodes
        nodes: List[int] = []
        for node in way.nodes:
            if node in self.g.nodes:
                nodes.append(node)
            else:
                osm_logger.warning(
                    "way %d references non-existing node %d - skipping node",
                    way.id,
                    node,
                )

        # Ensure the way still connects something after removing unknown references
        if len(nodes) < 2:
            osm_logger.warning(
                "way %d has too few nodes (after unknown nodes were removed) - skipping way",
                way.id,
            )
            return None

        return nodes

    def _create_edges(
        self,
        nodes: List[int],
        penalty: float,
        forward: bool,
        backward: bool,
    ) -> None:
        """_create_edges adds edges between ``nodes`` to the underlying graph,
        depending on the values of ``forward`` and ``backward``.
        The cost of each edge is the :py:func:`haversine_earth_distance` multiplied by ``penalty``.
        """
        for left_id, right_id in pairwise(nodes):
            left = self.g.nodes[left_id]
            right = self.g.nodes[right_id]
            weight = penalty * haversine_earth_distance(left.position, right.position)

            if forward:
                self.g.edges.setdefault(left_id, {})[right_id] = weight
            if backward:
                self.g.edges.setdefault(right_id, {})[left_id] = weight

    def _update_state_after_adding_way(self, way_id: int, nodes: List[int]) -> None:
        """_update_state_after_adding_way updates builder attributes after
        a way was successfully added to the graph."""
        self.unused_nodes.difference_update(nodes)
        self.way_nodes[way_id] = nodes

    def add_relation(self, relation: reader.Relation) -> None:
        restriction = self.g.profile.is_turn_restriction(relation.tags)
        if restriction is TurnRestriction.INAPPLICABLE:
            return

        try:
            is_mandatory = restriction is TurnRestriction.MANDATORY
            nodes = self._get_restriction_nodes(relation)
            self._store_restriction(relation.id, nodes, is_mandatory)
        except _InvalidTurnRestriction as e:
            e.log()

    def _get_restriction_nodes(self, r: reader.Relation) -> List[int]:
        """_get_turn_restriction_nodes return a sequence of nodes representing the route
        of a turn restriction. Only the last 2 members of the ``from`` member and
        first 2 member of the ``to`` member are taken into account.

        May raise :py:exc:`_InvalidTurnRestriction` if there are any issues during the processing.
        """
        members = self._get_ordered_restriction_members(r)
        member_nodes = [self._restriction_member_to_nodes(r, m) for m in members]
        return self._flatten_restriction_nodes(r, member_nodes)

    def _get_ordered_restriction_members(
        self,
        r: reader.Relation,
    ) -> List[reader.RelationMember]:
        """_get_ordered_turn_restriction_members returns a list of turn restriction
        members in the order from-via-...-via-to. Ensures there is exactly one ``from`` member,
        exactly one ``to`` member and at least one ``via`` member. Any other members are ignored.
        """
        from_: Optional[reader.RelationMember] = None
        to: Optional[reader.RelationMember] = None
        order: List[reader.RelationMember] = []

        for member in r.members:
            if member.role == "from":
                if from_:
                    raise _InvalidTurnRestriction(r, 'multiple "from" members')
                from_ = member

            elif member.role == "via":
                order.append(member)

            elif member.role == "to":
                if to:
                    raise _InvalidTurnRestriction(r, 'multiple "to" members')
                to = member

        if not from_:
            raise _InvalidTurnRestriction(r, 'missing "from" member')
        if not order:
            raise _InvalidTurnRestriction(r, 'missing "via" member')
        if not to:
            raise _InvalidTurnRestriction(r, 'missing "to" member')

        order.insert(0, from_)
        order.append(to)
        return order

    def _restriction_member_to_nodes(
        self,
        r: reader.Relation,
        member: reader.RelationMember,
    ) -> List[int]:
        """_restriction_member_to_nodes returns a list of nodes corresponding to a given
        turn restriction member.

        ``node`` references are only permitted for ``via`` members.
        ``way`` references return a list instance from ``self.way_nodes``, so care must be
        taken to ensure that the returned list is still usable by further restrictions.

        Any invalid members cause :py:exc:`_InvalidTurnRestriction` to be raised.
        """
        if member.type == "node" and member.role == "via":
            if member.ref not in self.g.nodes:
                raise _InvalidTurnRestriction(r, f"reference to unknown node: {member.ref}")
            return [member.ref]

        elif member.type == "way":
            nodes = self.way_nodes.get(member.ref)
            if not nodes:
                raise _InvalidTurnRestriction(r, f"reference to unknown way: {member.ref}")
            return nodes

        else:
            raise _InvalidTurnRestriction(
                r,
                f"invalid type of {member.role!r} member: {member.type}",
            )

    @staticmethod
    def _flatten_restriction_nodes(
        relation: reader.Relation,
        members_nodes: List[List[int]],
    ) -> List[int]:
        """_flatten_restriction_nodes turns a list of turn restriction members' nodes
        into a flat list of nodes. Only the last two nodes of the ``from`` member
        and the first two nodes of the ``to`` member are taken into account.

        Raises :py:exc:`_InvalidTurnRestriction` if the members are disjoined, that is
        they don't have a node in common.
        """
        nodes: List[int] = []

        for idx, member_nodes in enumerate(members_nodes):
            is_first = idx == 0
            is_last = idx == len(members_nodes) - 1

            if is_first:
                # First member needs to be reversed if its first (not last) node matches with
                # the second member's first/last node
                if member_nodes[-1] in (members_nodes[1][0], members_nodes[1][-1]):
                    # correct order, (A-B, B-C) or (A-B, C-B) case
                    pass
                elif member_nodes[0] in (members_nodes[1][0], members_nodes[1][-1]):
                    # incorrect order, (B-A, B-C) or (B-A, C-B) case
                    member_nodes.reverse()
                else:
                    # disjoined restriction, (A-B, C-D) case
                    raise _InvalidTurnRestriction(relation, "disjoined members")

            else:
                # Every other member needs to be reversed if its last (not first) node matches
                # with the previous member's last node
                if nodes[-1] == member_nodes[0]:
                    # correct order, (A-B, B-C) case
                    pass
                elif nodes[-1] == member_nodes[-1]:
                    # incorrect order, (A-B, C-B) case
                    member_nodes.reverse()
                else:
                    # disjoined restriction, (A-B, C-D) case
                    raise _InvalidTurnRestriction(relation, "disjoined members")

            assert is_first or nodes[-1] == member_nodes[0]
            if is_first:
                # "from" member - only care about the last 2 nodes; A-B-C-D → C-D
                nodes.extend(member_nodes[-2:])
            elif is_last:
                # "to" member - only care about the first 2 nodes,
                # but the first node was appended as the last node of the previous member,
                # thus only append the second node
                # A-B-C-D → A-B -("A" appended in previous step)→ B
                nodes.append(member_nodes[1])
            else:
                # "via" member - skip first node, as it was appended as the last node of
                # the precious member
                nodes.extend(member_nodes[1:])

        return nodes

    def _store_restriction(
        self,
        relation_id: int,
        osm_nodes: List[int],
        is_mandatory: bool,
    ) -> None:
        """_store_restriction modifies the graph to support the provided turn restriction,
        given by its sequence of OSM node ids and a flag indicating if it's a mandatory or a
        prohibitory restriction. ``relation_id`` is only used for reporting unsatisfiable
        restrictions.
        """

        # To store a turn restriction A-B-C-D-E, we replace all via nodes with phantom clones,
        # A-B'-C'-D'-E, and replace the A-B edge by A-B'.
        # For prohibitive restrictions, all of the original edges from the via nodes must be
        # retained, except for the D'-E edge.
        # For mandatory restrictions, all of the original edges from the via node must be
        # removed, except for the edges indicated by the restriction.
        # If a phantom node B' linked from A already exists, it must be reused.

        change: _GraphChange = _GraphChange(self.g)
        cloned_nodes = change.restriction_as_cloned_nodes(osm_nodes)

        if cloned_nodes is None:
            osm_logger.warning(
                "turn restriction %d: %s a non-existing route - skipping",
                relation_id,
                "mandates" if is_mandatory else "prohibits",
            )
            return  # discarding the change

        elif is_mandatory:
            for a, b in pairwise(cloned_nodes[1:]):
                change.ensure_only_edge(a, b)

        else:
            change.edges_to_remove.add((cloned_nodes[-2], cloned_nodes[-1]))

        change.apply()

    def cleanup(self) -> None:
        """cleanup removes unused nodes from the graph."""
        for node_id in self.unused_nodes:
            del self.g.nodes[node_id]
        gc.collect()


class _GraphChange:
    """_GraphChange represents a change to the :py:class:`Graph` which needs to be applied
    atomically/in one go.
    """

    g: Graph

    new_nodes: Dict[int, int]
    """Nodes to clone (including their edges), mapping from new id to old id."""

    edges_to_add: Dict[int, Dict[int, float]]
    """New edges to add, mapping from (new) node id to (new) node id to cost.
    Takes precedence over :py:attr:`new_nodes` and :py:attr:`edges_to_remove`.
    """

    edges_to_remove: Set[Tuple[int, int]]
    """Edges to remove, set of (from (new) node id, to (new) node id).
    Takes precedence over :py:attr:`new_nodes`, but **not** :py:attr:`edges_to_add`.
    """

    phantom_node_id_counter: int
    """New value for :py:attr:`Graph._phantom_node_id_counter`."""

    def __init__(self, g: Graph) -> None:
        self.g = g
        self.new_nodes = {}
        self.edges_to_add = {}
        self.edges_to_remove = set()
        self.phantom_node_id_counter = self.g._phantom_node_id_counter  # pyright: ignore

    def restriction_as_cloned_nodes(self, osm_nodes: List[int]) -> Optional[List[int]]:
        """Turns a A-B-C-D-E list of OSM nodes into a A-B'-C'-D'-E list by cloning
        all middle nodes. Cloned nodes (including E') may be re-used, if a B' node and A-B' edge
        already exists.

        Returns ``None`` if osm_nodes represents a disjoined sequence, and in this case
        the _GraphChange **must** be discarded, as it may contain garbage changes.
        """
        assert len(osm_nodes) >= 3

        cloned_nodes = [osm_nodes[0]]
        for osm_node_id in osm_nodes[1:]:
            previous_node_id = cloned_nodes[-1]
            original_node_id = self._get_to_node_id(previous_node_id, osm_node_id)
            if original_node_id is None:
                return None

            is_clone = osm_node_id != original_node_id
            is_last = osm_node_id == osm_nodes[-1]

            # We need to make a clone of `node` if the edge from `previous_node_id` to a node
            # with `osm_node_id` is to a non-phantom node AND not `is_last`.
            if not is_clone and not is_last:
                cost = self._get_edge_cost(previous_node_id, original_node_id)
                cloned_node_id = self._make_node_clone(original_node_id)
                self.edges_to_remove.add((previous_node_id, original_node_id))
                self.edges_to_add.setdefault(previous_node_id, {})[cloned_node_id] = cost
            else:
                cloned_node_id = original_node_id

            cloned_nodes.append(cloned_node_id)

        return cloned_nodes

    def _get_to_node_id(self, from_node_id: int, to_osm_id: int) -> Optional[int]:
        """_get_to_node_id gets the id of a node with a given ``to_osm_id``,
        with an edge going in from a node identified by ``from_node_id``.
        """
        original_from_node_id = self.new_nodes.get(from_node_id, from_node_id)
        for candidate_to_node_id in self.g.edges.get(original_from_node_id, {}):
            candidate_to_osm_id = self.g.nodes[candidate_to_node_id].osm_id
            if candidate_to_osm_id == to_osm_id:
                return candidate_to_node_id
        return None

    def _make_node_clone(self, original_node_id: int) -> int:
        """_make_node_clone records that ``original_node_id`` should be cloned,
        and returns the ID of the cloned node. Edges are also cloned."""
        assert original_node_id in self.g.nodes
        self.phantom_node_id_counter += 1
        cloned_node_id = self.phantom_node_id_counter
        self.new_nodes[cloned_node_id] = original_node_id
        return cloned_node_id

    def _get_edge_cost(self, from_node_id: int, to_node_id: int) -> float:
        """_get_edge_cost returns the cost of an edge from ``from_node_id``
        to ``to_node_id``. While ``from_node_id`` might be an id of a cloned node,
        ``to_node_id`` must exist in the :py:class:`Graph`.
        """
        if overridden_cost := self.edges_to_add.get(from_node_id, {}).get(to_node_id):
            return overridden_cost

        original_from_node_id = self.new_nodes.get(from_node_id, from_node_id)
        return self.g.edges[original_from_node_id][to_node_id]

    def apply(self) -> None:
        """apply applies all changes to the :py:class:`Graph`."""
        self.g._phantom_node_id_counter = self.phantom_node_id_counter  # pyright: ignore
        self._clone_nodes()
        self._remove_edges()
        self._add_edges()

    def _clone_nodes(self) -> None:
        """_clone_nodes applies changes prescribed by :py:attr:`new_nodes`."""
        for new_id, old_id in self.new_nodes.items():
            old_node = self.g.nodes[old_id]
            self.g.nodes[new_id] = GraphNode(
                id=new_id,
                position=old_node.position,
                external_id=old_node.osm_id,
            )
            self.g.edges[new_id] = self.g.edges[old_id].copy()

    def _remove_edges(self) -> None:
        """_remove_edges applies changes prescribed by :py:attr:`edges_to_remove`."""
        for from_id, to_id in self.edges_to_remove:
            _ = self.g.edges[from_id].pop(to_id, None)

    def _add_edges(self) -> None:
        """_add_edges applies changes prescribed by :py:attr:`edges_to_add`."""
        for from_id, edges in self.edges_to_add.items():
            for to_id, cost in edges.items():
                self.g.edges.setdefault(from_id, {})[to_id] = cost

    def ensure_only_edge(self, from_node_id: int, to_node_id: int) -> None:
        """ensure_only_edge ensure that the only node from ``from_node_id``
        is to node ``to_node_id``. Both ids might represent freshly-cloned nodes.
        """
        if from_node_id in self.edges_to_add:
            self.edges_to_add[from_node_id] = {
                to: cost for to, cost in self.edges_to_add[from_node_id].items() if to == to_node_id
            }

        original_from_node_id = self.new_nodes.get(from_node_id, from_node_id)
        for to in self.g.edges[original_from_node_id]:
            if to != to_node_id:
                self.edges_to_remove.add((from_node_id, to))


class _InvalidTurnRestriction(ValueError):
    """_InvalidTurnRestriction is raised when a turn restriction can't be applied
    to an :py:class:`Graph`. It is raised and caught by :py:class:`_GraphBuilder`,
    which logs the issues and moves onto processing next features.
    """

    def __init__(self, restriction: reader.Relation, reason: str) -> None:
        super().__init__(f"invalid turn restriction {restriction.id}: {reason} - skipping")
        self.restriction = restriction
        self.reason = reason

    def log(self) -> None:
        osm_logger.warning(self.args[0])
