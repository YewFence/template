from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from template_tool import TemplateError, TemplateRepository


class TemplateCapabilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        (self.root / "shared/static").mkdir(parents=True)
        (self.root / "overlays/example/static").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_config(
        self,
        capabilities: str = "docs-site = true\nrelease = false\n",
        *,
        version: int = 2,
        top_level: str = "",
        profile: str = "",
    ) -> None:
        (self.root / "templates.toml").write_text(
            f"version = {version}\n"
            f"{top_level}"
            "[templates.example]\n"
            f"{profile}"
            "[templates.example.capabilities]\n"
            f"{capabilities}"
            "[templates.example.instantiation]\n"
            'required = ["project_name"]\n'
            "[templates.example.instantiation.tokens]\n"
            'PROJECT_NAME = "project_name"\n'
            "[templates.example.instantiation.validation.metadata]\n"
            'project_name = "Example Project"\n'
            "[templates.example.instantiation.export.metadata]\n"
            'project_name = "REPLACE ME: project name"\n',
            encoding="utf-8",
        )

    def test_resolver_applies_defaults_and_deduplicated_overrides(self) -> None:
        self.write_config()
        repository = TemplateRepository(self.root)

        self.assertEqual(repository.resolve_capabilities("example"), ("docs-site",))
        self.assertEqual(
            repository.resolve_capabilities(
                "example",
                enable=("release", "release"),
                disable=("docs-site", "docs-site"),
            ),
            ("release",),
        )

    def test_resolver_rejects_conflicting_overrides(self) -> None:
        self.write_config()
        repository = TemplateRepository(self.root)

        with self.assertRaisesRegex(TemplateError, "both enabled and disabled: release"):
            repository.resolve_capabilities(
                "example", enable=("release",), disable=("release",)
            )

    def test_resolver_rejects_capability_not_declared_by_profile(self) -> None:
        self.write_config()
        repository = TemplateRepository(self.root)

        with self.assertRaisesRegex(TemplateError, "not applicable.*unknown"):
            repository.resolve_capabilities("example", enable=("unknown",))

    def test_resolver_rejects_invalid_override_name(self) -> None:
        self.write_config()
        repository = TemplateRepository(self.root)

        with self.assertRaisesRegex(TemplateError, "invalid capability name"):
            repository.resolve_capabilities("example", enable=("Docs-Site",))

    def test_capability_contract_requires_supported_schema_version(self) -> None:
        self.write_config(version=1)
        with self.assertRaisesRegex(TemplateError, "version = 2"):
            TemplateRepository(self.root)

        self.write_config(version=3)
        with self.assertRaisesRegex(TemplateError, "version = 2"):
            TemplateRepository(self.root)

    def test_capability_contract_rejects_unknown_fields_before_profiles(self) -> None:
        self.write_config(top_level="unknown = true\n")

        with self.assertRaisesRegex(TemplateError, "unknown top-level keys: unknown"):
            TemplateRepository(self.root)

    def test_capability_contract_rejects_unknown_profile_fields(self) -> None:
        self.write_config(
            capabilities='docs-site = "yes"\n', profile="unknown = true\n"
        )

        with self.assertRaisesRegex(
            TemplateError, "unknown keys in templates.example: unknown"
        ):
            TemplateRepository(self.root)

    def test_capability_names_and_defaults_are_validated(self) -> None:
        for declaration in (
            "Docs-Site = true\n",
            "docs_site = true\n",
            "docs--site = true\n",
            'docs-site = "yes"\n',
        ):
            with self.subTest(declaration=declaration):
                self.write_config(capabilities=declaration)
                with self.assertRaisesRegex(TemplateError, "capabilit"):
                    TemplateRepository(self.root)

    def test_capabilities_are_sorted_and_do_not_create_identity_tokens(self) -> None:
        self.write_config(capabilities="zeta = true\nalpha = false\n")
        repository = TemplateRepository(self.root)

        self.assertEqual(
            repository.capabilities("example"),
            (("alpha", False), ("zeta", True)),
        )
        self.assertEqual(
            repository.instantiation_spec("example").tokens,
            {"PROJECT_NAME": "project_name"},
        )


if __name__ == "__main__":
    unittest.main()
