import sys
from dataclasses import dataclass, field
from functools import singledispatchmethod
from io import DEFAULT_BUFFER_SIZE
from logging import getLogger
from math import isfinite
from typing import (
    IO,
    ClassVar,
    Dict,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Protocol,
    Set,
    Tuple,
)

from typing_extensions import Self

from . import osm_reader
from .distance import haversine_earth_distance
from .protocols import Position

osm_logger = getLogger("pyroutelib3.osm")

_MAX_OSM_NODE_ID = 0x0008_0000_0000_0000
"""_MAX_OSM_NODE_ID is the maximum permitted ID of a node coming from OpenStreetMap.
Values of _MAX_OSM_NODE_ID and above are used for phantom nodes created by turn restrictions.
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


class OSMProfile(Protocol):
    """Profile instructs how :py:class:`OSMGraph` should convert OSM features into a
    routing graph.
    """

    def way_penalty(self, __way_tags: Mapping[str, str]) -> Optional[float]:
        """way_penalty must return the penalty for traversing a way with the provided tags,
        or ``None`` if the way is not traversable.

        The returned penalty is then multiplied by the each way's segment length
        to get the cost of traversing an edge.

        The returned value must be finite and at least 1.
        """
        ...

    def way_direction(self, __way_tags: Mapping[str, str]) -> Tuple[bool, bool]:
        """way_direction must determine whether a way with the provided tags
        is traversable forward and backward. First element in the returned tuple
        must represent the forward direction, while the second - backward direction.
        """
        ...

    def is_exempted(self, __restriction_tags: Mapping[str, str]) -> bool:
        """is_exempted must determine whether the current Profile is exempted
        from adhering to the provided `turn restriction <https://wiki.openstreetmap.org/wiki/Relation:restriction>`_
        based on its tags.
        """
        ...


@dataclass
class OSMHighwayProfile:
    """OSMHighwayProfile implements :py:class:`OSMProfile` for routing over highway=* ways."""

    name: str

    penalties: Dict[str, float] = field(repr=False)
    """penalties maps highway tag values (after transformation through :py:obj:`EQUIVALENT_TAGS`)
    into their corresponding penalties. All penalties must be finite and not smaller than 1.
    """

    access: List[str] = field(repr=False)
    """access is the hierarchy of `access tags <https://wiki.openstreetmap.org/wiki/Key:access>`_
    to consider when checking if a route is traversable. Keys must be listed from least-specific
    first.
    """

    EQUIVALENT_TAGS: ClassVar[Mapping[str, str]] = {
        "motorway_link": "motorway",
        "trunk_link": "trunk",
        "primary_link": "primary",
        "secondary_link": "secondary",
        "tertiary_link": "tertiary",
        "minor": "unclassified",
        "pedestrian": "footway",
        "platform": "footway",
    }

    def way_penalty(self, way_tags: Mapping[str, str]) -> Optional[float]:
        # Get the penalty of the highway tag
        highway = way_tags.get("highway", "")
        highway = self.EQUIVALENT_TAGS.get(highway, highway)
        penalty = self.penalties.get(highway)
        if penalty is None:
            return None

        # Check if the way is traversable, as per the access tags
        if not self.is_allowed(way_tags):
            return None

        return penalty

    def is_allowed(self, way_tags: Mapping[str, str]) -> bool:
        allowed = True
        for access_tag in self.access:
            value = way_tags.get(access_tag)
            if value is None:
                pass
            elif value in ("no", "private"):
                allowed = False
            else:
                allowed = True
        return allowed

    def way_direction(self, way_tags: Mapping[str, str]) -> Tuple[bool, bool]:
        # Start by assuming two-way
        forward = True
        backward = True

        # Default one-way ways
        # fmt: off
        if (
            way_tags.get("highway") in ("motorway", "motorway_link")
            or way_tags.get("junction") in ("roundabout", "circular")
        ):
            # fmt: on
            backward = False

        # Check against the oneway tag
        oneway = way_tags.get("oneway")
        if oneway in ("yes", "true", "1"):
            forward = True
            backward = False
        elif oneway in ("-1", "reverse"):
            forward = False
            backward = True
        elif oneway == "no":
            forward = True
            backward = True

        return forward, backward

    def is_exempted(self, restriction_tags: Mapping[str, str]) -> bool:
        exempted = restriction_tags.get("except")
        if exempted is None:
            return False
        return any(exempted_type in self.access for exempted_type in exempted.split(";"))


OSM_PROFILE_CAR = OSMHighwayProfile(
    name="motorcar",
    penalties={
        "motorway": 1.0,
        "trunk": 1.0,
        "primary": 5.0,
        "secondary": 6.5,
        "tertiary": 10.0,
        "unclassified": 10.0,
        "residential": 15.0,
        "living_street": 20.0,
        "track": 20.0,
        "service": 20.0,
    },
    access=["access", "vehicle", "motor_vehicle", "motorcar"],
)
"""OSM_PROFILE_CAR is a :py:class:`OSMHighwayProfile` which can be used for car routing."""

OSM_PROFILE_BUS = OSMHighwayProfile(
    name="bus",
    penalties={
        "motorway": 1.0,
        "trunk": 1.0,
        "primary": 1.1,
        "secondary": 1.15,
        "tertiary": 1.15,
        "unclassified": 1.5,
        "residential": 2.5,
        "living_street": 2.5,
        "track": 5.0,
        "service": 5.0,
    },
    access=["access", "vehicle", "motor_vehicle", "psv", "bus", "routing:ztm"],
)
"""OSM_PROFILE_BUS is a :py:class:`OSMHighwayProfile` which can be used for bus routing."""


OSM_PROFILE_CYCLE = OSMHighwayProfile(
    name="bicycle",
    penalties={
        "trunk": 50.0,
        "primary": 10.0,
        "secondary": 3.0,
        "tertiary": 2.5,
        "unclassified": 2.5,
        "cycleway": 1.0,
        "residential": 1.0,
        "living_street": 1.5,
        "track": 2.0,
        "service": 2.0,
        "bridleway": 3.0,
        "footway": 3.0,
        "steps": 5.0,
        "path": 2.0,
    },
    access=["access", "vehicle", "bicycle"],
)
"""OSM_PROFILE_CYCLE is a :py:class:`OSMHighwayProfile` which can be used for bicycle routing."""


OSM_PROFILE_FOOT = OSMHighwayProfile(
    name="foot",
    penalties={
        "trunk": 4.0,
        "primary": 2.0,
        "secondary": 1.3,
        "tertiary": 1.2,
        "unclassified": 1.2,
        "residential": 1.2,
        "living_street": 1.2,
        "track": 1.2,
        "service": 1.2,
        "bridleway": 1.2,
        "footway": 1.0,
        "path": 1.0,
        "steps": 1.15,
    },
    access=["access", "foot"],
)
"""OSM_PROFILE_FOOT is a :py:class:`OSMHighwayProfile` which can be used for on-foot routing."""


@dataclass(frozen=True)
class OSMGraphNode:
    """OSMGraphNode is a *node* in a :py:class:`OSMGraph`."""

    id: int
    position: Position
    osm_id: int
    edges: Dict[int, float] = field(default_factory=dict)

    @property
    def external_id(self) -> int:
        return self.osm_id


class OSMGraph:
    """OSMGraph implements :py:class:`GraphLike` over OpenStreetMap data."""

    profile: OSMProfile
    data: Dict[int, OSMGraphNode]

    _phantom_node_id_counter: int
    """_phantom_node_id_counter is a counter used for generating IDs for phantom nodes
    created when processing turn restriction. Used by :py:class:`_OSMGraphBuilder` and
    :py:class:`_OSMGraphChange`.
    """

    def __init__(
        self,
        profile: OSMProfile,
        data: Optional[Dict[int, OSMGraphNode]] = None,
    ) -> None:
        self.profile = profile
        self.data = data or {}
        self._phantom_node_id_counter = _MAX_OSM_NODE_ID

    def get_node(self, id: int) -> OSMGraphNode:
        return self.data[id]

    def get_edges(self, id: int) -> Iterable[Tuple[int, float]]:
        return self.data[id].edges.items()

    def find_nearest_node(self, position: Position) -> OSMGraphNode:
        """find_nearest_node finds the closest node to the provided :py:obj:`Position`.
        Phantom nodes ``nd.id != nd.osm_id`` created by turn restrictions are not considered.

        This function iterates over every contained :py:class:`OSMGraphNode`, and can be
        very slow for big graphs. Use a helper data structure (like a K-D tree) if this function
        becomes a performance bottleneck.
        """

        return min(
            (nd for nd in self.data.values() if nd.id == nd.osm_id),
            key=lambda nd: haversine_earth_distance(position, nd.position),
        )

    def add_features(self, features: Iterable[osm_reader.Feature]) -> None:
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
        _OSMGraphBuilder.add_features_to(self, features)

    @classmethod
    def from_features(cls, profile: OSMProfile, features: Iterable[osm_reader.Feature]) -> Self:
        """Creates a :py:class:`OSMGraph` based on the provided ``profile`` and ``features``."""
        g = cls(profile)
        g.add_features(features)
        return g

    @classmethod
    def from_file(
        cls,
        profile: OSMProfile,
        buf: IO[bytes],
        format: Optional[Literal["xml", "bz2", "gz"]] = None,
        chunk_size: int = DEFAULT_BUFFER_SIZE,
    ) -> Self:
        """Creates a :py:class:`OSMGraph` based on the provided ``profile`` and features
        from the provided OSM file.

        ``format`` and ``chunk_size`` are passed through to :py:func:`osm_reader.read_features`.
        """
        return cls.from_features(profile, osm_reader.read_features(buf, format, chunk_size))


@dataclass
class _OSMGraphBuilder:
    """_OSMGraphBuilder is responsible for adding a self-contained batch of features to
    a :py:class:`OSMGraph`.

    See the restrictions on :py:meth:`OSMGraph.add_features` for underlying data assumptions.

    Usage::
        _OSMGraphBuilder.add_features_to(osm_graph, features)
    """

    g: OSMGraph

    unused_nodes: Set[int] = field(default_factory=set)
    """unused_nodes is a set of nodes added to the graph which weren't used
    by any way - and should be removed once all features have been processed.
    """

    way_nodes: Dict[int, List[int]] = field(default_factory=dict)
    """way_nodes maps way_ids to its sequence of nodes, required for relation processing."""

    @classmethod
    def add_features_to(cls, graph: OSMGraph, features: Iterable[osm_reader.Feature]) -> None:
        self = cls(graph)
        self.add_features(features)
        self.cleanup()

    def add_features(self, features: Iterable[osm_reader.Feature]) -> None:
        for feature in features:
            self.add_feature(feature)

    @singledispatchmethod
    def add_feature(self, feature: osm_reader.Feature) -> None:
        raise RuntimeError(f"invalid feature type: {type(feature).__qualname__}")

    @add_feature.register
    def add_node(self, node: osm_reader.Node) -> None:
        if node.id >= _MAX_OSM_NODE_ID:
            raise RuntimeError(
                f"OpenStreetMap node uses a very big ID ({node.id}). "
                "Such big ids are used internally for phantom nodes created when handling turn "
                "restrictions, and therefore not permitted, as it could create ID conflicts."
            )

        if node.id not in self.g.data:
            self.g.data[node.id] = OSMGraphNode(
                id=node.id,
                position=node.position,
                osm_id=node.id,
            )
            self.unused_nodes.add(node.id)

    @add_feature.register
    def add_way(self, way: osm_reader.Way) -> None:
        penalty = self._get_way_penalty(way)
        if penalty is None:
            return

        nodes = self._get_way_nodes(way)
        if nodes is None:
            return

        forward, backward = self.g.profile.way_direction(way.tags)
        self._create_edges(nodes, penalty, forward, backward)
        self._update_state_after_adding_way(way.id, nodes)

    def _get_way_penalty(self, way: osm_reader.Way) -> Optional[float]:
        """_get_way_penalty gets the penalty for using this way from the
        graph's :py:class:`OSMProfile` and validates it.

        Returns ``None`` if way is unroutable, a penalty ≥ 1, or raises ValueError.
        """
        penalty = self.g.profile.way_penalty(way.tags)
        if penalty is not None and (not isfinite(penalty) or penalty < 1.0):
            raise ValueError(
                f"{self.g.profile} returned invalid way penalty {penalty}. "
                "Penalties must be finite and not smaller than 1.0."
            )
        return penalty

    def _get_way_nodes(self, way: osm_reader.Way) -> Optional[List[int]]:
        """_get_way_nodes removes any unknown references from ``way.nodes``
        and emits warnings for them. Returns the filtered list, or ``None``
        if the way is too short to be usable after reference validation.
        """

        # Remove references to unknown nodes
        nodes: List[int] = []
        for node in way.nodes:
            if node in self.g.data:
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
            left = self.g.data[left_id]
            right = self.g.data[right_id]
            weight = penalty * haversine_earth_distance(left.position, right.position)

            if forward:
                left.edges[right_id] = weight
            if backward:
                right.edges[left_id] = weight

    def _update_state_after_adding_way(self, way_id: int, nodes: List[int]) -> None:
        """_update_state_after_adding_way updates builder attributes after
        a way was successfully added to the graph."""
        self.unused_nodes.difference_update(nodes)
        self.way_nodes[way_id] = nodes

    @add_feature.register
    def add_relation(self, relation: osm_reader.Relation) -> None:
        if not self._is_applicable_turn_restriction(relation):
            return

        try:
            is_mandatory = self._is_mandatory_restriction(relation)
            nodes = self._get_restriction_nodes(relation)
            self._store_restriction(relation.id, nodes, is_mandatory)
        except _InvalidTurnRestriction as e:
            e.log()

    def _is_applicable_turn_restriction(self, relation: osm_reader.Relation) -> bool:
        """_is_applicable_turn_restriction returns ``True`` if the provided
        relation represents a turn restriction applicable to the current profile."""
        return (
            relation.tags.get("type") == "restriction"
            and relation.tags.get("restriction", "").startswith(("no_", "only_"))
            and not self.g.profile.is_exempted(relation.tags)
        )

    def _is_mandatory_restriction(self, relation: osm_reader.Relation) -> bool:
        """_is_mandatory_restriction returns ``True`` if the relation represents
        a mandatory turn restriction, ``False`` for prohibitory turn restriction,
        and raises :py:exc:`_InvalidTurnRestriction` otherwise.
        """

        restriction = relation.tags.get("restriction", "")
        kind, _, description = restriction.partition("_")
        # fmt: off
        if (
            kind in ("no", "only")
            and description in ("right_turn", "left_turn", "u_turn", "straight_on")
        ):
            return kind == "only"
        # fmt: on
        raise _InvalidTurnRestriction(
            relation, f'unknown "restriction" tag value: {restriction!r}'
        )

    def _get_restriction_nodes(self, r: osm_reader.Relation) -> List[int]:
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
        r: osm_reader.Relation,
    ) -> List[osm_reader.RelationMember]:
        """_get_ordered_turn_restriction_members returns a list of turn restriction
        members in the order from-via-...-via-to. Ensures there is exactly one ``from`` member,
        exactly one ``to`` member and at least one ``via`` member. Any other members are ignored.
        """
        from_: Optional[osm_reader.RelationMember] = None
        to: Optional[osm_reader.RelationMember] = None
        order: List[osm_reader.RelationMember] = []

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
        r: osm_reader.Relation,
        member: osm_reader.RelationMember,
    ) -> List[int]:
        """_restriction_member_to_nodes returns a list of nodes corresponding to a given
        turn restriction member.

        ``node`` references are only permitted for ``via`` members.
        ``way`` references return a list instance from ``self.way_nodes``, so care must be
        taken to ensure that the returned list is still usable by further restrictions.

        Any invalid members cause :py:exc:`_InvalidTurnRestriction` to be raised.
        """
        if member.type == "node" and member.role == "via":
            if member.ref not in self.g.data:
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
        relation: osm_reader.Relation,
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

        change: Optional[_OSMGraphChange] = _OSMGraphChange(self.g)
        cloned_nodes = change.restriction_as_cloned_nodes(osm_nodes)

        if cloned_nodes is None and is_mandatory:
            # Unsatisfiable mandatory restriction. Since the
            osm_logger.warning(
                "turn restriction %d: mandates a non-existing route - removing %d->%d from graph",
                relation_id,
                osm_nodes[0],
                osm_nodes[1],
            )
            change = _OSMGraphChange(self.g)
            change.edges_to_remove.add((osm_nodes[0], osm_nodes[1]))

        elif cloned_nodes is None:
            osm_logger.warning(
                "turn restriction %d: prohibits a non-existing route - skipping",
                relation_id,
            )
            change = None

        elif is_mandatory:
            for a, b in pairwise(cloned_nodes[1:]):
                change.ensure_only_edge(a, b)

        else:
            change.edges_to_remove.add((cloned_nodes[-2], cloned_nodes[-1]))

        if change:
            change.apply()

    def cleanup(self) -> None:
        """cleanup removes unused nodes from the graph."""
        for node_id in self.unused_nodes:
            del self.g.data[node_id]


class _OSMGraphChange:
    """_OSMGraphChange represents a change to the :py:class:`OSMGraph` which needs to be applied
    atomically/in one go.
    """

    g: OSMGraph

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
    """New value for :py:attr:`OSMGraph._phantom_node_id_counter`."""

    def __init__(self, g: OSMGraph) -> None:
        self.g = g
        self.new_nodes = {}
        self.edges_to_add = {}
        self.edges_to_remove = set()
        self.phantom_node_id_counter = self.g._phantom_node_id_counter  # pyright: ignore

    def restriction_as_cloned_nodes(self, osm_nodes: List[int]) -> Optional[List[int]]:
        """Turns a A-B-C-D-E list of OSM nodes into a A-B'-C'-D'-E list by cloning
        all middle nodes. Cloned nodes (including E') may be re-used, if a B' node and A-B' edge
        already exists. Returns ``None`` if osm_nodes represents a disjoined sequence.
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
        for candidate_to_node_id in self.g.data[original_from_node_id].edges:
            candidate_to_osm_id = self.g.data[candidate_to_node_id].osm_id
            if candidate_to_osm_id == to_osm_id:
                return candidate_to_node_id
        return None

    def _make_node_clone(self, original_node_id: int) -> int:
        """_make_node_clone records that ``original_node_id`` should be cloned,
        and returns the ID of the cloned node. Edges are also cloned."""
        assert original_node_id in self.g.data
        self.phantom_node_id_counter += 1
        cloned_node_id = self.phantom_node_id_counter
        self.new_nodes[cloned_node_id] = original_node_id
        return cloned_node_id

    def _get_edge_cost(self, from_node_id: int, to_node_id: int) -> float:
        """_get_edge_cost returns the cost of an edge from ``from_node_id``
        to ``to_node_id``. While ``from_node_id`` might be an id of a cloned node,
        ``to_node_id`` must exist in the :py:class:`OSMGraph`.
        """
        if overridden_cost := self.edges_to_add.get(from_node_id, {}).get(to_node_id):
            return overridden_cost

        original_from_node_id = self.new_nodes.get(from_node_id, from_node_id)
        return self.g.data[original_from_node_id].edges[to_node_id]

    def apply(self) -> None:
        """apply applies all changes to the :py:class:`OSMGraph`."""
        self.g._phantom_node_id_counter = self.phantom_node_id_counter  # pyright: ignore
        self._clone_nodes()
        self._remove_edges()
        self._add_edges()

    def _clone_nodes(self) -> None:
        """_clone_nodes applies changes prescribed by :py:attr:`new_nodes`."""
        for new_id, old_id in self.new_nodes.items():
            old_node = self.g.data[old_id]
            self.g.data[new_id] = OSMGraphNode(
                id=new_id,
                position=old_node.position,
                osm_id=old_node.osm_id,
                edges=old_node.edges.copy(),
            )

    def _remove_edges(self) -> None:
        """_remove_edges applies changes prescribed by :py:attr:`edges_to_remove`."""
        for from_id, to_id in self.edges_to_remove:
            _ = self.g.data[from_id].edges.pop(to_id, None)

    def _add_edges(self) -> None:
        """_add_edges applies changes prescribed by :py:attr:`edges_to_add`."""
        for from_id, edges in self.edges_to_add.items():
            for to_id, cost in edges.items():
                self.g.data[from_id].edges[to_id] = cost

    def ensure_only_edge(self, from_node_id: int, to_node_id: int) -> None:
        """ensure_only_edge ensure that the only node from ``from_node_id``
        is to node ``to_node_id``. Both ids might represent freshly-cloned nodes.
        """
        if (clone_from_id := self.new_nodes.get(from_node_id)) is not None:
            if from_node_id in self.edges_to_add:
                self.edges_to_add[from_node_id] = {
                    to: cost
                    for to, cost in self.edges_to_add[from_node_id].items()
                    if to == to_node_id
                }

            for to in self.g.data[clone_from_id].edges:
                if to != to_node_id:
                    self.edges_to_remove.add((from_node_id, to))

        else:
            for to in self.g.data[from_node_id].edges:
                if to != to_node_id:
                    self.edges_to_remove.add((from_node_id, to))


class _InvalidTurnRestriction(ValueError):
    """_InvalidTurnRestriction is raised when a turn restriction can't be applied
    to an :py:class:`OSMGraph`. It is raised and caught by :py:class:`_OSMGraphBuilder`,
    which logs the issues and moves onto processing next features.
    """

    def __init__(self, restriction: osm_reader.Relation, reason: str) -> None:
        super().__init__(f"invalid turn restriction {restriction.id}: {reason}")
        self.restriction = restriction
        self.reason = reason

    def log(self) -> None:
        osm_logger.warning(self.args[0])
