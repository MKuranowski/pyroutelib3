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

"""Contains the Router implementation"""

from typing import List, Dict, Tuple
from math import inf
import heapq

from .datastore import Datastore
from .util import SEARCH_LIMIT, _AStarQueueItem
from .err import InvalidNode


class Router(Datastore):

    def _routeIsForbidden(self, route: List[int]) -> bool:
        """Checks if provided route ends with a forbidden move"""
        # There have to be at least 3 nodes for a forbidden move to match
        routeLen = len(route)
        if routeLen < 3:
            return False

        forbidHash = route[-3], route[-2], route[-1]

        # No restrictions under this hash
        if forbidHash not in self.forbiddenMoves:
            return False

        # Iterate over each restriction and test if it matches
        for forbiddenMove in self.forbiddenMoves[forbidHash]:
            moveLen = len(forbiddenMove)

            # If a move is longer the current route - restriction can't apply
            if moveLen > routeLen:
                continue

            # Check if last nodes of route match the forbidden move
            if route[-moveLen:] == forbiddenMove:
                return True

        return False

    def _routeForceNext(self, route: List[int], force: List[int]) -> List[int]:
        """Gets the value for _AStarQueueItem.forceNext based on:
        route up to and incl. considered node;
        previous item's forceNext without considered node."""
        if force:
            # If a mandatory move is performed: just return it
            return force
        if len(route) < 2:
            # Too short route to create an activator
            return []

        # Create and activator for look-up
        activator = route[-2], route[-1]

        if activator in self.mandatoryMoves:
            # Activator starts a mandatory move - return such move
            return self.mandatoryMoves[activator].copy()
        else:
            # No mandatory move
            return []

    def doRoute(self, start: int, end: int) -> Tuple[str, List[int]]:
        # Ensure start and end exist
        if start not in self.rnodes:
            raise InvalidNode(f"Start node ({start}) doesn't exist in graph")

        if end not in self.rnodes:
            raise InvalidNode(f"End node ({start}) doesn't exist in graph")

        # Special case if start == end
        if start == end:
            return "success", [start]

        # Search variables
        searched = 0
        queue: List[_AStarQueueItem] = []
        knownScores: Dict[int, float] = {}
        endLocation = self.rnodes[end]

        # Per-node variables
        distance = self.distance(self.rnodes[start], endLocation)

        # Add start node to queue
        knownScores[start] = 0
        heapq.heappush(
            queue,
            _AStarQueueItem(node=start, routeTo=[start], costTo=0, heuristic=distance),
        )

        # Iterate over items in queue
        while queue:
            # Check the search limit
            searched += 1
            if searched > SEARCH_LIMIT:
                return "gave_up", []

            # Retrieve an item from queue
            currItem = heapq.heappop(queue)
            currToLen = len(currItem.routeTo)

            # Check if end was reached
            if currItem.node == end:
                return "success", currItem.routeTo

            # Add all edges from this node to queue
            for toNode, edgeCost in self.routing.get(currItem.node, {}).items():
                # Get area around toNode
                toNodePos = self.rnodes[toNode]
                self.getArea(*toNodePos)

                # Ignore non-traversible edges
                if edgeCost <= 0:
                    continue

                # No turn-around at nodes (no a-b-a)
                if currToLen >= 2 and currItem.routeTo[-2] == toNode:
                    continue

                # Check if a mandatory move is performed and is followed
                if currItem.forceNext and currItem.forceNext[0] != toNode:
                    continue

                # Gather info about added item
                distance = self.distance(toNodePos, endLocation)
                newItem = _AStarQueueItem(
                    node=toNode,
                    routeTo=currItem.routeTo + [toNode],
                    costTo=currItem.costTo + edgeCost,
                    heuristic=currItem.costTo + distance,
                    forceNext=currItem.forceNext[1:],
                )

                # Check if a cheaper route to toNode exists
                if newItem.costTo > knownScores.get(toNode, inf):
                    continue

                # Check if we run into a restriction
                if self._routeIsForbidden(newItem.routeTo):
                    continue

                # Update the forceNext, if a new mandatory move is started
                newItem.forceNext = self._routeForceNext(newItem.routeTo, newItem.forceNext)

                # Save data to knownCosts and push into the queue
                knownScores[toNode] = newItem.costTo
                heapq.heappush(queue, newItem)

        # No route
        return "no_route", []
