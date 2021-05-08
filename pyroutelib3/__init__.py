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
#  2020-10-23  MK   Refactor code
# ---------------------------------------------------------------------------

"""Library for simple routing on OSM data"""

from .datastore import Datastore
from .router import Router
from .types import TypeDescription, TYPES
from .util import SEARCH_LIMIT, TILES_ZOOM, distHaversine, distEuclidian

__title__ = "pyroutelib3"
__description__ = "Library for simple routing on OSM data"
__url__ = "https://github.com/MKuranowski/pyroutelib3"
__author__ = "Oliver White"
__copyright__ = "Copyright 2007, Oliver White; " \
                "Modifications: Copyright 2017-2021, Mikolaj Kuranowski"
__credits__ = ["Oliver White", "Mikolaj Kuranowski"]
__license__ = "GPL v3"
__version__ = "1.7.1"
__maintainer__ = "Mikolaj Kuranowski"
__email__ = "".join(chr(i) for i in [109, 107, 117, 114, 97, 110, 111, 119, 115, 107, 105, 32, 91,
                                     1072, 116, 93, 32, 103, 109, 97, 105, 108, 46, 99, 111, 109])
