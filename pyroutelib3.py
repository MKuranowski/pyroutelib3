#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# Loading OSM data and doing routing with it
# ---------------------------------------------------------------------------
# Copyright 2007, Oliver White
# Modifications: Copyright 2017-2020, Mikolaj Kuranowski -
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
#  2007-11-04  OJW  Modified from pyroute.py
#  2007-11-05  OJW  Multiple forms of transport
#  2017-09-24  MK   Code cleanup
#  2017-09-30  MK   LocalFile - Only router
#  2017-10-11  MK   Access keys
#  2018-01-07  MK   Oneway:<Transport> tags & New distance function
#  2018-08-14  MK   Turn restrictions
#  2018-08-18  MK   New data download function
#  2019-09-15  MK   Allow for custom storage classes, instead of default dict
#  2020-02-14  MK   Use osmiter for data parsing to allow more file types
#  2020-05-08  MK   Make use of hashing in turn restriction handling
#  2020-05-11  MK   Decouple _AddToQueue from doRoute
# ---------------------------------------------------------------------------
from urllib.request import urlretrieve
from collections import OrderedDict
import osmiter
import math
import time
import os

__title__ = "pyroutelib3"
__description__ = "Library for simple routing on OSM data"
__url__ = "https://github.com/MKuranowski/pyroutelib3"
__author__ = "Oliver White"
__copyright__ = "Copyright 2007, Oliver White; " \
                "Modifications: Copyright 2017-2020, Mikolaj Kuranowski"
__credits__ = ["Oliver White", "Mikolaj Kuranowski"]
__license__ = "GPL v3"
__version__ = "1.6.3"
__maintainer__ = "Mikolaj Kuranowski"
__email__ = "".join(chr(i) for i in [109, 107, 117, 114, 97, 110, 111, 119, 115, 107, 105, 64,
                                     103, 109, 97, 105, 108, 46, 99, 111, 109])


TYPES = {
    "car": {
        "weights": {
            "motorway": 10, "trunk": 10, "primary": 2, "secondary": 1.5, "tertiary": 1,
            "unclassified": 1, "residential": 0.7, "living_street": 0.5, "track": 0.5,
            "service": 0.5,
        },
        "access": ["access", "vehicle", "motor_vehicle", "motorcar"]},
    "bus": {
        "weights": {
            "motorway": 10, "trunk": 10, "primary": 2, "secondary": 1.5, "tertiary": 1,
            "unclassified": 1, "residential": 0.8, "track": 0.3, "service": 0.9,
        },
        "access": ["access", "vehicle", "motor_vehicle", "psv", "bus"]},
    "cycle": {
        "weights": {
            "trunk": 0.05, "primary": 0.3, "secondary": 0.9, "tertiary": 1,
            "unclassified": 1, "cycleway": 2, "residential": 2.5, "living_street": 1,
            "track": 1, "service": 1, "bridleway": 0.8, "footway": 0.8, "steps": 0.5, "path": 1,
        },
        "access": ["access", "vehicle", "bicycle"]},
    "horse": {
        "weights": {
            "primary": 0.05, "secondary": 0.15, "tertiary": 0.3, "unclassified": 1,
            "residential": 1, "living_street": 1, "track": 1.5, "service": 1,
            "bridleway": 5, "path": 1.5,
        },
        "access": ["access", "horse"]},
    "foot": {
        "weights": {
            "trunk": 0.3, "primary": 0.6, "secondary": 0.95, "tertiary": 1,
            "unclassified": 1, "residential": 1, "living_street": 1, "track": 1, "service": 1,
            "bridleway": 1, "footway": 1.2, "path": 1.2, "steps": 1.15,
        },
        "access": ["access", "foot"]},
    "tram": {
        "weights": {"tram": 1, "light_rail": 1},
        "access": ["access"]},
    "train": {
        "weights": {"rail": 1, "light_rail": 1, "subway": 1, "narrow_guage": 1},
        "access": ["access"]}
}

def _whichTile(lat, lon, zoom):
    """Determine in which tile the given lat, lon lays"""
    n = 2 ** zoom
    x = n * ((lon + 180) / 360)
    y = n * ((1 - math.log(math.tan(math.radians(lat))
                           + (1 / math.cos(math.radians(lat)))) / math.pi) / 2)
    return int(x), int(y)

def _marcToLat(x):
    return math.degrees(math.atan(math.sinh(x)))

def _tileBoundary(x, y, z):
    """Return (left, bottom, right, top) of bbox of given tile"""
    n = 2 ** z
    top = _marcToLat(math.pi * (1 - 2 * (y * (1 / n))))
    bottom = _marcToLat(math.pi * (1 - 2 * ((y + 1) * (1 / n))))
    left = x * (360 / n) - 180
    right = left + (360 / n)
    return left, bottom, right, top

def _flatternAndRemoveDupes(x):
    result = []
    prev = None
    for subx in x:
        for item in subx:
            if item != prev:
                prev = item
                result.append(item)
    return result

class Datastore:
    """Object for storing routing data"""
    def __init__(self, transport, localfile=False, localfileType="xml",
                 expire_data=30, storage_class=dict, ignoreDataErrs=True):
        """Initialise an OSM-file parser"""
        # Routing data
        self.routing = storage_class()
        self.rnodes = storage_class()
        self.mandatoryMoves = storage_class()
        self.forbiddenMoves = storage_class()

        # Info about OSM
        self.tiles = storage_class()
        self.expire_data = 86400 * expire_data  # expire_data is in days, we need seconds
        self.localFile = bool(localfile)
        self.ignoreDataErrs = ignoreDataErrs

        # verify localFileType
        if localfileType not in {"xml", "gz", "bz2", "pbf"}:
            raise ValueError("localfileType must be 'xml', 'gz', 'bz2' or 'pbf', "
                             f"not {localfileType!r}")

        # Parsing/Storage data
        self.storage_class = storage_class

        # Dict-type custom transport weights
        if isinstance(transport, dict):
            # Check if required info is in given transport dict
            if not {"name", "access", "weights"}.issubset(transport.keys()):
                raise ValueError("custom transport dict is missing required keys")

            self.transport = transport["name"]
            self.type = transport

        else:
            # OSM uses bicycle in tags, pyroutelib used "cycle"
            self.transport = transport if transport != "cycle" else "bicycle"
            self.type = TYPES[transport].copy()

        # Save the maximum weight
        self._maxWeight = max(self.type["weights"].values())

        # Load local file if it was passed
        if self.localFile:
            self.loadOsm(localfile, localfileType)

    def _allowedVehicle(self, tags):
        """Check way against access tags"""
        # Default to true
        allowed = True

        # Priority is ascending in the access array
        for key in self.type["access"]:
            if key in tags:
                if tags[key] in {"no", "private"}:
                    allowed = False
                else:
                    allowed = True

        return allowed

    @staticmethod
    def distance(n1, n2):
        """Calculate distance in km between two nodes using haversine forumla"""
        lat1, lon1 = map(math.radians, n1)
        lat2, lon2 = map(math.radians, n2)
        dlathalf = (lat2 - lat1) * 0.5
        dlonhalf = (lon2 - lon1) * 0.5

        sqrth = math.sqrt(
            (math.sin(dlathalf) ** 2)
            + (math.cos(lat1) * math.cos(lat2) * (math.sin(dlonhalf) ** 2))
        )

        return math.asin(sqrth) * 2 * 6371

    def nodeLatLon(self, node):
        """Get node's lat lon"""
        return self.rnodes[node]

    def getArea(self, lat, lon):
        """Download data in the vicinity of a lat/long"""
        # Don't download data if we loaded a custom OSM file
        if self.localFile:
            return

        # Get info on tile in wich lat, lon lays
        x, y = _whichTile(lat, lon, 15)
        tileId = f"{x},{y}"

        # Don't redownload tiles
        if tileId in self.tiles:
            return

        # Download tile data
        self.tiles[tileId] = True
        directory = os.path.join("tilescache", "15", str(x), str(y))
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
            downloadedSecondsAgo = math.inf

        if downloadedSecondsAgo >= self.expire_data:
            left, bottom, right, top = _tileBoundary(x, y, 15)

            urlretrieve(
                f"https://api.openstreetmap.org/api/0.6/map?bbox={left},{bottom},{right},{top}",
                filename
            )

        self.loadOsm(filename, "xml")

    def parseOsmFile(self, file, filetype):
        """Return nodes, ways and realations of given file
           Only highway=* and railway=* ways are returned, and
           only type=restriction (and type=restriction:<transport type>) are returned"""
        nodes = self.storage_class()
        ways = self.storage_class()
        relations = self.storage_class()

        for elem in osmiter.iter_from_osm(file, filetype):

            if elem["type"] == "node":
                nodes[elem["id"]] = elem

            # Store only potentially routable ways
            elif elem["type"] == "way" \
                    and (elem["tag"].get("highway") or elem["tag"].get("railway")):
                ways[elem["id"]] = elem

            # Store only potential turn restrictions
            elif elem["type"] == "relation" \
                    and elem["tag"].get("type", "").startswith("restriction"):
                relations[elem["id"]] = elem

        return nodes, ways, relations

    def loadOsm(self, file, filetype="xml"):
        """Load data from OSM file to self"""
        nodes, ways, relations = self.parseOsmFile(file, filetype)

        for wayId, wayData in ways.items():
            wayNodes = []
            for nd in wayData["nd"]:

                if nd not in nodes:
                    continue

                wayNodes.append((nodes[nd]["id"], nodes[nd]["lat"], nodes[nd]["lon"]))

            self.storeWay(wayId, wayData["tag"], wayNodes)

        for relId, relData in relations.items():
            try:
                # Ignore reltions which are not restrictions
                if relData["tag"].get("type") not in {"restriction",
                                                      "restriction:" + self.transport}:
                    continue

                # Ignore restriction if except tag points to any "access" values
                relation_except = set(relData["tag"].get("except", "").split(";"))
                if relation_except.intersection(self.type["access"]):
                    continue

                # Ignore restrictions if on foot, unless explicitly stated in restriction
                if self.transport == "foot" \
                        and relData["tag"].get("type") != "restriction:foot" \
                        and "restriction:foot" not in relData["tag"]:
                    continue

                restrictionType = relData["tag"].get("restriction:" + self.transport,
                                                     relData["tag"]["restriction"])

                nodes = []
                fromMember = [i for i in relData["member"] if i["role"] == "from"][0]
                toMember = [i for i in relData["member"] if i["role"] == "to"][0]

                for viaMember in [i for i in relData["member"] if i["role"] == "via"]:
                    if viaMember["type"] == "way":
                        nodes.append(ways[int(viaMember["ref"])]["nd"])
                    else:
                        nodes.append([int(viaMember["ref"])])

                nodes.insert(0, ways[int(fromMember["ref"])]["nd"])
                nodes.append(ways[int(toMember["ref"])]["nd"])

                self.storeRestriction(relId, restrictionType, nodes)

            except (KeyError, AssertionError, IndexError, ValueError):
                if self.ignoreDataErrs:
                    continue
                else:
                    raise

    def storeRestriction(self, relId, restrictionType, members):
        # Order members of restriction
        # Members should look somewhat like this: ([a, b], [b, c], [c], [c, d, e], [e, f])
        for x in range(len(members) - 1):
            commonNode = (set(members[x]).intersection(set(members[x + 1]))).pop()

            # If first node of member[x+1] is different then common_node, try to reverse it
            if members[x + 1][0] != commonNode:
                members[x + 1].reverse()

            # Only the "from" way can be reversed while ordering the nodes,
            # Otherwise, the x way could be reversed twice (as member[x] and member[x+1])
            if x == 0 and members[x][-1] != commonNode:
                members[x].reverse()

            # Assume member[x] and member[x+1] are ordered correctly
            if members[x][-1] != members[x + 1][0]:
                raise ValueError(f"unable to order restriction {relId}")

        if restrictionType.startswith("no_"):
            # Convert all memebers into one list
            flatMembers = _flatternAndRemoveDupes(members)

            if len(flatMembers) < 3:
                raise ValueError(f"invalid turn restriction {relId}")

            # Create a hash for faster checking
            forbidHash = tuple(flatMembers[-3:])

            if forbidHash in self.forbiddenMoves:
                self.forbiddenMoves[forbidHash].append(flatMembers)
            else:
                self.forbiddenMoves[forbidHash] = [flatMembers]

        elif restrictionType.startswith("only_"):
            force = []
            forceActivator = (members[0][-2], members[1][0])

            # Add all via members
            for x in range(1, len(members) - 1):
                for i in members[x][1:]:
                    force.append(i)

            # Finalize by denoting 'via>to'
            force.append(members[-1][1])

            self.mandatoryMoves[forceActivator] = force

    def storeWay(self, wayId, tags, nodes):
        highway = self.equivalent(tags.get("highway", ""))
        railway = self.equivalent(tags.get("railway", ""))
        oneway = tags.get("oneway", "")

        # Oneway is default on roundabouts
        if not oneway and (tags.get("junction", "") in {"roundabout", "circular"}
                           or highway == "motorway"):
            oneway = "yes"

        if self.transport == "foot" or (oneway in {"yes", "true", "1", "-1"}
                                        and tags.get("oneway:" + self.transport, "yes") == "no"):
            oneway = "no"

        # Calculate what vehicles can use this route
        weight = self.type["weights"].get(highway, 0) or self.type["weights"].get(railway, 0)

        # Check against access tags
        if (not self._allowedVehicle(tags)) or weight <= 0:
            return

        # Store routing information
        for index in range(1, len(nodes)):
            node1Id, node1Pos = nodes[index - 1][0], nodes[index - 1][1:]
            node2Id, node2Pos = nodes[index][0], nodes[index][1:]

            # Check if nodes' positions are stored
            if node1Id not in self.rnodes:
                self.rnodes[node1Id] = node1Pos

            if node2Id not in self.rnodes:
                self.rnodes[node2Id] = node2Pos

            # Calculate the cost of this edge
            dist = self.distance(node1Pos, node2Pos)
            cost = dist / weight

            # Check if nodes have dicts for storing travel costs
            if node1Id not in self.routing:
                self.routing[node1Id] = {}

            if node2Id not in self.routing:
                self.routing[node2Id] = {}

            # Is way traversible forward?
            if oneway not in {"-1", "reverse"}:
                self.routing[node1Id][node2Id] = cost

            # Is way traversible backword?
            if oneway not in {"yes", "true", "1"}:
                self.routing[node2Id][node1Id] = cost

    @staticmethod
    def equivalent(tag):
        """Simplifies a bunch of tags to nearly-equivalent ones"""
        equivalent = {
            "motorway_link": "motorway",
            "trunk_link": "trunk",
            "primary_link": "primary",
            "secondary_link": "secondary",
            "tertiary_link": "tertiary",
            "minor": "unclassified",
            "pedestrian": "footway",
            "platform": "footway",
        }
        return equivalent.get(tag, tag)

    def findNode(self, lat, lon):
        """Find the nearest node that can be the start of a route"""
        # Get area around location we're trying to find
        self.getArea(lat, lon)
        maxDist, closestNode = math.inf, None

        # Iterate over nodes and overwrite closest_node if it's closer
        # TODO: K-D trees?
        for nodeId, nodePos in self.rnodes.items():
            distanceDiff = self.distance(nodePos, (lat, lon))
            if distanceDiff < maxDist:
                maxDist = distanceDiff
                closestNode = nodeId

        return closestNode

    def report(self):
        """Display some info about the loaded data"""
        edges = sum(len(i) for i in self.routing.values())
        print(f"Loaded {len(self.rnodes)} nodes")
        print(f"Loaded {edges} {self.transport} edges")

class Router(Datastore):

    def clearVariables(self):
        self.queue = []
        self.costTo = {}
        self.endPos = None

    def addToQueue(self, fromNode, toNode, cost, prevItem):
        # Check if route is traversible
        if cost == 0:
            return

        # Don't turn around at a node (no a-b-a)
        if len(prevItem["route"]) >= 2 and prevItem["route"][-2] == toNode:
            return

        # Check if we comply with mandatory moves
        if "forceNext" in prevItem and prevItem["forceNext"][0] != toNode:
            return

        # Ger fromNode and toNode position
        fromPos = self.rnodes.get(fromNode)
        toPos = self.rnodes.get(toNode)

        # Assume both fromNode and toNode exist
        if fromPos is None or toPos is None:
            return

        # Get data around toNode
        self.getArea(*toPos)

        # Gather some data on the added queue item
        route = prevItem["route"] + [toNode]
        totalCost = prevItem["totalCost"] + cost
        heuristicCost = totalCost + self.distance(toPos, self.endPos)

        # Check if we have a cheaper way of getting to toNode
        if self.costTo.get(toNode, math.inf) < totalCost:
            return

        # Check if we don't run into a restriction
        if len(route) >= 3:
            forbidHash = tuple(route[-3:])

            for restriction in self.forbiddenMoves.get(forbidHash, []):
                # If route is shorter then restriction, move to next check
                if len(restriction) > len(route):
                    continue

                # If route ends with restriction → don't add this edge
                if route[-len(restriction):] == restriction:
                    return

        # Check for mandatory moves
        if "forceNext" in prevItem and len(prevItem["forceNext"]) > 1:
            forceNext = prevItem["forceNext"][1:]

        else:
            mandatoryActivator = tuple(route[-2:])
            forceNext = self.mandatoryMoves.get(mandatoryActivator)

        # Gather all important data into a dict
        nextItem = {
            "id": toNode,
            "route": route,
            "totalCost": totalCost,
            "heuristicCost": heuristicCost,
        }

        if forceNext is not None:
            nextItem["forceNext"] = forceNext

        # Set the cost to toNode
        self.costTo[toNode] = totalCost

        # Insert nextItem while keeping the queue ordered by decreasing heuristic cost
        for count, test in enumerate(self.queue):
            if test["heuristicCost"] > heuristicCost:
                self.queue.insert(count, nextItem)
                break
        else:
            self.queue.append(nextItem)

    def doRoute(self, start, end):
        self.clearVariables()

        # Assume start and end exist
        if start not in self.routing or start not in self.rnodes:
            raise KeyError(f"start node {start} doesn't exist in the graph")

        elif end not in self.rnodes:
            raise KeyError(f"end node {start} doesn't exist in the graph")

        elif start == end:
            return "no_route", []

        # Save the end position
        self.endPos = self.rnodes[end]

        # Add the start node
        self.costTo[start] = 0
        self.queue.append({
            "id": start,
            "route": [start],
            "totalCost": 0,
            "heuristicCost": self.distance(self.rnodes[start], self.endPos)
        })

        # Limit search time
        count = 0
        while count < 1_000_000:
            count += 1

            # Get an item from the queue
            try:
                considered = self.queue.pop(0)
            except IndexError:
                self.clearVariables()
                return "no_route", []

            # Check if we arrived at the end
            if considered["id"] == end:
                self.clearVariables()
                return "success", considered["route"]

            # Add all edges originating from considered queue item
            for neighbor, cost in self.routing.get(considered["id"], {}).items():
                self.addToQueue(considered["id"], neighbor, cost, considered)

        self.clearVariables()
        return "gave_up", []
