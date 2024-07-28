# pyroutelib3

<!-- This file must be kept in sync with docs/index.rst -->

[GitHub](https://github.com/MKuranowski/pyroutelib3) |
[Documentation](https://pyroutelib3.readthedocs.io/) |
[Issue Tracker](https://github.com/MKuranowski/pyroutelib3/issues) |
[PyPI](https://pypi.org/project/pyroutelib3/)

Simple routing over OSM data.

pyroutelib3 is a Python library for simple routing over
[OpenStreetMap](https://openstreetmap.org) data.

```py
import pyroutelib3

live_graph = pyroutelib3.osm.LiveGraph(pyroutelib3.osm.CarProfile())

start_node = live_graph.find_nearest_node((52.23201, 21.00737))
end_node = live_graph.find_nearest_node((52.24158, 21.02807))

route = pyroutelib3.find_route_without_turn_around(live_graph, start_node.id, end_node.id)
route_lat_lons = [live_graph.get_node(node).position for node in route]
```

The example above uses `osm.LiveGraph`, which automatically downloads OpenStreetMap data in tiles
and caches them on your disk. It is much more wise to download the data beforehand from a service
like [Geofabrik OSM data extracts](https://download.geofabrik.de/):

```py
import pyroutelib3

with open("mazowieckie-latest.osm.pbf", "rb") as f:
    graph = pyroutelib3.osm.Graph.from_file(pyroutelib3.osm.CarProfile(), f)

start_node = graph.find_nearest_node((52.23201, 21.00737))
end_node = graph.find_nearest_node((52.24158, 21.02807))

route = pyroutelib3.find_route_without_turn_around(graph, start_node, end_node)
route_lat_lons = [graph.get_node(node).position for node in route]
```

pyroutelib3 not only is able to parse OpenStreetMap data into a graph (see the `osm` module),
but also contains generic implementations of the A* path-finding algorithm (`find_route` and
`find_route_without_turn_around` functions) and the k-d tree data structure (`KDTree` class).

This library was designed with extensibility in mind, and most components can be swapped for
completely custom ones through the usage of well-defined protocols. As an example,
a `nx.GraphAdaptor` is provided to use [networkx graphs](https://networkx.org/documentation/stable/reference/introduction.html#graphs)
with pyroutelib3's functionality.


## Installation

```
pip install --upgrade pyroutelib3
```

pyroutelib3 uses [semantic versioning](https://semver.org/). Always specify dependencies on
this library with a constraint on the major revision, e.g. `pyroutelib3 ~= 2.0.0`.

Note that version 1 of this library is incompatible with version 2.


## Features

- Generic A* algorithm implementation (`find_route` and `find_route_without_turn_around` functions)
- Generic graph data structure (`SimpleGraph` class)
- Generic k-d data structure (`KDTree` class)
- Extensibility through usage of well-defined protocols (`protocols` module)
    - [networkx](https://networkx.org/) compatibility (`nx.GraphAdaptor` and
        `nx.ExternalGraphAdaptor` classes)
- [OSM XML](https://wiki.openstreetmap.org/wiki/OSM_XML) and [OSM PBF](https://wiki.openstreetmap.org/wiki/PBF_Format>)
    file parsing (`osm.reader.read_features` function)
- Converting [OpenStreetMap data](https://openstreetmap.org/) into a usable graph (`osm.Graph` class)
    - High customizability of the process through the usage of different profiles.
    - Expressing way preferences through the usage of penalties for unpreferred tags
    - Respecting [access restrictions](https://wiki.openstreetmap.org/wiki/Key:access) on ways
    - Support for [turn restrictions](https://wiki.openstreetmap.org/wiki/Relation:restriction>),
        including `restriction:TRANSPORT` and `exempt` tags
    - Downloading data on-the-fly (`osm.LiveGraph` class)


## License

pyroutelib3 is distributed under GNU GPL v3 (or any later version).

> © Copyright 2024 Mikołaj Kuranowski
>
> pyroutelib3 is free software: you can redistribute it and/or modify
> it under the terms of the GNU General Public License as published by
> the Free Software Foundation; either version 3 of the License, or
> (at your option) any later version.
>
> pyroutelib3 is distributed in the hope that it will be useful,
> but WITHOUT ANY WARRANTY; without even the implied warranty of
> MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
> GNU General Public License for more details.
>
> You should have received a copy of the GNU General Public License
> along with pyroutelib3. If not, see <http://www.gnu.org/licenses/>.
