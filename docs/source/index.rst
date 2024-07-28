pyroutelib3
===========

.. This file must be kept in sync with README.md.

.. py:currentmodule:: pyroutelib3

`GitHub <https://github.com/MKuranowski/pyroutelib3>`_ |
`Documentation <https://pyroutelib3.readthedocs.io/>`_ |
`Issue Tracker <https://github.com/MKuranowski/pyroutelib3/issues>`_ |
`PyPI <https://pypi.org/project/pyroutelib3/>`_

pyroutelib3 is a Python library for simple routing over
`OpenStreetMap <https://openstreetmap.org>`_ data. ::

    import pyroutelib3

    live_graph = pyroutelib3.osm.LiveGraph(pyroutelib3.osm.CarProfile())

    start_node = live_graph.find_nearest_node((52.23201, 21.00737))
    end_node = live_graph.find_nearest_node((52.24158, 21.02807))

    route = pyroutelib3.find_route_without_turn_around(live_graph, start_node.id, end_node.id)
    route_lat_lons = [live_graph.get_node(node).position for node in route]

The example above uses :py:class:`osm.LiveGraph`, which automatically downloads OpenStreetMap
data in tiles and caches them on your disk. It is much more wise to download the data beforehand
from a service like `Geofabrik OSM data extracts <https://download.geofabrik.de/>`_::

    import pyroutelib3

    with open("mazowieckie-latest.osm.pbf", "rb") as f:
        graph = pyroutelib3.osm.Graph.from_file(pyroutelib3.osm.CarProfile(), f)

    start_node = graph.find_nearest_node((52.23201, 21.00737))
    end_node = graph.find_nearest_node((52.24158, 21.02807))

    route = pyroutelib3.find_route_without_turn_around(graph, start_node, end_node)
    route_lat_lons = [graph.get_node(node).position for node in route]

pyroutelib3 not only is able to parse OpenStreetMap data into a graph
(see the `osm` module), but also contains generic implementations of the A* path-finding
algorithm (:py:func:`find_route` and :py:func:`find_route_without_turn_around`) and the
k-d tree data structure (:py:class:`KDTree`).

This library was designed with extensibility in mind, and most components can be swapped for
completely custom ones through the usage of well-defined :py:mod:`protocols`. As an example,
a :py:class:`nx.GraphAdaptor` is provided to use `networkx graphs <https://networkx.org/documentation/stable/reference/introduction.html#graphs>`_
with pyroutelib3's functionality.


Installation
------------

::

    pip install pyroutelib3

pyroutelib3 uses `semantic versioning <https://semver.org/>`_. Always specify dependencies on
this library with a constraint on the major revision, e.g. ``pyroutelib3 ~= 2.0.0``.

Note that version 1 of this library is incompatible with version 2.


Features
--------

* Generic A* algorithm implementation (:py:func:`find_route` and :py:func:`find_route_without_turn_around`)
* Generic graph data structure (:py:class:`SimpleGraph`)
* Generic k-d data structure (:py:class:`KDTree`)
* Extensibility through usage of well-defined :py:mod:`~pyroutelib3.protocols`

  * `networkx <https://networkx.org/>`_ compatibility (:py:class:`nx.GraphAdaptor` and
    :py:class:`nx.ExternalGraphAdaptor`)

* `OSM XML <https://wiki.openstreetmap.org/wiki/OSM_XML>`_ and `OSM PBF <https://wiki.openstreetmap.org/wiki/PBF_Format>`_
  file parsing (:py:func:`osm.reader.read_features`)
* Converting `OpenStreetMap data <https://openstreetmap.org/>`_ into a usable graph (:py:class:`osm.Graph`)

  * High customizability of the process through the usage of :ref:`different profiles <profiles>`.
  * Expressing way preferences through the usage of penalties for unpreferred tags
  * Respecting `access restrictions <https://wiki.openstreetmap.org/wiki/Key:access>`_ on ways
  * Support for `turn restrictions <https://wiki.openstreetmap.org/wiki/Relation:restriction>`_,
    including ``restriction:TRANSPORT`` and ``exempt`` tags
  * Downloading data on-the-fly (:py:class:`osm.LiveGraph`)


.. toctree::
    :hidden:
    :maxdepth: 2

    self
    api
    migrating_from_v1
    license
    changelog