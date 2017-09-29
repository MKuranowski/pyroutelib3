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
#----------------------------------------------------------------------------
import os
import re
import sys
import math
import osmapi
import xml.etree.ElementTree as etree
from datetime import datetime
from . import (tiledata, tilenames, weights)


__title__ = "pyroutelib3"
__description__ = "Library for simple routing on OSM data"
__url__ = "https://github.com/MKuranowski/pyroutelib3"
__author__ = "Oliver White"
__copyright__ = "Copyright 2007, Oliver White; Modifications: Copyright 2017, Mikolaj Kuranowski"
__credits__ = ["Oliver White", "Mikolaj Kuranowski"]
__license__ = "GPL v3"
__version__ = "0.3"
__maintainer__ = "Mikolaj Kuranowski"
__email__ = "mkuranowski@gmail.com"


class Datastore(object):
    """Parse an OSM file looking for routing information"""
    def __init__(self, transport, localfile=""):
        """Initialise an OSM-file parser"""
        self.routing = {}
        self.rnodes = {}
        self.transport = transport
        self.localFile = localfile
        self.tiles = {}
        self.weights = weights.RoutingWeights()
        self.api = osmapi.OsmApi(api="api.openstreetmap.org")

        if self.localFile:
            self.loadOsm(self.localFile)

    def getArea(self, lat, lon):
        """Download data in the vicinity of a lat/long.
        Return filename to existing or newly downloaded .osm file."""

        z = tiledata.DownloadLevel()
        (x,y) = tilenames.tileXY(lat, lon, z)

        tileID = '%d,%d'%(x,y)
        if self.tiles.get(tileID,False) or self.localFile:
            return

        self.tiles[tileID] = True

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

    def getElementAttributes(self, element):
        result = {}
        for k, v in element.attrib.items():
            if k == "uid": v = int(v)
            elif k == "changeset": v = int(v)
            elif k == "version": v = int(v)
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
        result = []
        with open(filename, "r") as f:
            for event, elem in etree.iterparse(f): # events=['end']
                if elem.tag == "node":
                    data = self.getElementAttributes(elem)
                    data["tag"] = self.getElementTags(elem)
                    result.append({
                        "type": "node",
                        "data": data
                    })
                elif elem.tag == "way":
                    data = self.getElementAttributes(elem)
                    data["tag"] = self.getElementTags(elem)
                    data["nd"] = []
                    for child in elem:
                        if child.tag == "nd": data["nd"].append(int(child.attrib["ref"]))
                    result.append({
                        "type": "way",
                        "data": data
                    })
                elif elem.tag == "relation":
                    data = self.getElementAttributes(elem)
                    data["tag"] = self.getElementTags(elem)
                    data["member"] = []
                    for child in elem:
                        if child.tag == " member": data["member"].append(self.getElementAttributes(child))
                    result.append({
                        "type": "relation",
                        "data": data
                    })
                    elem.clear()
        return result

    def loadOsm(self, filename):
        if(not os.path.exists(filename)):
            print("No such data file %s" % filename)
            return(False)

        nodes, ways = {}, {}

        data = self.parseOsmFile(filename)
        # data = [{ type: node|way|relation, data: {}},...]

        for x in data:
            try:
                if x['type'] == 'node':
                    nodes[x['data']['id']] = x['data']
                elif x['type'] == 'way':
                    ways[x['data']['id']] = x['data']
                else:
                    continue
            except KeyError:
                # Don't care about bad data (no type/data key)
                continue

        for way_id, way_data in ways.items():
            way_nodes = []
            for nd in way_data['nd']:
                if nd not in nodes: continue
                way_nodes.append([nodes[nd]['id'], nodes[nd]['lat'], nodes[nd]['lon']])
            self.storeWay(way_id, way_data['tag'], way_nodes)

        return(True)

    def storeWay(self, wayID, tags, nodes):
        highway = self.equivalent(tags.get('highway', ''))
        railway = self.equivalent(tags.get('railway', ''))
        oneway = tags.get('oneway', '')
        reversible = not oneway in('yes','true','1')

        # Calculate what vehicles can use this route
        # TODO: just use getWeight != 0
        access = {}
        access['cycle'] = highway in ('primary','secondary','tertiary','unclassified','minor','cycleway','residential', 'track','service')
        access['car'] = highway in ('motorway','trunk','primary','secondary','tertiary','unclassified','minor','residential', 'service')
        access['train'] = railway in ('rail','light_rail','subway')
        access['tram'] = railway in ('tram')
        access['foot'] = access['cycle'] or highway in('footway','steps')
        access['horse'] = highway in ('track','unclassified','bridleway')

        # Store routing information
        last = [None,None,None]

        if(wayID == 41 and 0):
            print(nodes)
            sys.exit()

        for node in nodes:
            (node_id,x,y) = node
            if last[0]:
                if(access[self.transport]):
                    weight = self.weights.get(self.transport, railway or highway)
                    self.addLink(last[0], node_id, weight)
                    self.makeNodeRouteable(last)
                    if reversible or self.transport == 'foot':
                        self.addLink(node_id, last[0], weight)
                        self.makeNodeRouteable(node)
            last = node

    def makeNodeRouteable(self, node):
        self.rnodes[node[0]] = [node[1],node[2]]

    def addLink(self, fr, to, weight=1):
        """Add a routeable edge to the scenario"""
        try:
            if to in list(self.routing[fr].keys()):
                return
            self.routing[fr][to] = weight
        except KeyError:
            self.routing[fr] = {to: weight}

    def equivalent(self, tag):
        """Simplifies a bunch of tags to nearly-equivalent ones"""
        equivalent = { \
            "primary_link":"primary",
            "trunk":"primary",
            "trunk_link":"primary",
            "secondary_link":"secondary",
            "tertiary":"secondary",
            "tertiary_link":"secondary",
            "residential":"unclassified",
            "minor":"unclassified",
            "steps":"footway",
            "driveway":"service",
            "pedestrian":"footway",
            "bridleway":"cycleway",
            "track":"cycleway",
            "arcade":"footway",
            "canal":"river",
            "riverbank":"river",
            "lake":"river",
            "light_rail":"railway"
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

    def distance(self,n1,n2):
        """Calculate distance between two nodes"""
        lat1 = self.data.rnodes[n1][0]
        lon1 = self.data.rnodes[n1][1]
        lat2 = self.data.rnodes[n2][0]
        lon2 = self.data.rnodes[n2][1]
        # TODO: projection issues
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        dist2 = dlat * dlat + dlon * dlon
        dist = math.sqrt(dist2)
        return(dist)

    def nodeLatLon(self, node):
        """Get node's lat lon"""
        lat, lon = self.data.rnodes[node][0], self.data.rnodes[node][1]
        return([lat, lon])

    def doRoute(self, start, end):
        """Do the routing"""
        self.searchEnd = end
        closed = [start]
        self.queue = []

        # Start by queueing all outbound links from the start node
        blankQueueItem = {'end':-1,'distance':0,'nodes':str(start)}

        try:
            for i, weight in self.data.routing[start].items():
                self._addToQueue(start,i, blankQueueItem, weight)
        except KeyError:
            return('no_such_node',[])

        # Limit for how long it will search
        count = 0
        while count < 1000000:
            count = count + 1
            try:
                nextItem = self.queue.pop(0)
            except IndexError:
                # Queue is empty: failed
                # TODO: return partial route?
                return('no_route',[])
            x = nextItem['end']
            if x in closed: continue
            if x == end:
                # Found the end node - success
                routeNodes = [int(i) for i in nextItem['nodes'].split(",")]
                return('success', routeNodes)
            closed.append(x)
            try:
                for i, weight in self.data.routing[x].items():
                    if not i in closed:
                        self._addToQueue(x,i,nextItem, weight)
            except KeyError:
                pass
        else:
            return('gave_up',[])

    def _addToQueue(self, start, end, queueSoFar, weight=1):
        """Add another potential route to the queue"""

        # getArea() checks that map data is available around the end-point,
        # and downloads it if necessary
        #
        # TODO: we could reduce downloads even more by only getting data around
        # the tip of the route, rather than around all nodes linked from the tip
        end_pos = self.data.rnodes[end]
        self.data.getArea(end_pos[0], end_pos[1])

        # If already in queue, ignore
        for test in self.queue:
            if test['end'] == end: return
        distance = self.distance(start, end)
        if(weight == 0): return
        distance = distance / weight

        # Create a hash for all the route's attributes
        distanceSoFar = queueSoFar['distance']
        queueItem = { \
            'distance': distanceSoFar + distance,
            'maxdistance': distanceSoFar + self.distance(end, self.searchEnd),
            'nodes': queueSoFar['nodes'] + "," + str(end),
            'end': end
        }

        # Try to insert, keeping the queue ordered by decreasing worst-case distance
        count = 0
        for test in self.queue:
            if test['maxdistance'] > queueItem['maxdistance']:
                self.queue.insert(count,queueItem)
                break
            count = count + 1
        else:
            self.queue.append(queueItem)
