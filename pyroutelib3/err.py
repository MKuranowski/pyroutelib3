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

"""Contains errors used by pyroutelib3"""


class BaseOsmError(Exception):
    """Base for all error thrown by pyroutelib3."""
    pass


class OsmReferenceError(BaseOsmError, KeyError):
    """OSM Feature referenced another, not known feature."""
    pass


class OsmInvalidRestriction(BaseOsmError, ValueError):
    """OSM restriction relation is not valid."""
    pass


class OsmStructureError(BaseOsmError, ValueError):
    """Provided OSM file is invalid"""
    pass


class InvalidNode(BaseOsmError, KeyError):
    """User-provided node is not known."""
    pass


class InvalidTypeDescription(BaseOsmError, TypeError):
    """User-provided routing type is not valid."""
