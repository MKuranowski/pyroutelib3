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


class SkeletonProfile(Profile):
    """SkeletonProfile implements :py:class:`Profile` for routing over every way in OSM data,
    regardless of used tags. This profile is meant for holding graphs in OSM XML/OSM PBF
    formats, without following OpenStreetMap mapping conventions. All relations (and thus
    turn restrictions) are ignored.

    The only introspected tag is ``oneway``, which may be set to ``yes`` or ``-1``.
    """

    def way_penalty(self, way_tags: Mapping[str, str]) -> Optional[float]:
        return 1.0

    def way_direction(self, way_tags: Mapping[str, str]) -> Tuple[bool, bool]:
        oneway = way_tags.get("oneway")
        if oneway == "yes":
            return True, False
        elif oneway == "-1":
            return False, True
        return True, True

    def is_turn_restriction(self, relation_tags: Mapping[str, str]) -> TurnRestriction:
        return TurnRestriction.INAPPLICABLE


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
    }

    def way_penalty(self, way_tags: Mapping[str, str]) -> Optional[float]:
        # Get the penalty of the highway tag
        highway = self.get_active_highway_value(way_tags)
        penalty = self.penalties.get(highway)
        if penalty is None:
            return None

        # Check if the way is traversable, as per the access tags
        if not self.is_allowed(way_tags):
            return None

        return penalty

    def get_active_highway_value(self, tags: Mapping[str, str]) -> str:
        highway = tags.get("highway", "")
        return self.EQUIVALENT_TAGS.get(highway, highway)

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

        restriction = self.get_active_restriction_value(tags)
        kind, _, description = restriction.partition("_")
        # fmt: off
        if (
            kind in ("no", "only")
            and description in ("right_turn", "left_turn", "u_turn", "straight_on")
        ):
            return TurnRestriction.PROHIBITORY if kind == "no" else TurnRestriction.MANDATORY
        # fmt: on

        return TurnRestriction.INAPPLICABLE

    def get_active_restriction_value(self, tags: Mapping[str, str]) -> str:
        active_value = ""
        for mode in self.access:
            key = f"restriction:{mode}" if mode != "access" else "restriction"
            if value := tags.get(key):
                active_value = value
        return active_value

    def is_exempted(self, restriction_tags: Mapping[str, str]) -> bool:
        exempted = restriction_tags.get("except")
        if exempted is None:
            return False
        return any(exempted_type in self.access for exempted_type in exempted.split(";"))


class CarProfile(HighwayProfile):
    """CarProfile is a :py:class:`HighwayProfile` with default parameters which can be used for
    car routing."""

    def __init__(
        self,
        name: Optional[str] = None,
        penalties: Optional[Dict[str, float]] = None,
        access: Optional[List[str]] = None,
    ) -> None:
        super().__init__(
            name=name or "motorcar",
            penalties=penalties
            or {
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
            access=access or ["access", "vehicle", "motor_vehicle", "motorcar"],
        )


class BusProfile(HighwayProfile):
    """BusProfile is a :py:class:`HighwayProfile` with default parameters which can be used for
    bus routing.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        penalties: Optional[Dict[str, float]] = None,
        access: Optional[List[str]] = None,
    ) -> None:
        super().__init__(
            name=name or "bus",
            penalties=penalties
            or {
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
            access=access or ["access", "vehicle", "motor_vehicle", "psv", "bus", "routing:ztm"],
        )


class NonMotorroadHighwayProfile(HighwayProfile):
    """NonMotorroadHighwayProfile is a base class for profiles over highway=* ways,
    for which motorroad=yes implies no access.
    """

    def is_allowed(self, way_tags: Mapping[str, str]) -> bool:
        if way_tags.get("motorroad") == "yes":
            return False
        return super().is_allowed(way_tags)


class BicycleProfile(NonMotorroadHighwayProfile):
    """BicycleProfile is a :py:class:`NonMotorroadHighwayProfile` with default parameters
    which can be used for bicycle routing.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        penalties: Optional[Dict[str, float]] = None,
        access: Optional[List[str]] = None,
    ) -> None:
        super().__init__(
            name=name or "bicycle",
            penalties=penalties
            or {
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
            access=access or ["access", "vehicle", "bicycle"],
        )


class FootProfile(NonMotorroadHighwayProfile):
    """FootProfile is a :py:class:`NonMotorroadHighwayProfile` with default parameters
    which can be used for on-foot routing.

    FootProfile treats several tags differently to :py:class:`HighwayProfile`:

    * ``public_transport=platform`` and ``railway=platform`` are treated as-if ``highway=platform``
    * (TODO) ``oneway`` tags are ignored, unless on ``highway=footway``, ``highway=path``,
        ``highway=steps`` or ``highway=platform``. On other ways,
        only ``oneway:foot`` is considered.
    * Only ``restriction:foot`` turn restrictions are considered.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        penalties: Optional[Dict[str, float]] = None,
        access: Optional[List[str]] = None,
    ) -> None:
        super().__init__(
            name=name or "foot",
            penalties=penalties
            or {
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
                "footway": 1.05,
                "path": 1.05,
                "steps": 1.15,
                "pedestrian": 1.0,
                "platform": 1.1,
            },
            access=access or ["access", "foot"],
        )

    def get_active_highway_value(self, tags: Mapping[str, str]) -> str:
        highway = super().get_active_highway_value(tags)
        if not highway and (
            tags.get("public_transport") == "platform" or tags.get("railway") == "platform"
        ):
            return "platform"
        return highway

    def get_active_restriction_value(self, tags: Mapping[str, str]) -> str:
        return tags.get("restriction:foot", "")
