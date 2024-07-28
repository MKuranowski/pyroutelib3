Migrating from v1
=================

.. py:currentmodule:: pyroutelib3

While all of the functionality from v1 is retained in v2, the API has been completely
overhauled. The old Router class is no longer present (being replaced by simple functions,
:py:func:`find_route` and :py:func:`find_route_without_turn_around`). Datastore has
been replaced by :py:class:`osm.Graph` and :py:class:`osm.LiveGraph` classes.


Datastore
---------

Main usage (instantiating a graph, finding nodes close to start and end position,
finding the shortest path and converting node ids to lat-lon pairs) is presented in
:doc:`the main page </index>`.

Instead of ``r = Router("car", "my-local-file.osm.pbf", localFileType="pbf")`` do this::

    with open("my-local-file.osm.pbf", "rb") as f:
        graph = pyroutelib3.osm.Graph.from_file(pyroutelib3.osm.CarProfile(), f)

To load data automatically from OSM, instead of ``r = Router("car")``, do this::

    graph = pyroutelib3.osm.LiveGraph(pyroutelib3.osm.CarProfile())


.. rubric:: Initialization arguments

====================== ===========================================================================================
v1                     v2
====================== ===========================================================================================
transport              profile
localfile              :py:meth:`osm.Graph.from_file`, ``buf`` argument
localfileType          :py:meth:`osm.Graph.from_file`, ``format`` argument
expireData             tile_expiry_seconds (:py:class:`osm.LiveGraph` only)
ignoreDataErrs         no direct replacement, use ``logging.getLogger("pyroutelib3.osm").setLevel(logging.ERROR)``
distFunction           not applicable, OSM data implies :py:func:`haversine_earth_distance`
pyroutelib3.TILES_ZOOM :py:attr:`~osm.LiveGraph.tile_zoom` (:py:class:`osm.LiveGraph` only)
====================== ===========================================================================================

.. rubric:: Attributes/Properties

====================== ===========================================================================================
v1                     v2
====================== ===========================================================================================
rnodes                 :py:attr:`~SimpleGraph.nodes`
routing                :py:attr:`~SimpleGraph.edges`
mandatoryMoves         not applicable, turn restrictions are directly represented in the graph
forbiddenMoves         not applicable, turn restrictions are directly represented in the graph
distance               not applicable, OSM data implies :py:func:`haversine_earth_distance`
transport              not applicable, some profiles have a ``name`` attribute
type                   :py:attr:`~osm.Graph.profile`
localFile              not applicable, use ``local_file = not isinstance(graph, pyroutelib3.osm.LiveGraph)``
pyroutelib3.TILES_ZOOM :py:attr:`~osm.LiveGraph.tile_zoom` (:py:class:`osm.LiveGraph` only)
====================== ===========================================================================================

.. rubric:: Methods

================ ================================================================================================
v1               v2
================ ================================================================================================
getArea          :py:meth:`~osm.LiveGraph.load_tile_around` (:py:class:`osm.LiveGraph` only)
loadOsm          :py:meth:`~osm.Graph.add_features` (use in conjunction with :py:func:`osm.reader.read_features`)
storeWay         not possible to add a single way
storeRestriction not possible to add a single restriction
equivalent       depends on the :py:class:`osm.Profile` implementation
findNode         :py:meth:`~osm.Graph.find_nearest_node`, :py:attr:`~SimpleExternalNode.id` attribute
nodeLatLon       :py:meth:`~osm.Graph.find_nearest_node`, :py:attr:`~SimpleExternalNode.position` attribute
report           no replacement
doRoute          see :ref:`Router section <migration_router>`
================ ================================================================================================


Profiles
--------

Profiles (also called types in v1 documentation) has seen the largest overhaul in v2.
In v1 routing profiles were represented by a dictionary of the profile name, weights
and access tags; and pre-defined profiles could be provided as strings. In v2, profiles
are abstracted away into a simple protocol, :py:class:`osm.Profile`.

.. _migration_base_profiles:

V2 comes with 4 base implementations of that interface: :py:class:`osm.SkeletonProfile`,
:py:class:`osm.RailwayProfile`, :py:class:`HighwayProfile` and :py:class:`NonMotorroadHighwayProfile`.

Instead of using weights, preferences are now expressed using penalties. Version 1
calculated the cost of an edge as ``distance_between_nodes / weight``, which lead to
violations of the `A* heuristic <https://en.wikipedia.org/wiki/A*_search_algorithm#Admissibility>`_
if weight was greater than 1. In version 2, the calculation was changed to ``distance_between_nodes * penalty``,
with a check that the penalty is not smaller than 1, ensuring the A* heuristic behaves correctly.
To convert weights to penalties, divide each weight by the minimal weight, e.g.::

    {"primary": 0.2, "secondary": 0.6, "tertiary": 1.0}
    → {"primary": 0.2 / 0.2, "secondary": 0.6 / 0.2, "tertiary": 1.0 / 0.2}
    → {"primary": 1.0, "secondary": 3.0, "tertiary": 5.0}

Pre-made profiles can be replaced by directly instantiating the following classes:

===== ==============================
v1    v2
===== ==============================
car   :py:class:`osm.CarProfile`
bus   :py:class:`osm.BusProfile`
cycle :py:class:`osm.BicycleProfile`
horse ∅
foot  :py:class:`osm.FootProfile`
tram  :py:class:`osm.TramProfile`
train :py:class:`osm.RailwayProfile`
∅     :py:class:`osm.SubwayProfile`
===== ==============================

Each of the pre-made profiles accepts custom ``name``, ``penalties`` and ``access`` arguments,
to override default values. Custom profiles can be implemented by inheriting from
:ref:`base profiles <migration_base_profiles>` (see :py:class:`~osm.FootProfile` for a good example
of that), or by completely custom class implementing :py:class:`osm.Profile`.


.. _migration_router:

Router
------

The Router class is no longer present in version 2, the ``doRoute`` method has been
replaced by the :py:func:`find_route_without_turn_around` and :py:func:`find_route` functions.
Prefer to use the first function, unless you are absolutely sure there are no turn
restrictions in your data.

The status string is no longer being used, instead, :ref:`find_route family of functions <find_route>`
behave in the following manner:

========= ==================================
v1 status v2 behavior
========= ==================================
success   non-empty list returned
no_route  empty list returned
gave_up   :py:exc:`StepLimitExceeded` raised
========= ==================================

Instead of the ``SEARCH_LIMIT`` module constants, :ref:`find_route functions <find_route>` take a
``step_limit`` argument.

Instead of the ``distance`` Datastore attribute / ``distFunction`` init parameter,
:ref:`find_route functions <find_route>` take a ``distance`` parameter.


Distance functions
------------------

============= ===================================
v1            v2
============= ===================================
distHaversine :py:func:`haversine_earth_distance`
distEuclidian :py:func:`euclidean_distance`
∅             :py:func:`taxicab_distance`
============= ===================================
