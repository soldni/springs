import unittest

import springs as sp


class TestResolvers(unittest.TestCase):
    def test_sanitize(self):
        c = sp.from_dict(
            {
                "a": "///fooo:::",
                "b": "${sp.sanitize:${a}}",
                "c": "${sp.sanitize:${a},0}",
                "d": "${sp.sanitize:${a},true}",
                "e": "${sp.sanitize:${a},true,4}",
                "f": '${sp.sanitize:${a},true,255," "}',
            }
        )

        self.assertEqual(c.b, "_fooo_")
        self.assertEqual(c.c, "___fooo___")
        self.assertEqual(c.d, c.b)
        self.assertEqual(c.e, "_f")
        self.assertEqual(c.f, " fooo")
