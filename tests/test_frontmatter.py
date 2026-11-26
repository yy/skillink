"""Verify stdlib YAML frontmatter parsing without external dependencies."""

import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

with patch.object(
    sys, "path", [str(Path(__file__).resolve().parents[1] / "bin"), *sys.path]
):
    fm = importlib.import_module("frontmatter")


class FrontmatterTests(unittest.TestCase):
    def test_plain_quoted_and_multiline_scalars(self):
        text = (
            "---\n"
            "# Leading comment\n"
            "name: alpha  # inline comment\n"
            'description: "Quoted: \\"value\\" with # hash"\n'
            "single: 'it''s fine'\n"
            "folded: >\n"
            "  First line\n"
            "  second line.\n"
            "\n"
            "  Second paragraph.\n"
            "literal: |-\n"
            "  line 1\n"
            "  line 2\n"
            "continuation: starts here\n"
            "  and continues\n"
            "disable-model-invocation: true\n"
            "nested:\n"
            "  author: yy\n"
            "  tags:\n"
            "    - one\n"
            "---\n"
            "Body text.\n"
        )
        data, body = fm.parse_frontmatter(text)
        self.assertEqual(data["name"], "alpha")
        self.assertEqual(data["description"], 'Quoted: "value" with # hash')
        self.assertEqual(data["single"], "it's fine")
        self.assertEqual(data["folded"], "First line second line.\nSecond paragraph.\n")
        self.assertEqual(data["literal"], "line 1\nline 2")
        self.assertEqual(data["continuation"], "starts here and continues")
        self.assertIs(data["disable-model-invocation"], True)
        self.assertEqual(body, "Body text.")

    def test_malformed_frontmatter_raises_value_error(self):
        cases = [
            "No frontmatter at all\n",
            "---\nname: alpha\n",
            "---\n- item\n---\nBody\n",
            '---\nname: "unclosed\n---\nBody\n',
            "---\nname: alpha\nname: beta\n---\nBody\n",
            "---\n  indented: bad\n---\nBody\n",
        ]
        for sample in cases:
            with self.subTest(sample=sample):
                with self.assertRaises(ValueError):
                    fm.parse_frontmatter(sample)


if __name__ == "__main__":
    unittest.main()
