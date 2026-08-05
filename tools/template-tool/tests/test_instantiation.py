from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from template_tool.instantiation import InstantiationError, InstantiationSpec, instantiate_tree


class InstantiationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.spec = InstantiationSpec(
            required=("project_name", "description", "binary_name"),
            tokens={"PROJECT_NAME": "project_name", "PROJECT_DESCRIPTION": "description", "BINARY_NAME": "binary_name"},
            derived={"PROJECT_DESCRIPTION_JSON": ("description", "json-string")},
            validation_metadata={"project_name": "Example", "description": "Hello", "binary_name": "example"},
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_replaces_text_and_path_tokens(self) -> None:
        (self.root / "cmd/{{BINARY_NAME}}").mkdir(parents=True)
        (self.root / "cmd/{{BINARY_NAME}}/main.go").write_text(
            'package main\nconst name = "{{PROJECT_NAME}}"\nconst description = {{PROJECT_DESCRIPTION_JSON}}\n',
            encoding="utf-8",
        )
        instantiate_tree(self.root, self.spec, {"project_name": "Example CLI", "description": 'Say "hello"', "binary_name": "example"})
        output = self.root / "cmd/example/main.go"
        self.assertTrue(output.is_file())
        self.assertIn('Example CLI', output.read_text(encoding="utf-8"))
        self.assertIn('"Say \\"hello\\""', output.read_text(encoding="utf-8"))

    def test_rejects_invalid_metadata_and_unknown_token(self) -> None:
        with self.assertRaisesRegex(InstantiationError, "leading or trailing"):
            instantiate_tree(self.root, self.spec, {"project_name": " Example", "description": "ok", "binary_name": "example"})
        (self.root / "README.md").write_text("{{UNKNOWN_TOKEN}}\n", encoding="utf-8")
        with self.assertRaisesRegex(InstantiationError, "unknown metadata token"):
            instantiate_tree(self.root, self.spec, self.spec.validation_metadata)

    def test_rejects_path_collision(self) -> None:
        (self.root / "cmd/{{BINARY_NAME}}").mkdir(parents=True)
        (self.root / "cmd/example").mkdir(parents=True)
        with self.assertRaisesRegex(InstantiationError, "target already exists"):
            instantiate_tree(self.root, self.spec, self.spec.validation_metadata)


if __name__ == "__main__":
    unittest.main()
