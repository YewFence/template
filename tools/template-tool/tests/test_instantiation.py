from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from template_tool.instantiation import (
    InstantiationError,
    InstantiationSpec,
    instantiate_tree,
    validate_metadata_value,
)


class TestInstantiation:
    def setup_method(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.spec = InstantiationSpec(
            required=("project_name", "description", "binary_name"),
            tokens={"PROJECT_NAME": "project_name", "PROJECT_DESCRIPTION": "description", "BINARY_NAME": "binary_name"},
            derived={"PROJECT_DESCRIPTION_JSON": ("description", "json-string")},
            validation_metadata={"project_name": "Example", "description": "Hello", "binary_name": "example"},
            export_metadata={"project_name": "Replace Me", "description": "Replace me", "binary_name": "replace-me"},
        )

    def teardown_method(self) -> None:
        self.temporary_directory.cleanup()

    def test_replaces_text_and_path_tokens(self) -> None:
        (self.root / "cmd/{{BINARY_NAME}}").mkdir(parents=True)
        (self.root / "cmd/{{BINARY_NAME}}/main.go").write_text(
            'package main\nconst name = "{{PROJECT_NAME}}"\nconst description = {{PROJECT_DESCRIPTION_JSON}}\n',
            encoding="utf-8",
        )
        instantiate_tree(self.root, self.spec, {"project_name": "Example CLI", "description": 'Say "hello"', "binary_name": "example"})
        output = self.root / "cmd/example/main.go"
        assert output.is_file()
        assert "Example CLI" in output.read_text(encoding="utf-8")
        assert '"Say \\"hello\\""' in output.read_text(encoding="utf-8")

    def test_rejects_invalid_metadata_and_unknown_token(self) -> None:
        with pytest.raises(InstantiationError, match="leading or trailing"):
            instantiate_tree(self.root, self.spec, {"project_name": " Example", "description": "ok", "binary_name": "example"})
        (self.root / "README.md").write_text("{{UNKNOWN_TOKEN}}\n", encoding="utf-8")
        with pytest.raises(InstantiationError, match="unknown metadata token"):
            instantiate_tree(self.root, self.spec, self.spec.validation_metadata)

    def test_rejects_path_collision(self) -> None:
        (self.root / "cmd/{{BINARY_NAME}}").mkdir(parents=True)
        (self.root / "cmd/example").mkdir(parents=True)
        with pytest.raises(InstantiationError, match="target already exists"):
            instantiate_tree(self.root, self.spec, self.spec.validation_metadata)

    def test_rejects_invalid_github_identity_metadata(self) -> None:
        with pytest.raises(InstantiationError, match="valid GitHub owner"):
            validate_metadata_value("github_owner", "YewFence/")
        with pytest.raises(InstantiationError, match="valid GitHub repository"):
            validate_metadata_value("repo_name", "example/repository")
        with pytest.raises(InstantiationError, match="valid Python package identifier"):
            validate_metadata_value("python_package", "example-package")
        with pytest.raises(InstantiationError, match="valid Python package identifier"):
            validate_metadata_value("python_package", "class")
