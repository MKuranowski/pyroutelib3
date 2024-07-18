from unittest import TestCase

from .profile import HighwayProfile

TEST_HIGHWAY_PROFILE = HighwayProfile(
    "cat",
    {"footway": 1.0, "path": 2.0},
    ["access", "cat"],
)


class TestHighwayProfile(TestCase):
    def test_way_penalty(self) -> None:
        self.assertEqual(TEST_HIGHWAY_PROFILE.way_penalty({"highway": "footway"}), 1.0)
        self.assertEqual(TEST_HIGHWAY_PROFILE.way_penalty({"highway": "path"}), 2.0)
        self.assertIsNone(TEST_HIGHWAY_PROFILE.way_penalty({"highway": "motorway"}))
        self.assertIsNone(TEST_HIGHWAY_PROFILE.way_penalty({"highway": "motorway", "access": "no"}))
        self.assertEqual(
            TEST_HIGHWAY_PROFILE.way_penalty(
                {"highway": "footway", "access": "private", "cat": "yes"},
            ),
            1.0,
        )

    def test_way_direction(self) -> None:
        self.assertTupleEqual(
            TEST_HIGHWAY_PROFILE.way_direction({"highway": "footway"}),
            (True, True),
        )
        self.assertTupleEqual(
            TEST_HIGHWAY_PROFILE.way_direction({"highway": "footway", "oneway": "yes"}),
            (True, False),
        )
        self.assertTupleEqual(
            TEST_HIGHWAY_PROFILE.way_direction({"highway": "footway", "oneway": "-1"}),
            (False, True),
        )
        self.assertTupleEqual(
            TEST_HIGHWAY_PROFILE.way_direction({"highway": "motorway_link"}),
            (True, False),
        )
        self.assertTupleEqual(
            TEST_HIGHWAY_PROFILE.way_direction({"highway": "footway", "junction": "roundabout"}),
            (True, False),
        )
        self.assertTupleEqual(
            TEST_HIGHWAY_PROFILE.way_direction({"highway": "motorway_link", "oneway": "no"}),
            (True, True),
        )
        self.assertTupleEqual(
            TEST_HIGHWAY_PROFILE.way_direction(
                {"highway": "footway", "junction": "roundabout", "oneway": "-1"},
            ),
            (False, True),
        )

    def test_is_exempted(self) -> None:
        self.assertFalse(TEST_HIGHWAY_PROFILE.is_exempted({}))
        self.assertFalse(TEST_HIGHWAY_PROFILE.is_exempted({"except": "bus"}))
        self.assertTrue(TEST_HIGHWAY_PROFILE.is_exempted({"except": "cat"}))
        self.assertTrue(TEST_HIGHWAY_PROFILE.is_exempted({"except": "bus;cat"}))
