#!/usr/bin/env python3
#----------------------------------------------------------------------------
# Loading OSM data and doing routing with it
# node_lat, node_lon = Router().data.rnodes[node_id][0], Router().data.rnodes[node_id][1]
#----------------------------------------------------------------------------
# Copyright 2007, Oliver White
# Modifications: Copyright 2017, Mikolaj Kuranowski -
# Based on https://github.com/gaulinmp/pyroutelib2
#----------------------------------------------------------------------------
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
#----------------------------------------------------------------------------
# Changelog:
#  2007-11-04  OJW  Modified from pyroute.py
#  2007-11-05  OJW  Multiple forms of transport
#  2017-09-24  MK   Code cleanup
#  2017-09-30  MK   LocalFile - Only router
#  2017-10-11  MK   Access keys
#  2018-01-07  MK   Oneway:<Transport> tags & New distance function
#  2018-08-14  MK   Turn restrictions
#  2018-08-18  MK   New data download function
#----------------------------------------------------------------------------
import os
import re
import sys
import math
import time
import dateutil.parser
import xml.etree.ElementTree as etree
from warnings import warn
from datetime import datetime
from collections import OrderedDict
from urllib.request import urlretrieve

__title__ = "pyroutelib3"
__description__ = "Library for simple routing on OSM data"
__url__ = "https://github.com/MKuranowski/pyroutelib3"
__author__ = "Oliver White"
__copyright__ = "Copyright 2007, Oliver White; Modifications: Copyright 2017-2018, Mikolaj Kuranowski"
__credits__ = ["Oliver White", "Mikolaj Kuranowski"]
__license__ = "GPL v3"
__version__ = "1.2"
__maintainer__ = "Mikolaj Kuranowski"
__email__ = "mkuranowski@gmail.com"


TYPES = {
    "car": {
        "weights": {"motorway": 10, "trunk": 10, "primary": 2, "secondary": 1.5, "tertiary": 1,
            "unclassified": 1, "residential": 0.7, "track": 0.5, "service": 0.5},
        "access": ["access", "vehicle", "motor_vehicle", "motorcar"]},
    "bus": {
        "weights": {"motorway": 10, "trunk": 10, "primary": 2, "secondary": 1.5, "tertiary": 1,
            "unclassified": 1, "residential": 0.8, "track": 0.3, "service": 0.9},
        "access": ["access", "vehicle", "motor_vehicle", "psv", "bus"]},
    "cycle": {
        "weights": {"trunk": 0.05, "primary": 0.3, "secondary": 0.9, "tertiary": 1,
            "unclassified": 1, "cycleway": 2, "residential": 2.5, "track": 1,
            "service": 1, "bridleway": 0.8, "footway": 0.8, "steps": 0.5, "path": 1},
        "access": ["access", "vehicle", "bicycle"]},
    "horse": {
        "weights": {"primary": 0.05, "secondary": 0.15, "tertiary": 0.3, "unclassified": 1, \
        "residential": 1, "track": 1.5, "service": 1, "bridleway": 5, "path": 1.5},
        "access": ["access", "horse"]},
    "foot": {
        "weights": {"trunk": 0.3, "primary": 0.6, "secondary": 0.95, "tertiary": 1,
            "unclassified": 1, "residential": 1, "track": 1, "service": 1,
            "bridleway": 1, "footway": 1.2, "path": 1.2, "steps": 1.15},
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
    y = n * ((1 - math.log(math.tan(math.radians(lat)) + (1 / math.cos(math.radians(lat)))) / math.pi) / 2)
    return int(x), int(y), int(zoom)

def _tileBoundary(x, y, z):
    """Return (left, bottom, right, top) of bbox of given tile"""
    n = 2 ** z
    mercToLat = lambda x: math.degrees(math.atan(math.sinh(x)))
    top = mercToLat(math.pi * (1 - 2 * (y * (1/n))))
    bottom = mercToLat(math.pi * (1 - 2 * ((y+1) * (1/n))))
    left = x * (360/n) -180
    right = left + (360/n)
    return left, bottom, right, top

class Datastore:
    """Object for storing routing data with basic OSM parsing functionality"""
    def __init__(self, transport, localfile=False, expire_data=30):
        """Initialise an OSM-file parser"""
        # Routing data
        self.routing = {}
        self.rnodes = {}
        self.mandatoryMoves = {}
        self.forbiddenMoves = set()

        # Info about OSM
        self.tiles = set()
        self.expire_data = 86400 * expire_data # expire_data is in days, we preofrm calculations in seconds
        self.localFile = bool(localfile)

        # Dict-type custom transport weights
        if isinstance(transport, dict):
            # Check if required info is in given transport dict
            assert {"name", "access", "weights"}.issubset(transport.keys())
            self.transport = transport["name"]
            self.type = transport

        else:
            self.transport = transport if transport != "cycle" else "bicycle" # Osm uses bicycle in tags
            self.type = TYPES[transport].copy()

        # Load local file if it was passed
        if self.localFile:
            self.loadOsm(localfile)

    def _allowedVehicle(self, tags):
        """Check way against access tags"""

        # Default to true
        allowed = True

        # Priority is ascending in the access array
        for key in self.type["access"]:
            if key in tags:
                if tags[key] in ["no", "private"]: allowed = False
                else: allowed =  True

        return allowed

    def _attributes(self, element):
        """Get OSM element atttributes and do some common type conversion"""
        result = {}
        for k, v in element.attrib.items():
            if k == "uid": v = int(v)
            elif k == "changeset": v = int(v)
            elif k == "version": v = float(v)
            elif k == "id": v = int(v)
            elif k == "lat": v = float(v)
            elif k == "lon": v = float(v)
            elif k == "open": v = (v == "true")
            elif k == "visible": v = (v == "true")
            elif k == "ref": v = int(v)
            elif k == "comments_count": v = int(v)
            elif k == "timestamp": v = dateutil.parser.parse(v)
            elif k == "created_at": v = dateutil.parser.parse(v)
            elif k == "closed_at": v = dateutil.parser.parse(v)
            elif k == "date": v = dateutil.parser.parse(v)
            result[k] = v
        return result

    def distance(self, n1, n2):
        """Calculate distance in km between two nodes using haversine forumla"""
        lat1, lon1 = n1[0], n1[1]
        lat2, lon2 = n2[0], n2[1]
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        d = math.sin(math.radians(dlat) * 0.5) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(math.radians(dlon) * 0.5) ** 2
        return math.asin(math.sqrt(d)) * 12742

    def nodeLatLon(self, node):
        """Get node's lat lon"""
        return self.rnodes[node]

    def getArea(self, lat, lon):
        """Download data in the vicinity of a lat/long"""
        # Don't download data if we loaded a custom OSM file
        if self.localFile: return

        # Get info on tile in wich lat, lon lays
        x, y, z = _whichTile(lat, lon, 15)
        tileId = "{0},{1}".format(x, y)

        # Don't redownload tiles
        if tileId in self.tiles: return

        # Download tile data
        self.tiles.add(tileId)
        directory = os.path.join("tilescache", "15", str(x), str(y))
        filename = os.path.join(directory, "data.osm")

        # Make sure directory to which we download .osm filess exists
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
            urlretrieve("https://api.openstreetmap.org/api/0.6/map?bbox={0},{1},{2},{3}".format(left, bottom, right, top), filename)

        self.loadOsm(filename)

    def parseOsmFile(self, file):
        """Return nodes, ways and realations of given file
           Only highway=* and railway=* ways are returned, and
           only type=restriction (and type=restriction:<transport type>) are returned"""
        nodes, ways, relations = {}, {}, {}

        # Check if a file-like object was passed
        if hasattr(file, "read"): fp = file

        # If not assume that "file" is a path to file
        else: fp = open(os.fspath(file), "r", encoding="utf-8")

        try:
            for event, elem in etree.iterparse(fp):
                data = self._attributes(elem)
                data["tag"] = {i.attrib["k"]: i.attrib["v"] for i in elem.iter("tag")}

                if elem.tag == "node":
                    nodes[data["id"]] = data

                # Store only potentially routable ways
                elif elem.tag == "way" and (data["tag"].get("highway") or data["tag"].get("railway")):
                    data["nd"] = [int(i.attrib["ref"]) for i in elem.iter("nd")]
                    ways[data["id"]] = data

                # Store only potential turn restrictions
                elif elem.tag == "relation" and data["tag"].get("type", "").startswith("restriction"):
                    data["member"] = [self._attributes(i) for i in elem.iter("member")]
                    relations[data["id"]] = data

        finally:
            # Close file if a path was passed
            if not hasattr(file, "read"): fp.close()

        return nodes, ways, relations

    def loadOsm(self, file):
        """Load data from OSM file to self"""
        nodes, ways, relations = self.parseOsmFile(file)

        for wayId, wayData in ways.items():
            wayNodes = []
            for nd in wayData["nd"]:
                if nd not in nodes: continue
                wayNodes.append((nodes[nd]["id"], nodes[nd]["lat"], nodes[nd]["lon"]))
            self.storeWay(wayId, wayData["tag"], wayNodes)

        for relId, relData in relations.items():
            try:
                # Ignore reltions which are not restrictions
                if relData["tag"].get("type") not in ("restriction", "restriction:" + self.transport):
                    continue

                # Ignore restriction if except tag points to any "access" values
                if set(relData["tag"].get("except", "").split(";")).intersection(self.type["access"]):
                    continue

                # Ignore foot restrictions unless explicitly stated
                if self.transport == "foot" and relData["tag"].get("type") != "restriction:foot" and \
                         "restriction:foot" not in relData["tag"].keys():
                    continue

                restrictionType = relData["tag"].get("restriction:" + self.transport) or relData["tag"]["restriction"]

                nodes = []
                fromMember = [i for i in relData["member"] if i["role"] == "from"][0]
                toMember = [i for i in relData["member"] if i["role"] == "to"][0]

                for viaMember in [i for i in relData["member"] if i["role"] == "via"]:
                    if viaMember["type"] == "way": nodes.append(ways[int(viaMember["ref"])]["nd"])
                    else: nodes.append([int(viaMember["ref"])])

                nodes.insert(0, ways[int(fromMember["ref"])]["nd"])
                nodes.append(ways[int(toMember["ref"])]["nd"])

                self.storeRestriction(relId, restrictionType, nodes)

            except (KeyError, AssertionError, IndexError):
                continue

    def storeRestriction(self, relId, restrictionType, members):
        # Order members of restriction, so that members look somewhat like this: ([a, b], [b, c], [c], [c, d, e], [e, f])
        for x in range(len(members)-1):
            commonNode = (set(members[x]).intersection(set(members[x+1]))).pop()

            # If first node of member[x+1] is different then common_node, try to reverse it
            if members[x+1][0] != commonNode:
                members[x+1].reverse()

            # Only the "from" way can be reversed while ordering the nodes,
            # Otherwise, the x way could be reversed twice (as member[x] and member[x+1])
            if x == 0 and members[x][-1] != commonNode:
                members[x].reverse()

            # Assume member[x] and member[x+1] are ordered correctly
            assert members[x][-1] == members[x+1][0]

        if restrictionType.startswith("no_"):
            # Start by denoting 'from>via'
            forbid = "{},{},".format(members[0][-2], members[1][0])

            # Add all via members
            for x in range(1, len(members)-1):
                for i in members[x][1:]: forbid += "{},".format(i)

            # Finalize by denoting 'via>to'
            forbid += str(members[-1][1])

            self.forbiddenMoves.add(forbid)

        elif restrictionType.startswith("only_"):
            force = []
            forceActivator = "{},{}".format(members[0][-2], members[1][0])

            # Add all via members
            for x in range(1, len(members)-1):
                for i in members[x][1:]: force.append(i)

            # Finalize by denoting 'via>to'
            force.append(members[-1][1])

            self.mandatoryMoves[forceActivator] = force

    def storeWay(self, wayId, tags, nodes):
        highway = self.equivalent(tags.get("highway", ""))
        railway = self.equivalent(tags.get("railway", ""))
        oneway = tags.get("oneway", "")

        # Oneway is default on roundabouts
        if not oneway and (tags.get("junction", "") in ["roundabout", "circular"] or highway == "motorway"):
            oneway = "yes"

        if self.transport == "foot" or (oneway in ["yes", "true", "1", "-1"] and tags.get("oneway:" + self.transport, "yes") == "no"):
            oneway = "no"

        # Calculate what vehicles can use this route
        weight = self.type["weights"].get(highway, 0) or \
                 self.type["weights"].get(railway, 0)

        # Check against access tags
        if (not self._allowedVehicle(tags)) or weight <= 0:
            return

        # Store routing information
        for index in range(1, len(nodes)):
            node1Id, node1Lat, node1Lon = nodes[index - 1]
            node2Id, node2Lat, node2Lon = nodes[index]

            # Check if nodes' positions are stored
            if node1Id not in self.rnodes.keys(): self.rnodes[node1Id] = (node1Lat, node1Lon)
            if node2Id not in self.rnodes.keys(): self.rnodes[node2Id] = (node2Lat, node2Lon)

            # Check if nodes have dicts for storing travel costs
            if node1Id not in self.routing.keys(): self.routing[node1Id] = {}
            if node2Id not in self.routing.keys(): self.routing[node2Id] = {}

            # Is way traversible forward?
            if oneway not in ["-1", "reverse"]:
                self.routing[node1Id][node2Id] = weight

            # Is way traversible backword?
            if oneway not in ["yes", "true", "1"]:
                self.routing[node2Id][node1Id] = weight

    def equivalent(self, tag):
        """Simplifies a bunch of tags to nearly-equivalent ones"""
        equivalent = { \
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
        for nodeId, nodePos in self.rnodes.items():
            distanceDiff = self.distance(nodePos, (lat, lon))
            if distanceDiff < maxDist:
                maxDist = distanceDiff
                closestNode = nodeId

        return closestNode

    def report(self):
        """Display some info about the loaded data"""
        print("Loaded %d nodes" % len(list(self.rnodes.keys())))
        print("Loaded %d %s routes" % (len(list(self.routing.keys())), self.transport))

class Router(Datastore):
    def __getattr__(self, name):
        """BACKWARDS COMAPTIBILITY WHEN DATASTORE WAS AT Router.data"""
        if name == ("data"):
            warn("Router inherits from Datastore, call router.* instead of router.data.*", SyntaxWarning)
            return self
        return object.__getattribute__(self, name)

    def __setattr__(self, name, value):
        """BACKWARDS COMAPTIBILITY WHEN DATASTORE WAS AT Router.data"""
        if name == ("data"):
            warn("Router inherits from Datastore, call router.* instead of router.data.*", SyntaxWarning)
            return self
        return object.__setattr__(self, name, value)

    def doRoute(self, start, end):
        """Do the routing"""
        _closed = {start}
        _queue = []
        _closeNode = True
        _end = end

        # Define function that addes to the queue
        def _addToQueue(start, end, queueSoFar, weight=1):
            """Add another potential route to the queue"""
            nonlocal _closed, _queue, _closeNode

            # Assume start and end nodes have positions
            if end not in self.rnodes or start not in self.rnodes:
                return

            # Get data around end node
            self.getArea(self.rnodes[end][0], self.rnodes[end][1])

            # Ignore if route is not traversible
            if weight == 0:
                return

            # Do not turn around at a node (don't do this: a-b-a)
            if len(queueSoFar["nodes"].split(",")) >= 2 and queueSoFar["nodes"].split(",")[-2] == str(end):
                return

            edgeCost = self.distance(self.rnodes[start], self.rnodes[end]) / weight
            totalCost = queueSoFar["cost"] + edgeCost
            heuristicCost = totalCost + self.distance(self.rnodes[end], self.rnodes[_end])
            allNodes = queueSoFar["nodes"] + "," + str(end)

            # Check if path queueSoFar+end is not forbidden
            for i in self.forbiddenMoves:
                if i in allNodes:
                    _closeNode = False
                    return

            # Check if we have a way to 'end' node
            endQueueItem = None
            for i in _queue:
                if i["end"] == end:
                    endQueueItem = i
                    break

            # If we do, and known totalCost to end is lower we can ignore the queueSoFar path
            if endQueueItem and endQueueItem["cost"] < totalCost:
                return

            # If the queued way to end has higher total cost, remove it (and add the queueSoFar scenario, as it's cheaper)
            elif endQueueItem:
                _queue.remove(endQueueItem)

            # Check against mandatory turns
            forceNextNodes = None
            if queueSoFar.get("mandatoryNodes", None):
                forceNextNodes = queueSoFar["mandatoryNodes"]

            else:
                for activationNodes, nextNodes in self.mandatoryMoves.items():
                    if allNodes.endswith(activationNodes):
                        _closeNode = False
                        forceNextNodes = nextNodes.copy()
                        break

            # Create a hash for all the route's attributes
            queueItem = { \
                "cost": totalCost,
                "heuristicCost": heuristicCost,
                "nodes": allNodes,
                "end": end,
                "mandatoryNodes": forceNextNodes
            }

            # Try to insert, keeping the queue ordered by decreasing heuristic cost
            count = 0
            for test in _queue:
                if test["heuristicCost"] > queueItem["heuristicCost"]:
                    _queue.insert(count, queueItem)
                    break
                count += 1

            else:
                _queue.append(queueItem)

        # Start by queueing all outbound links from the start node
        if start not in self.routing.keys():
            return "no_such_node", []

        elif start == end:
            return "no_route", []

        else:
            for linkedNode, weight in self.routing[start].items():
                _addToQueue(start, linkedNode, {"cost": 0, "nodes": str(start)}, weight)

        # Limit for how long it will search
        count = 0
        while count < 1000000:
            count += 1
            _closeNode = True

            # Pop first item from queue for routing. If queue it's empty - it means no route exists
            if len(_queue) > 0:
                nextItem = _queue.pop(0)
            else:
                return "no_route", []

            consideredNode = nextItem["end"]

            # If we already visited the node, ignore it
            if consideredNode in _closed:
                continue

            # Found the end node - success
            if consideredNode == end:
                return "success", [int(i) for i in nextItem["nodes"].split(",")]

            # Check if we preform a mandatory turn
            if nextItem["mandatoryNodes"]:
                _closeNode = False
                nextNode = nextItem["mandatoryNodes"].pop(0)
                if consideredNode in self.routing.keys() and nextNode in self.routing.get(consideredNode, {}).keys():
                    _addToQueue(consideredNode, nextNode, nextItem, self.routing[consideredNode][nextNode])

            # If no, add all possible nodes from x to queue
            elif consideredNode in self.routing.keys():
                for nextNode, weight in self.routing[consideredNode].items():
                    if nextNode not in _closed:
                        _addToQueue(consideredNode, nextNode, nextItem, weight)

            if _closeNode:
                _closed.add(consideredNode)

        else:
            return "gave_up", []
