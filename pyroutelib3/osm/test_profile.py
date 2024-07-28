# © Copyright 2024 Mikołaj Kuranowski
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import TestCase

from .profile import (
    FootProfile,
    HighwayProfile,
    NonMotorroadHighwayProfile,
    RailwayProfile,
    SkeletonProfile,
    TurnRestriction,
)


class TestSkeletonProfile(TestCase):
    def test(self) -> None:
        p = SkeletonProfile()

        self.assertEqual(p.way_penalty({}), 1.0)
        self.assertEqual(p.way_penalty({"railway": "rail"}), 1.0)
        self.assertEqual(p.way_penalty({"railway": "narrow_gauge"}), 1.0)
        self.assertEqual(p.way_penalty({"highway": "primary"}), 1.0)
        self.assertEqual(p.way_penalty({"railway": "rail", "access": "no"}), 1.0)

        self.assertEqual(p.way_direction({}), (True, True))
        self.assertEqual(p.way_direction({"oneway": "yes"}), (True, False))
        self.assertEqual(p.way_direction({"oneway": "-1"}), (False, True))
        self.assertEqual(p.way_direction({"oneway": "no"}), (True, True))

        self.assertIs(
            p.is_turn_restriction({"type": "restriction", "restriction": "no_left_turn"}),
            TurnRestriction.INAPPLICABLE,
        )
        self.assertIs(
            p.is_turn_restriction({"type": "restriction", "restriction": "only_right_turn"}),
            TurnRestriction.INAPPLICABLE,
        )
        self.assertIs(
            p.is_turn_restriction({"type": "restriction", "restriction:foot": "no_left_turn"}),
            TurnRestriction.INAPPLICABLE,
        )
        self.assertIs(
            p.is_turn_restriction({"restriction": "no_left_turn"}),
            TurnRestriction.INAPPLICABLE,
        )
        self.assertIs(p.is_turn_restriction({}), TurnRestriction.INAPPLICABLE)


class TestHighwayProfile(TestCase):
    profile = HighwayProfile(
        "cat",
        {"footway": 1.0, "path": 2.0},
        ["access", "cat"],
    )

    def test_way_penalty(self) -> None:
        self.assertEqual(self.profile.way_penalty({"highway": "footway"}), 1.0)
        self.assertEqual(self.profile.way_penalty({"highway": "path"}), 2.0)
        self.assertIsNone(self.profile.way_penalty({"highway": "motorway"}))
        self.assertIsNone(self.profile.way_penalty({"highway": "motorway", "access": "no"}))
        self.assertEqual(
            self.profile.way_penalty(
                {"highway": "footway", "access": "private", "cat": "yes"},
            ),
            1.0,
        )

    def test_get_active_highway_value(self) -> None:
        self.assertEqual(self.profile.get_active_highway_value({"highway": "footway"}), "footway")
        self.assertEqual(self.profile.get_active_highway_value({"highway": "motorway"}), "motorway")
        self.assertEqual(
            self.profile.get_active_highway_value({"highway": "motorway_link"}),
            "motorway",
        )
        self.assertEqual(
            self.profile.get_active_highway_value({"building": "yes"}),
            "",
        )

    def test_is_allowed(self) -> None:
        self.assertTrue(self.profile.is_allowed({}))
        self.assertTrue(self.profile.is_allowed({"foot": "no"}))
        self.assertFalse(self.profile.is_allowed({"cat": "no"}))
        self.assertFalse(self.profile.is_allowed({"access": "yes", "cat": "no"}))
        self.assertTrue(self.profile.is_allowed({"access": "no", "cat": "yes"}))
        self.assertTrue(self.profile.is_allowed({"motorroad": "yes"}))

    def test_way_direction(self) -> None:
        self.assertTupleEqual(
            self.profile.way_direction({"highway": "footway"}),
            (True, True),
        )
        self.assertTupleEqual(
            self.profile.way_direction({"highway": "footway", "oneway": "yes"}),
            (True, False),
        )
        self.assertTupleEqual(
            self.profile.way_direction({"highway": "footway", "oneway": "-1"}),
            (False, True),
        )
        self.assertTupleEqual(
            self.profile.way_direction({"highway": "motorway_link"}),
            (True, False),
        )
        self.assertTupleEqual(
            self.profile.way_direction({"highway": "footway", "junction": "roundabout"}),
            (True, False),
        )
        self.assertTupleEqual(
            self.profile.way_direction({"highway": "motorway_link", "oneway": "no"}),
            (True, True),
        )
        self.assertTupleEqual(
            self.profile.way_direction(
                {"highway": "footway", "junction": "roundabout", "oneway": "-1"},
            ),
            (False, True),
        )

    def test_get_active_oneway_value(self) -> None:
        self.assertEqual(self.profile.get_active_oneway_value({}), "")
        self.assertEqual(self.profile.get_active_oneway_value({"oneway": "yes"}), "yes")
        self.assertEqual(
            self.profile.get_active_oneway_value({"oneway": "yes", "oneway:cat": "no"}),
            "no",
        )

    def test_is_turn_restriction(self) -> None:
        self.assertIs(self.profile.is_turn_restriction({}), TurnRestriction.INAPPLICABLE)
        self.assertIs(
            self.profile.is_turn_restriction({"type": "multipolygon"}),
            TurnRestriction.INAPPLICABLE,
        )
        self.assertIs(
            self.profile.is_turn_restriction({"restriction": "no_left_turn"}),
            TurnRestriction.INAPPLICABLE,
        )
        self.assertIs(
            self.profile.is_turn_restriction({"type": "restriction", "restriction": "no_u_turn"}),
            TurnRestriction.PROHIBITORY,
        )
        self.assertIs(
            self.profile.is_turn_restriction({"type": "restriction", "restriction": "only_u_turn"}),
            TurnRestriction.MANDATORY,
        )
        self.assertIs(
            self.profile.is_turn_restriction({"type": "restriction", "restriction": "no_entry"}),
            TurnRestriction.INAPPLICABLE,
        )
        self.assertIs(
            self.profile.is_turn_restriction(
                {"type": "restriction", "restriction:hgv": "no_u_turn"},
            ),
            TurnRestriction.INAPPLICABLE,
        )
        self.assertIs(
            self.profile.is_turn_restriction(
                {"type": "restriction", "restriction:cat": "no_u_turn"},
            ),
            TurnRestriction.PROHIBITORY,
        )
        self.assertIs(
            self.profile.is_turn_restriction(
                {"type": "restriction", "restriction": "no_u_turn", "except": "cat"},
            ),
            TurnRestriction.INAPPLICABLE,
        )

    def test_get_active_restriction_value(self) -> None:
        self.assertEqual(self.profile.get_active_restriction_value({}), "")
        self.assertEqual(
            self.profile.get_active_restriction_value({"restriction": "no_left_turn"}),
            "no_left_turn",
        )
        self.assertEqual(
            self.profile.get_active_restriction_value(
                {"restriction": "only_straight_on", "restriction:cat": "no_straight_on"}
            ),
            "no_straight_on",
        )

    def test_is_exempted(self) -> None:
        self.assertFalse(self.profile.is_exempted({}))
        self.assertFalse(self.profile.is_exempted({"except": "bus"}))
        self.assertTrue(self.profile.is_exempted({"except": "cat"}))
        self.assertTrue(self.profile.is_exempted({"except": "bus;cat"}))


class TestNonMotorroadHighwayProfile(TestCase):
    profile = NonMotorroadHighwayProfile(
        "cat",
        {"footway": 1.0, "path": 2.0},
        ["access", "cat"],
    )

    def test(self) -> None:
        self.assertFalse(self.profile.is_allowed({"motorroad": "yes"}))


class TestFootProfile(TestCase):
    profile = FootProfile()

    def test_get_active_highway_value(self) -> None:
        self.assertEqual(self.profile.get_active_highway_value({}), "")
        self.assertEqual(self.profile.get_active_highway_value({"highway": "footway"}), "footway")
        self.assertEqual(
            self.profile.get_active_highway_value({"highway": "primary_link"}),
            "primary",
        )
        self.assertEqual(self.profile.get_active_highway_value({"highway": "platform"}), "platform")
        self.assertEqual(
            self.profile.get_active_highway_value({"public_transport": "platform"}),
            "platform",
        )
        self.assertEqual(self.profile.get_active_highway_value({"railway": "platform"}), "platform")

    def test_get_active_oneway_value(self) -> None:
        self.assertEqual(
            self.profile.get_active_oneway_value({"highway": "primary", "oneway": "yes"}),
            "",
        )
        self.assertEqual(
            self.profile.get_active_oneway_value({"highway": "path", "oneway": "yes"}),
            "yes",
        )
        self.assertEqual(
            self.profile.get_active_oneway_value({"highway": "primary", "oneway:foot": "yes"}),
            "yes",
        )

    def test_get_active_restriction_value(self) -> None:
        self.assertEqual(
            self.profile.get_active_restriction_value({"restriction": "no_u_turn"}),
            "",
        )
        self.assertEqual(
            self.profile.get_active_restriction_value({"restriction:foot": "no_u_turn"}),
            "no_u_turn",
        )


class TestRailwayProfile(TestCase):
    def test(self) -> None:
        p = RailwayProfile()

        self.assertEqual(p.way_penalty({"railway": "rail"}), 1.0)
        self.assertEqual(p.way_penalty({"railway": "narrow_gauge"}), 1.0)
        self.assertIsNone(p.way_penalty({"highway": "primary"}))
        self.assertIsNone(p.way_penalty({"railway": "rail", "access": "no"}))

        self.assertEqual(p.way_direction({}), (True, True))
        self.assertEqual(p.way_direction({"oneway": "yes"}), (True, False))
        self.assertEqual(p.way_direction({"oneway": "-1"}), (False, True))
        self.assertEqual(p.way_direction({"oneway": "no"}), (True, True))

        self.assertIs(
            p.is_turn_restriction({"type": "restriction", "restriction": "no_left_turn"}),
            TurnRestriction.PROHIBITORY,
        )
        self.assertIs(
            p.is_turn_restriction({"type": "restriction", "restriction": "only_right_turn"}),
            TurnRestriction.MANDATORY,
        )
        self.assertIs(
            p.is_turn_restriction({"type": "restriction", "restriction:foot": "no_left_turn"}),
            TurnRestriction.INAPPLICABLE,
        )
        self.assertIs(
            p.is_turn_restriction({"restriction": "no_left_turn"}),
            TurnRestriction.INAPPLICABLE,
        )
