# ---------------------------------------------------------------------------
# Loading OSM data and doing routing with it
# ---------------------------------------------------------------------------
# Copyright 2007, Oliver White
# Modifications: Copyright 2017-2021, Mikolaj Kuranowski -
# Based on https://github.com/gaulinmp/pyroutelib2
# ---------------------------------------------------------------------------
# This file is part of pyroutelib3.
#
# pyroutelib3 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pyroutelib3 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pyroutelib3. If not, see <http://www.gnu.org/licenses/>.
# ---------------------------------------------------------------------------
# Changelog:
#  2020-10-23  MK   Refactor code
# ---------------------------------------------------------------------------

"""Contains some utility functions used to handle OSM data"""

from typing import Container, Mapping, Sequence, Tuple, List
import math

from .err import OsmInvalidRestriction, OsmReferenceError


# Way processing


def getWayWeight(way: dict, weights: Mapping[str, float]) -> float:
    """Determines the weight of given way. Returns 0 if way shouldn't be traversible."""
    highway_val = way["tag"].get("highway")
    railway_val = way["tag"].get("railway")

    highway_weight = weights.get(highway_val, 0)
    railway_weight = weights.get(railway_val, 0)

    return max(highway_weight, railway_weight)


def getWayAllowed(way: dict, access_tags: Sequence[str]) -> bool:
    """Checks if this way is restricted by access tags."""
    allowed = True

    for tag in access_tags:
        value = way["tag"].get(tag)
        if value is not None:
            if value == "no" or value == "private":
                allowed = False
            else:
                allowed = True

    return allowed


def getWayOneway(way: dict, profile_name: str) -> int:
    """Checks in which direction can this way be traversed.
    For on-foot profiles only "oneway:foot" tags are checked.

    Returns:
    - -1 if way can only be traversed backwards,
    -  0 if way can be traversed both ways,
    -  1 if way can only be traversed forwards.
    """
    oneway = 0

    # on-foot special case
    if profile_name == "foot":
        oneway_val = way["tag"].get("oneway:foot", "")
        if oneway_val in {"yes", "true", "1"}:
            oneway = 1
        elif oneway_val in {"-1", "reverse"}:
            oneway = -1

        return oneway

    # Values used to determine if road is one-way
    oneway_val = way["tag"].get("oneway", "")
    highway_val = way["tag"].get("highway", "")
    junction_val = way["tag"].get("junction", "")

    # Motorways are one-way by default
    if highway_val in {"motorway", "motorway_link"}:
        oneway = 1

    # Roundabouts and circular junctions are one-way by default
    if junction_val in {"roundabout", "circular"}:
        oneway = 1

    # oneway tag present
    if "oneway" in way["tag"]:
        value = way["tag"]["oneway"]
        if value in {"yes", "true", "1"}:
            oneway = 1
        elif value in {"-1", "reverse"}:
            oneway = -1
        elif value in {"no"}:
            oneway = 0

    return oneway


# Relation processing


def _reoderRelNodes(rel_id: int, rel_nodes: List[List[int]]) -> None:
    """Reverses mebers of relation to ensure that rel_nodes[i][-1] == rel_nodes[i + 1][0]"""
    for i in range(len(rel_nodes) - 1):
        # Only reverse rel_nodes[i + 1], so that a sub-list is not reversed twice.
        # The only excpetion is that rel_nodes[0] can be reversed
        # x: rel_nodes[i]
        # y: rel_nodes[i + 1]
        x_first = rel_nodes[i][0]
        x_last = rel_nodes[i][-1]
        y_first = rel_nodes[i + 1][0]
        y_last = rel_nodes[i + 1][-1]

        if x_last == y_first:
            # Sorted
            pass
        elif x_last == y_last:
            rel_nodes[i + 1].reverse()
        elif i == 0 and x_first == y_first:
            rel_nodes[i].reverse()
        elif i == 0 and x_first == y_last:
            rel_nodes[i].reverse()
            rel_nodes[i + 1].reverse()
        else:
            raise OsmInvalidRestriction(f"Restriction {rel_id} is disjoined")

        # Check if after swapping nodes match
        if rel_nodes[i][-1] != rel_nodes[i + 1][0]:
            raise RuntimeError(f"Unable to sort restriction {rel_id}")


def getRelationNodes(
        rel: dict,
        nodes: Container[int],
        ways: Mapping[int, List[int]]) -> List[List[int]]:
    """Parses a turn restriction, given all known nodes and ways.
    Returns a nested list of meber's nodes, sorted:
    that is e.g. [[a, b], [b, c], [c], [c, d, e], [e, f]] (letters represent node ids)
    """
    result: List[List[int]] = []

    froms = [i for i in rel["member"] if i["role"] == "from"]
    vias = [i for i in rel["member"] if i["role"] == "via"]
    tos = [i for i in rel["member"] if i["role"] == "to"]

    # Check the amount & type of members
    if len(froms) != 1:
        raise OsmInvalidRestriction(f"Restriction {rel['id']} has no/multiple from members")

    if froms[0]["type"] != "way":
        raise OsmInvalidRestriction(f"Restriction {rel['id']} from member is not a way")

    if len(tos) != 1:
        raise OsmInvalidRestriction(f"Restriction {rel['id']} has no/multiple to members")

    if tos[0]["type"] != "way":
        raise OsmInvalidRestriction(f"Restriction {rel['id']} to member is not a way")

    # Unpack relation members
    members = [froms[0], *vias, tos[0]]

    # Convert each member to a list of nodes
    while members:
        member = members.pop(0)

        if member["type"] == "node":
            # Check if node exists
            if member["ref"] not in nodes:
                raise OsmReferenceError(f"Restriction {rel['id']} references a "
                                        f"non-existant node {member['ref']}")

            result.append([member["ref"]])

        elif member["type"] == "way":
            # Check if way exists
            if member["ref"] not in ways:
                raise OsmReferenceError(f"Restriction {rel['id']} references a "
                                        f"non-existant way {member['ref']}")

            result.append(ways[member["ref"]].copy())

        else:
            raise OsmInvalidRestriction(f"Restriction {rel['id']} has a member of unexpected type "
                                        f"({member['type']!r})")

    # Order nodes
    _reoderRelNodes(rel["id"], result)
    return result


def getFlatRelNodes(a: Sequence[Sequence[int]]) -> List[int]:
    """Flattens a list of all member's nodes to a list of node ids."""
    result = [a[0][0]]
    previous = a[0][0]

    for sub_a in a:
        for elem in sub_a:
            if elem != previous:
                result.append(elem)
                previous = elem

    return result


# Tile processing
# see https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames


def _mercToLat(x: float) -> float:
    return math.degrees(math.atan(math.sinh(x)))


def getOsmTile(lat: float, lon: float, zoom: int) -> Tuple[int, int]:
    """Determine in which tile the given lat, lon lays"""
    n = 2 ** zoom
    x = n * ((lon + 180) / 360)
    y = n * ((1 - math.log(math.tan(math.radians(lat))
                           + (1 / math.cos(math.radians(lat)))) / math.pi) / 2)
    return int(x), int(y)


def getTileBoundary(x: int, y: int, z: int) -> Tuple[float, float, float, float]:
    """Return (left, bottom, right, top) of bbox of given tile"""
    n = 2 ** z
    top = _mercToLat(math.pi * (1 - 2 * (y * (1 / n))))
    bottom = _mercToLat(math.pi * (1 - 2 * ((y + 1) * (1 / n))))
    left = x * (360 / n) - 180
    right = left + (360 / n)
    return left, bottom, right, top
