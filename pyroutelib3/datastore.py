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

"""Contains the Datastore implementation"""

from urllib.request import urlretrieve
from osmiter import iter_from_osm
from typing_extensions import Literal
from typing import Any, Dict, IO, List, Mapping, Set, Tuple, Union, Optional
from math import inf
import time
import os

from .osmparsing import getWayAllowed, getWayOneway, getWayWeight, \
    getRelationNodes, getFlatRelNodes, getOsmTile, getTileBoundary
from .types import TYPES, TypeDescription, validate_type
from .util import TILES_ZOOM, Position, DistFunction, distHaversine
from .err import InvalidNode, OsmInvalidRestriction, OsmReferenceError, OsmStructureError


class Datastore:
    # Graph data
    rnodes: Dict[int, Position]
    routing: Dict[int, Dict[int, float]]
    mandatoryMoves: Dict[Tuple[int, int], List[int]]
    forbiddenMoves: Dict[Tuple[int, int, int], List[List[int]]]
    distance: DistFunction

    # Profile type
    transport: str
    type: TypeDescription

    # Info about live OSM downloading
    localFile: bool
    tiles: Set[Tuple[int, int]]
    expireData: int
    ignoreDataErrs: bool

    # Init function

    def __init__(
            self,
            transport: Union[str, TypeDescription, Mapping[str, Any]],
            localfile: Union[None, str, bytes, int, IO[bytes]] = None,
            localfileType: Literal['xml', 'gz', 'bz2', 'pbf'] = "xml",
            expireData: int = 30,
            ignoreDataErrs: bool = True,
            distFunction: DistFunction = distHaversine) -> None:
        # Graph data
        self.rnodes = {}
        self.routing = {}
        self.mandatoryMoves = {}
        self.forbiddenMoves = {}
        self.distance = distFunction

        # Profile type
        if isinstance(transport, str):
            self.transport = transport
            self.type = TYPES[transport].copy()
        else:
            self.transport = transport["name"]
            self.type = validate_type(transport)

        # Info about live OSM downloading
        self.localFile = localfile is not None
        self.tiles = set()
        self.expireData = 86400 * expireData
        self.ignoreDataErrs = ignoreDataErrs

        # Load the given osmfile
        if localfile is not None:
            self.loadOsm(localfile, localfileType)

    # Data Loading

    def getArea(self, lat: float, lon: float) -> None:
        """Download data in the vicinity of a position.
        No-op if `self.localFile`."""
        # Don't download data if we loaded a custom OSM file
        if self.localFile:
            return

        # Get info on tile in wich lat, lon lays
        x, y = getOsmTile(lat, lon, TILES_ZOOM)

        # Don't redownload tiles
        if (x, y) in self.tiles:
            return

        # Download tile data
        self.tiles.add((x, y))
        directory = os.path.join("tilescache", str(TILES_ZOOM), str(x), str(y))
        filename = os.path.join(directory, "data.osm")

        # Make sure directory to which we download .osm files exists
        if not os.path.exists(directory):
            os.makedirs(directory)

        # In versions prior to 1.0 tiles were saved to tilescache/z/x/y/data.osm.pkl
        elif os.path.exists(filename + ".pkl"):
            os.rename(filename + ".pkl", filename)

        # Don't redownload data from pre-expire date
        try:
            downloadedSecondsAgo = time.time() - os.path.getmtime(filename)
        except OSError:
            downloadedSecondsAgo = inf

        if downloadedSecondsAgo >= self.expireData:
            left, bottom, right, top = getTileBoundary(x, y, TILES_ZOOM)

            urlretrieve(
                f"https://api.openstreetmap.org/api/0.6/map?bbox={left},{bottom},{right},{top}",
                filename
            )

        self.loadOsm(filename, "xml")

    def loadOsm(self, osm_file: Union[str, bytes, int, IO[bytes]],
                osm_file_format: Literal['xml', 'gz', 'bz2', 'pbf'] = "xml") -> None:
        """Parses provided osm file and saves routing data."""
        encounteredNodes: Dict[int, Position] = {}
        usedWays: Dict[int, List[int]] = {}

        for feature in iter_from_osm(osm_file, osm_file_format, set()):
            if feature["type"] == "node":
                # N O D E
                # Save position, if it's used by some way, it'll be saved to the Datastore
                encounteredNodes[feature["id"]] = feature["lat"], feature["lon"]

            elif feature["type"] == "way":
                # W A Y
                # Pass it to self.store_way; if it was stored:
                # store un-saved node positions
                # and cache way["nd"] for relation parsing
                stored = self.storeWay(feature, encounteredNodes)
                if stored:
                    usedWays[feature["id"]] = feature["nd"]

                    for nd in filter(lambda i: i not in self.rnodes, feature["nd"]):
                        self.rnodes[nd] = encounteredNodes[nd]

            elif feature["type"] == "relation":
                # R E L A T I O N
                # Check if it's a turn restriction and process it
                # Ignore non-restrictions
                if feature["tag"].get("type") not in {"restriction",
                                                      "restriction:" + self.transport}:
                    continue

                # Store this restriction
                try:
                    self.storeRestriction(feature, usedWays)
                except (OsmReferenceError, OsmInvalidRestriction):
                    if self.ignoreDataErrs:
                        continue
                    else:
                        raise

            else:
                raise OsmStructureError(f"Unexpected feature type: {feature['type']!r} "
                                        f"on feature with id {feature['id']!r}")

    def storeWay(self, way: dict, knownNodes: Dict[int, Any]) -> bool:
        """Parses an OSM way and saves routing data derived from this way."""
        def getNodePos(nodeId: int) -> Optional[Position]:
            "Gets position of node with given ID, or None if node doesn't exist"
            if nodeId in self.rnodes:
                return self.rnodes[nodeId]
            elif nodeId in knownNodes:
                return knownNodes[nodeId]
        # Simplify tags
        if "highway" in way["tag"]:
            way["tag"]["highway"] = self.equivalent(way["tag"]["highway"])
        if "railway" in way["tag"]:
            way["tag"]["railway"] = self.equivalent(way["tag"]["railway"])

        # Info about weight
        weight = getWayWeight(way, self.type["weights"])
        allowed = getWayAllowed(way, self.type["access"])

        if weight <= 0 or not allowed:
            return False

        oneway = getWayOneway(way, self.transport)

        # Iterate over each edge (pair of nodes) in this way
        for node1Id, node2Id in zip(way["nd"][:-1], way["nd"][1:]):
            # Assume both nodes exist
            node1Pos = getNodePos(node1Id)
            node2Pos = getNodePos(node2Id)

            if node1Pos is None:
                raise OsmReferenceError(f"Way {way['id']} referenced invalid node: {node1Id}")

            if node2Pos is None:
                raise OsmReferenceError(f"Way {way['id']} referenced invalid node: {node2Id}")

            # Calculate cost of this edge
            cost = self.distance(node1Pos, node2Pos) / weight

            # Is the way traversible forward?
            if oneway >= 0:
                self.routing.setdefault(node1Id, {})[node2Id] = cost

            # Is the way traversible backwards?
            if oneway <= 0:
                self.routing.setdefault(node2Id, {})[node1Id] = cost

        return True

    def storeRestriction(self, rel: dict, usedWays: Dict[int, List[int]]) -> bool:
        """Parses an OSM restriction and saves restriction data derived from this relation."""
        # Ignore restriction if on-foot, except when explicilty stated
        if self.transport == "foot" \
                and rel["tag"].get("type") != "restriction:foot" \
                and "restriction:foot" not in rel["tag"]:
            return False

        # Ignore restriction if any of names in 'except' applies to current profile
        if set(rel["tag"].get("except", "").split(";")) \
                .intersection(self.type["access"]):
            return False

        # Get the list of nodes of this relation
        relNodes = getRelationNodes(rel, self.rnodes.keys(), usedWays)

        # Get the restriction type
        restrType = rel["tag"].get("restriction:" + self.transport) \
            or rel["tag"].get("restriction")

        if restrType is None:
            raise OsmInvalidRestriction(
                f"Relation with id={rel['id']} and type={rel['tag']['type']!r} "
                f"has no matching 'restriction'/"
                f"'{'restriction' + self.transport!r} tag!")

        if restrType.startswith("no_"):
            self.storeRestrictionForbidden(rel["id"], relNodes)
        elif restrType.startswith("only_"):
            self.storeRestrictionMandatory(rel["id"], relNodes)
        else:
            raise OsmInvalidRestriction(f"Invalid restriction type of {rel['id']}: "
                                        f"({restrType!r})")

        return True

    def storeRestrictionForbidden(self, relId: int, relNodes: List[List[int]]):
        """Saves a forbiddenMove from the list of relation nodes."""
        # Ignore the beggining of the "from" member: only last 2 members are important
        relNodes[0] = relNodes[0][-2:]

        # Ignore the end of the "to" member: only first 2 members are important
        relNodes[-1] = relNodes[-1][:2]

        # Flatten the member list
        flatNodes = getFlatRelNodes(relNodes)
        if len(flatNodes) < 3:
            raise OsmInvalidRestriction(f"Too short restriction {relId}")

        # Create a hash of this relation: last 3 nodes
        forbidingHash = flatNodes[-3], flatNodes[-2], flatNodes[-1]

        # Store the whole forbidden move under its hash
        self.forbiddenMoves.setdefault(forbidingHash, []).append(flatNodes)

    def storeRestrictionMandatory(self, relId: int, relNodes: List[List[int]]):
        """Saves a mandatoryMove from the list of relation nodes."""
        # The mandatory move starts when route includes this pair of nodes (in order ofc)
        forceActivator = relNodes[0][-2], relNodes[0][-1]

        # Check against activator collisions
        if forceActivator in self.mandatoryMoves:
            raise OsmInvalidRestriction("Multiple only_* restrictions activate with "
                                        f"{forceActivator} (one of which is {relId})")

        # Add all nodes that must follow the activator.
        # First: add all 'via' members, ignoring the first node to aviod duplicates
        forceNodes = []
        for viaMember in relNodes[1:-1]:
            forceNodes.extend(viaMember[1:])

        # Add first node of 'to' after traversing all 'via' members
        forceNodes.append(relNodes[-1][1])

        # Save this mandatory move
        self.mandatoryMoves[forceActivator] = forceNodes

    # Simple processing of data

    @staticmethod
    def equivalent(tag: str) -> str:
        """Simplifies a bunch of tags to nearly-equivalent ones"""
        return {
            "motorway_link": "motorway",
            "trunk_link": "trunk",
            "primary_link": "primary",
            "secondary_link": "secondary",
            "tertiary_link": "tertiary",
            "minor": "unclassified",
            "pedestrian": "footway",
            "platform": "footway",
        }.get(tag, tag)

    def findNode(self, lat: float, lon: float) -> int:
        """Perform a naive nearest-neighbour search.
        It has _really_ poor performance on bigger grpahs, because of its O(n) complexity."""
        # Retrieve area around search root
        self.getArea(lat, lon)

        # Naive NN search
        bestId = -1
        bestDist = inf

        if len(self.rnodes) <= 0:
            raise KeyError("findNode in an empty space")

        for nodeId, nodePos in self.rnodes.items():
            nodeDist = self.distance((lat, lon), nodePos)
            if nodeDist < bestDist:
                bestId = nodeId
                bestDist = nodeDist

        return bestId

    def nodeLatLon(self, node: int) -> Position:
        """Returns position of a node with a given id.
        Raises InvalidNode if node is not loaded."""
        pos = self.rnodes.get(node)
        if pos is None:
            raise InvalidNode(f"no such node: {node}")
        else:
            return pos

    def report(self):
        """Display some info about the loaded data"""
        edges = sum(len(i) for i in self.routing.values())
        print(f"Loaded {len(self.rnodes)} nodes")
        print(f"Loaded {edges} {self.transport} edges")
