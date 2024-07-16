from dataclasses import dataclass, field
from functools import singledispatchmethod
from io import DEFAULT_BUFFER_SIZE
from itertools import pairwise
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
        """add_features adds OpenStreetMap data to the graph."""
        builder = _OSMGraphBuilder(self)
        builder.add_features(features)
        builder.cleanup()

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
    g: OSMGraph
    unused_nodes: Set[int] = field(default_factory=set)
    way_nodes: Dict[int, List[int]] = field(default_factory=dict)

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
        penalty = self.g.profile.way_penalty(way.tags)
        if penalty is not None and (not isfinite(penalty) or penalty < 1.0):
            raise ValueError(
                f"{self.g.profile} returned invalid way penalty {penalty}. "
                "Penalties must be finite and not smaller than 1.0."
            )
        return penalty

    def _get_way_nodes(self, way: osm_reader.Way) -> Optional[List[int]]:
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
        for left_id, right_id in pairwise(nodes):
            left = self.g.data[left_id]
            right = self.g.data[right_id]
            weight = penalty * haversine_earth_distance(left.position, right.position)

            if forward:
                left.edges[right_id] = weight
            if backward:
                right.edges[left_id] = weight

    def _update_state_after_adding_way(self, way_id: int, nodes: List[int]) -> None:
        self.unused_nodes.difference_update(nodes)
        self.way_nodes[way_id] = nodes

    @add_feature.register
    def add_relation(self, relation: osm_reader.Relation) -> None:
        pass  # TODO: add_relation

    def cleanup(self) -> None:
        for node_id in self.unused_nodes:
            del self.g.data[node_id]
