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
#----------------------------------------------------------------------------
import os
import re
import sys
import math
import osmapi
import xml.etree.ElementTree as etree
from collections import OrderedDict
from datetime import datetime
from . import (tiledata, tilenames)


__title__ = "pyroutelib3"
__description__ = "Library for simple routing on OSM data"
__url__ = "https://github.com/MKuranowski/pyroutelib3"
__author__ = "Oliver White"
__copyright__ = "Copyright 2007, Oliver White; Modifications: Copyright 2017-2018, Mikolaj Kuranowski"
__credits__ = ["Oliver White", "Mikolaj Kuranowski"]
__license__ = "GPL v3"
__version__ = "0.9pre5"
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
        "access": ["access", "vehicle", "motor_vehicle", "motorcar"]},
    "tram": {
        "weights": {"tram": 1, "light_rail": 1},
        "access": []},
    "train": {
        "weights": {"rail": 1, "light_rail": 1, "subway": 1, "narrow_guage": 1},
        "access": []}
}

class Datastore(object):
    """Parse an OSM file looking for routing information"""
    def __init__(self, transport, localfile=""):
        """Initialise an OSM-file parser"""
        self.routing = {}
        self.rnodes = {}
        self.mandatoryMoves = {}
        self.forbiddenMoves = set()

        self.tiles = []
        self.transport = transport if transport != "cycle" else "bicycle" # Osm uses bicycle in tags
        self.localFile = localfile
        self.type = TYPES[transport]

        if self.localFile:
            self.loadOsm(self.localFile)
            self.api = None

        else:
            self.api = osmapi.OsmApi(api="api.openstreetmap.org")

    def getArea(self, lat, lon):
        """Download data in the vicinity of a lat/long.
        Return filename to existing or newly downloaded .osm file."""

        z = tiledata.DownloadLevel()
        (x,y) = tilenames.tileXY(lat, lon, z)

        tileID = '%d,%d'%(x,y)
        if self.localFile or tileID in self.tiles:
            return

        self.tiles.append(tileID)

        filename = tiledata.GetOsmTileData(z,x,y)
        #print "Loading %d,%d at z%d from %s" % (x,y,z,filename)
        return(self.loadOsm(filename))

    def _ParseDate(self, DateString):
        result = DateString
        try:
            result = datetime.strptime(DateString, "%Y-%m-%d %H:%M:%S UTC")
        except:
            try:
                result = datetime.strptime(DateString, "%Y-%m-%dT%H:%M:%SZ")
            except:
                pass
        return result

    def _allowedVehicle(self, tags):
        "Check way against access tags"

        # Default to true
        allowed = True

        # Priority is ascending in the access array
        for key in self.type["access"]:
            if key in tags:
                if tags[key] in ("no", "private"): allowed = False
                else: allowed =  True

        return(allowed)

    def getElementAttributes(self, element):
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
            elif k == "timestamp": v = self._ParseDate(v)
            elif k == "created_at": v = self._ParseDate(v)
            elif k == "closed_at": v = self._ParseDate(v)
            elif k == "date": v = self._ParseDate(v)
            result[k] = v
        return result

    def getElementTags(self, element):
        result = {}
        for child in element:
            if child.tag =="tag":
                k = child.attrib["k"]
                v = child.attrib["v"]
                result[k] = v
        return result

    def parseOsmFile(self, filename):
        nodes, ways, relations = {}, {}, {}
        with open(filename, "r", encoding="utf-8") as f:
            for event, elem in etree.iterparse(f): # events=['end']
                data = self.getElementAttributes(elem)
                data["tag"] = self.getElementTags(elem)

                if elem.tag == "node":
                    nodes[data["id"]] = data

                elif elem.tag == "way":
                    data["nd"] = []
                    for child in elem:
                        if child.tag == "nd": data["nd"].append(int(child.attrib["ref"]))
                    ways[data["id"]] = data

                elif elem.tag == "relation":
                    data["member"] = []
                    for child in elem:
                        if child.tag == "member": data["member"].append(self.getElementAttributes(child))
                    relations[data["id"]] = data

        return nodes, ways, relations

    def loadOsm(self, filename):
        if(not os.path.exists(filename)):
            print("No such data file %s" % filename)
            return(False)

        nodes, ways, relations = self.parseOsmFile(filename)

        for way_id, way_data in ways.items():
            way_nodes = []
            for nd in way_data['nd']:
                if nd not in nodes: continue
                way_nodes.append([nodes[nd]['id'], nodes[nd]['lat'], nodes[nd]['lon']])
            self.storeWay(way_id, way_data['tag'], way_nodes)

        for rel_id, rel_data in relations.items():
            try:
                # Ignore reltions which are not restrictions
                if rel_data["tag"].get("type") not in ("restriction", "restriction:" + self.transport): continue

                # Ignore restriction if except tag points to any "access" values
                if set(rel_data["tag"].get("except", "").split(";")).intersection(self.type["access"]): continue

                # Ignore foot restrictions unless explicitly stated
                if self.transport == "foot" and rel_data["tag"].get("type") != "restriction:foot" and \
                         "restriction:foot" not in rel_data["tag"].keys():
                    continue

                restriction_type = rel_data["tag"].get("restriction:" + self.transport, rel_data["tag"]["restriction"])

                nodes = []
                from_member = [i for i in rel_data["member"] if i["role"] == "from"][0]
                to_member = [i for i in rel_data["member"] if i["role"] == "to"][0]

                for via_member in [i for i in rel_data["member"] if i["role"] == "via"]:
                    if via_member["type"] == "way": nodes.append(ways[int(via_member["ref"])]["nd"])
                    else: nodes.append([int(via_member["ref"])])

                nodes.insert(0, ways[int(from_member["ref"])]["nd"])
                nodes.append(ways[int(to_member["ref"])]["nd"])

                self.storeRestriction(rel_id, restriction_type, nodes)

            except (KeyError, AssertionError, IndexError):
                continue

        return(True)

    def storeRestriction(self, rel_id, restriction_type, members):
        # Order members of restriction, so that members look somewhat like this: ([a, b], [b, c], [c], [c, d, e], [e, f])
        for x in range(len(members)-1):
            common_node = (set(members[x]).intersection(set(members[x+1]))).pop()

            # If first node of member[x+1] is different then common_node, try to reverse it
            if members[x+1][0] != common_node:
                members[x+1].reverse()

            # Only the "from" way can be reversed while ordering the nodes,
            # Otherwise, the x way could be reversed twice (as member[x] and member[x+1])
            if x == 0 and members[x][-1] != common_node:
                members[x].reverse()

            # Assume member[x] and member[x+1] are ordered correctly
            assert members[x][-1] == members[x+1][0]

        if restriction_type.startswith("no_"):
            # Start by denoting 'from>via'
            forbid = "{},{},".format(members[0][-2], members[1][0])

            # Add all via members
            for x in range(1, len(members)-1):
                for i in members[x][1:]: forbid += "{},".format(i)

            # Finalize by denoting 'via>to'
            forbid += str(members[-1][1])

            self.forbiddenMoves.add(forbid)

        elif restriction_type.startswith("only_"):
            force = []
            force_activator = "{},{}".format(members[0][-2], members[1][0])

            # Add all via members
            for x in range(1, len(members)-1):
                for i in members[x][1:]: force.append(i)

            # Finalize by denoting 'via>to'
            force.append(members[-1][1])

            self.mandatoryMoves[force_activator] = force

    def storeWay(self, wayID, tags, nodes):
        highway = self.equivalent(tags.get("highway", ""))
        railway = self.equivalent(tags.get("railway", ""))
        oneway = tags.get("oneway", "")

        # Oneway is default on roundabouts
        if not oneway and tags.get("junction", "") in ["roundabout", "circular"]:
            oneway = "yes"

        if oneway in ["yes", "true", "1", "-1"] and tags.get("oneway:" + self.transport, "yes") == "no":
            oneway = "no"

        # Calculate what vehicles can use this route
        weight = self.type["weights"].get(highway, 0) or \
                 self.type["weights"].get(railway, 0)

        # Check against access tags
        if not self._allowedVehicle(tags): weight = 0

        # Store routing information
        last = [None, None, None]

        for node in nodes:
            (node_id, x, y) = node
            if last[0]:
                if weight != 0:
                    if oneway not in ["-1"]:
                        self.addLink(last[0], node_id, weight)
                        self.makeNodeRouteable(last)
                    if oneway not in ["yes", "true", "1"] or self.transport == "foot":
                        self.addLink(node_id, last[0], weight)
                        self.makeNodeRouteable(node)
            last = node

    def makeNodeRouteable(self, node):
        self.rnodes[node[0]] = [node[1],node[2]]

    def addLink(self, fr, to, weight=1):
        """Add a routeable edge to the scenario"""
        if fr not in self.routing:
            self.routing[fr] = {}
        self.routing[fr][to] = weight

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
        try: return(equivalent[tag])
        except KeyError: return(tag)

    def findNode(self, lat, lon):
        """Find the nearest node that can be the start of a route"""
        self.getArea(lat,lon)
        maxDist = 1E+20
        nodeFound = None
        posFound = None
        for (node_id,pos) in list(self.rnodes.items()):
            dy = pos[0] - lat
            dx = pos[1] - lon
            dist = dx * dx + dy * dy
            if(dist < maxDist):
                maxDist = dist
                nodeFound = node_id
                posFound = pos
        # print("found at %s"%str(posFound))
        return(nodeFound)

    def report(self):
        """Display some info about the loaded data"""
        print("Loaded %d nodes" % len(list(self.rnodes.keys())))
        print("Loaded %d %s routes" % (len(list(self.routing.keys())), self.transport))

class Router(object):
    def __init__(self, transport, localfile=""):
        self.data = Datastore(transport, localfile)

    def distance(self, n1, n2):
        """Calculate distance in km between two nodes using haversine forumla"""
        lat1, lon1 = map(math.radians, self.data.rnodes[n1])
        lat2, lon2 = map(math.radians, self.data.rnodes[n2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        d = math.sin(dlat * 0.5) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon * 0.5) ** 2
        return math.asin(math.sqrt(d)) * 12742

    def nodeLatLon(self, node):
        """Get node's lat lon"""
        lat, lon = self.data.rnodes[node][0], self.data.rnodes[node][1]
        return([lat, lon])

    def doRoute(self, start, end):
        """Do the routing"""
        self.searchEnd = end
        self.closed = [start]
        self.queue = []

        # Start by queueing all outbound links from the start node
        blankQueueItem = {'end':-1,'cost':0,'nodes':str(start)}

        if start not in self.data.routing.keys():
            return 'no_such_node', []
        else:
            for i, weight in self.data.routing[start].items():
                self._addToQueue(start, i, blankQueueItem, weight)

        # Limit for how long it will search
        count = 0
        while count < 1000000:
            count = count + 1
            self.nodeWasFullySerched = True
            if len(self.queue) > 0:
                nextItem = self.queue.pop(0)
            else:
                return 'no_route', []

            x = nextItem['end']
            if x in self.closed: continue
            if x == end:
                # Found the end node - success
                return 'success', [int(i) for i in nextItem['nodes'].split(",")]

            # Check if we preform a mandatory turn
            if nextItem['mandatoryNodes']:
                self.nodeWasFullySerched = False
                y = nextItem['mandatoryNodes'].pop(0)
                if x in self.data.routing.keys() and y in self.data.routing.get(x, {}).keys():
                    self._addToQueue(x, y, nextItem, self.data.routing[x][y])

            # If no, add all possible nodes from x to queue
            elif x in self.data.routing.keys():
                for y, weight in self.data.routing[x].items():
                    if y not in self.closed:
                        self._addToQueue(x, y, nextItem, weight)

            if self.nodeWasFullySerched:
                self.closed.append(x)

        else:
            return 'gave_up', []

    def _addToQueue(self, start, end, queueSoFar, weight=1):
        """Add another potential route to the queue"""

        # Assume start and end nodes have positions
        if end not in self.data.rnodes or start not in self.data.rnodes:
            return

        # getArea() checks that map data is available around the end-point,
        # and downloads it if necessary
        #
        # TODO: we could reduce downloads even more by only getting data around
        # the tip of the route, rather than around all nodes linked from the tip
        self.data.getArea(self.data.rnodes[end][0], self.data.rnodes[end][1])

        # Ignore if route is not traversible
        if weight == 0:
            return

        # Do not turn around at a node (don't do this: a-b-a)
        if len(queueSoFar['nodes'].split(",")) >= 2 and queueSoFar['nodes'].split(",")[-2] == str(end):
            return

        edgeCost = self.distance(start, end) / weight
        totalCost = queueSoFar['cost'] + edgeCost
        heuristicCost = totalCost + self.distance(end, self.searchEnd)
        allNodes = queueSoFar['nodes'] + "," + str(end)

        # Check if path queueSoFar+end is not forbidden
        for i in self.data.forbiddenMoves:
            if i in allNodes:
                self.nodeWasFullySerched = False
                return

        # Check if we have a way to 'end' node
        endQueueItem = None
        for i in self.queue:
            if i['end'] == end:
                endQueueItem = i
                break

        # If we do, and known totalCost to end is lower we can ignore the queueSoFar path
        if endQueueItem and endQueueItem['cost'] < totalCost:
            return

        # If the queued way to end has higher total cost, remove it (and add the queueSoFar scenario, as it's cheaper)
        elif endQueueItem:
            self.queue.remove(endQueueItem)

        # Check against mandatory turns
        forceNextNodes = None
        if queueSoFar.get('mandatoryNodes', None):
            forceNextNodes = queueSoFar['mandatoryNodes']
        else:
            for activationNodes, nextNodes in self.data.mandatoryMoves.items():
                if allNodes.endswith(activationNodes):
                    self.nodeWasFullySerched = False
                    forceNextNodes = nextNodes.copy()
                    break

        # Create a hash for all the route's attributes
        queueItem = { \
            'cost': totalCost,
            'heuristicCost': heuristicCost,
            'nodes': allNodes,
            'end': end,
            'mandatoryNodes': forceNextNodes
        }

        # Try to insert, keeping the queue ordered by decreasing heuristic cost
        count = 0
        for test in self.queue:
            if test['heuristicCost'] > queueItem['heuristicCost']:
                self.queue.insert(count, queueItem)
                break
            count += 1
        else:
            self.queue.append(queueItem)
