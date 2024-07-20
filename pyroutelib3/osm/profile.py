from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar, Dict, List, Mapping, Optional, Protocol, Tuple


class TurnRestriction(Enum):
    """TurnRestriction indicates whether an `OSM relation <https://wiki.openstreetmap.org/wiki/Relation>`_
    is an applicable `turn restriction <https://wiki.openstreetmap.org/wiki/Relation:restriction>`_.
    Used as the return value of :py:meth:`Profile.is_turn_restriction`.
    """

    INAPPLICABLE = 0
    """Not a turn restriction, or a restriction not applicable to the current :py:class:`Profile`."""

    PROHIBITORY = 1
    """Prohibitory (no_*) restriction, following the route of restriction is not allowed."""

    MANDATORY = 2
    """Mandatory (only_*) restriction, stepping from the "from" onto the "via" member
    forces the use of the restriction's route.
    """


class Profile(Protocol):
    """Profile instructs how :py:class:`Graph` should convert OSM features into a
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

    def is_turn_restriction(self, __relation_tags: Mapping[str, str]) -> TurnRestriction:
        """is_turn_restriction must determine whether the relation (given by its tags) is
        an applicable `turn restriction <https://wiki.openstreetmap.org/wiki/Relation:restriction>`_.

        If the relation is not a turn restriction, or is a turn restriction not applicable
        to this Profile, must return :py:obj:`TurnRestriction.INAPPLICABLE`.

        If following the route of the restriction is forbidden, must return
        :py:obj:`TurnRestriction.PROHIBITORY`.

        If following the route of the restriction is forced, must return
        :py:obj:`TurnRestriction.MANDATORY`.
        """
        ...


@dataclass
class HighwayProfile(Profile):
    """HighwayProfile implements :py:class:`Profile` for routing over highway=* ways."""

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

    def is_turn_restriction(self, tags: Mapping[str, str]) -> TurnRestriction:
        if tags.get("type") != "restriction" or self.is_exempted(tags):
            return TurnRestriction.INAPPLICABLE

        restriction = tags.get("restriction", "")
        kind, _, description = restriction.partition("_")
        # fmt: off
        if (
            kind in ("no", "only")
            and description in ("right_turn", "left_turn", "u_turn", "straight_on")
        ):
            return TurnRestriction.PROHIBITORY if kind == "no" else TurnRestriction.MANDATORY
        # fmt: on

        return TurnRestriction.INAPPLICABLE

    def is_exempted(self, restriction_tags: Mapping[str, str]) -> bool:
        exempted = restriction_tags.get("except")
        if exempted is None:
            return False
        return any(exempted_type in self.access for exempted_type in exempted.split(";"))


PROFILE_CAR = HighwayProfile(
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
"""PROFILE_CAR is a :py:class:`HighwayProfile` which can be used for car routing."""

PROFILE_BUS = HighwayProfile(
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
"""PROFILE_BUS is a :py:class:`HighwayProfile` which can be used for bus routing."""


PROFILE_CYCLE = HighwayProfile(
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
"""PROFILE_CYCLE is a :py:class:`HighwayProfile` which can be used for bicycle routing."""


PROFILE_FOOT = HighwayProfile(
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
"""PROFILE_FOOT is a :py:class:`HighwayProfile` which can be used for on-foot routing."""
