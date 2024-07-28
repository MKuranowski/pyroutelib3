# © Copyright 2024 Mikołaj Kuranowski
# SPDX-License-Identifier: GPL-3.0-or-later

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
        """way_penalty returns the penalty of using this way,
        by looking up the return value of :py:meth:`get_active_highway_value`
        in :py:attr:`penalties`, unless :py:meth:`is_allowed` return False.
        """
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
        """get_active_highway_value gets the string to lookup in :py:attr:`penalties` -
        the value of the "highway" tag, normalized through :py:obj:`EQUIVALENT_TAGS`.
        """
        highway = tags.get("highway", "")
        return self.EQUIVALENT_TAGS.get(highway, highway)

    def is_allowed(self, way_tags: Mapping[str, str]) -> bool:
        """is_allowed checks if a way is allowed, as per the
        `access tags <https://wiki.openstreetmap.org/wiki/Key:access>`_ and the hierarchy
        defined in :py:attr:`access`. Only values of "no" and "private" can exclude a way,
        any other value (even "destination" or "permit") is assumed to allow a way to be used.
        """
        for access_tag in reversed(self.access):
            value = way_tags.get(access_tag)
            if value in ("no", "private"):
                return False
            elif value is not None:
                return True
        return True

    def way_direction(self, way_tags: Mapping[str, str]) -> Tuple[bool, bool]:
        """way_direction returns the direction of travel of the provided way.
        Apart from considering the oneway tag (as returned by :py:meth:`get_active_oneway_value`),
        ``highway=motorway``, ``highway=motorway_link``, ``junction=roundabout`` and
        ``junction=circular`` default to being oneway.
        """

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
        oneway = self.get_active_oneway_value(way_tags)
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

    def get_active_oneway_value(self, tags: Mapping[str, str]) -> str:
        """get_active_oneway_value returns the most specific "oneway:MODE" tag,
        falling back to "oneway" - to use when checking way directionality.
        """
        for mode in reversed(self.access):
            if mode != "access" and (value := tags.get(f"oneway:{mode}")):
                return value
        return tags.get("oneway", "")

    def is_turn_restriction(self, tags: Mapping[str, str]) -> TurnRestriction:
        """is_turn_restriction checks relation tags to determine what kind of
        :py:class:`TurnRestriction` this is. The relation must have a "type=restriction"
        tag, however, the restriction type may be under "restriction" or "restriction:MODE"
        keys (see :py:meth:`get_active_restriction_value`), and :py:meth:`is_exempted` must
        return False. Only only/no right_turn/left_turn/u_turn/straight_on restrictions
        are accepted.
        """

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
        """get_active_restriction_value returns the most specific "restriction:MODE" tag,
        falling back to "restriction" - to use when checking turn restriction type.
        """
        for mode in reversed(self.access):
            if mode != "access" and (value := tags.get(f"restriction:{mode}")):
                return value
        return tags.get("restriction", "")

    def is_exempted(self, restriction_tags: Mapping[str, str]) -> bool:
        """is_exempted returns ``True`` if any of the transportation modes
        under the ``except`` tag are present in :py:attr:`access`.
        """
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
    * ``oneway`` tags are ignored, unless on ``highway=footway``, ``highway=path``,
        ``highway=steps`` or ``highway=platform``. On other ways, only ``oneway:foot`` is used.
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

    def get_active_oneway_value(self, tags: Mapping[str, str]) -> str:
        active_value = ""
        if self.get_active_highway_value(tags) in ("footway", "path", "steps", "platform"):
            active_value = tags.get("oneway", "")
        if value := tags.get("oneway:foot", ""):
            active_value = value
        return active_value

    def get_active_restriction_value(self, tags: Mapping[str, str]) -> str:
        return tags.get("restriction:foot", "")


@dataclass
class RailwayProfile:
    """RailwayProfile implements :py:class:`Profile` for routing over railway=* ways.

    Only ``access=no`` or ``access=private`` can prevent a way from being excluded from the graph.
    There are no default one ways, and only ``oneway`` values of ``yes`` and ``-1`` are accepted.
    All ``type=restriction`` with ``restriction`` tag set to only/no
    right_turn/left_turn/u_turn/straight_on are passed through.

    ``RailwayProfile()`` can be used as a profile for routing over ``railway=rail``, ``light_rail``,
    ``subway`` and ``narrow_gauge``.
    """

    name: str = "railway"

    penalties: Dict[str, float] = field(
        default_factory=lambda: {
            "rail": 1.0,
            "light_rail": 1.0,
            "subway": 1.0,
            "narrow_gauge": 1.0,
        },
        repr=False,
    )

    def way_penalty(self, tags: Mapping[str, str]) -> Optional[float]:
        if tags.get("access") in ("no", "private"):
            return None
        return self.penalties.get(tags.get("railway", ""))

    def way_direction(self, tags: Mapping[str, str]) -> Tuple[bool, bool]:
        oneway = tags.get("oneway")
        if oneway == "yes":
            return True, False
        elif oneway == "-1":
            return False, True
        return True, True

    def is_turn_restriction(self, tags: Mapping[str, str]) -> TurnRestriction:
        kind, _, description = tags.get("restriction", "").partition("_")
        if (
            tags.get("type") == "restriction"
            and kind in ("no", "only")
            and description in ("right_turn", "left_turn", "u_turn", "straight_on")
        ):
            return TurnRestriction.PROHIBITORY if kind == "no" else TurnRestriction.MANDATORY
        return TurnRestriction.INAPPLICABLE


class TramProfile(RailwayProfile):
    """TramProfile is a :py:class:`RailwayProfile` which allows routing only over
    ``railway=tram`` or ``light_rail`` ways.
    """

    def __init__(self) -> None:
        super().__init__("tram", {"tram": 1.0, "light_rail": 1.0})


class SubwayProfile(RailwayProfile):
    """SubwayProfile is a :py:class:`RailwayProfile` which allows routing only over
    ``railway=subway`` ways.
    """

    def __init__(self) -> None:
        super().__init__("subway", {"subway": 1.0})
