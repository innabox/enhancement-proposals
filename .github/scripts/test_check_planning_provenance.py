"""Unit tests for the planning-document provenance contract."""

import unittest
from unittest import mock

import check_planning_provenance as provenance


def marker(payload: str) -> str:
    return f"<!-- ai-workflow-provenance:{payload} -->"


class ChangedDocumentPathsTests(unittest.TestCase):
    def test_selects_only_changed_planning_documents(self):
        diff = (
            b"README.md\0"
            b"enhancements/OSAC-1-example/design.md\0"
            b"enhancements/OSAC-2-example/prd.md\0"
            b"enhancements/OSAC-3-example/Design.md\0"
            b"enhancements/OSAC-4-example/DESIGN.md\0"
            b"enhancements/OSAC-5-example/README.md\0"
            b"guidelines/design.md\0"
            b"enhancements/OSAC-6-example/notes.md\0"
        )
        self.assertEqual(
            provenance.changed_document_paths(diff),
            [
                "enhancements/OSAC-1-example/design.md",
                "enhancements/OSAC-2-example/prd.md",
                "enhancements/OSAC-3-example/Design.md",
                "enhancements/OSAC-4-example/DESIGN.md",
                "enhancements/OSAC-5-example/README.md",
            ],
        )


class DocumentValidationTests(unittest.TestCase):
    design_path = "enhancements/OSAC-1-example/design.md"

    def test_accepts_session_provenance_for_matching_document_type(self):
        content = (
            "# Design\n\n## Provenance\n\n"
            + marker('{"schema_version":1,"provenance_kind":"session","workflow":"design"}')
        )
        self.assertEqual(provenance.validate_document(self.design_path, content), [])

    def test_accepts_legacy_and_case_variant_design_filenames(self):
        content = (
            "# Design\n\n## Provenance\n\n"
            + marker('{"schema_version":1,"provenance_kind":"session","workflow":"design"}')
        )
        for filename in ("README.md", "Design.md", "DESIGN.md"):
            path = f"enhancements/OSAC-1-example/{filename}"
            with self.subTest(filename=filename):
                self.assertEqual(provenance.validate_document(path, content), [])

    def test_accepts_commit_only_provenance(self):
        content = (
            "# Design\n\n## Provenance\n\n"
            + marker('{"schema_version":1,"provenance_kind":"commit_only","workflow":"design"}')
        )
        self.assertEqual(provenance.validate_document(self.design_path, content), [])

    def test_accepts_explicit_decline_marker_without_footer(self):
        content = "# Design\n\n" + marker('{"schema_version":1,"provenance_kind":"declined"}')
        self.assertEqual(provenance.validate_document(self.design_path, content), [])

    def test_rejects_missing_provenance(self):
        self.assertEqual(
            provenance.validate_document(self.design_path, "# Design\n"),
            [f"{self.design_path}: missing ai-workflow-provenance comment"],
        )

    def test_rejects_wrong_workflow(self):
        content = (
            "# Design\n\n## Provenance\n\n"
            + marker('{"schema_version":1,"provenance_kind":"session","workflow":"prd"}')
        )
        self.assertEqual(
            provenance.validate_document(self.design_path, content),
            [f"{self.design_path}: provenance workflow must be 'design', not 'prd'"],
        )

    def test_rejects_invalid_json_and_multiple_markers(self):
        invalid = "# Design\n\n" + marker("not-json")
        self.assertEqual(
            provenance.validate_document(self.design_path, invalid),
            [f"{self.design_path}: provenance comment does not contain valid JSON"],
        )

        multiple = (
            "# Design\n\n## Provenance\n\n"
            + marker('{"schema_version":1,"provenance_kind":"session","workflow":"design"}')
            + "\n"
            + marker('{"schema_version":1,"provenance_kind":"session","workflow":"design"}')
        )
        self.assertEqual(
            provenance.validate_document(self.design_path, multiple),
            [f"{self.design_path}: expected exactly one ai-workflow-provenance comment"],
        )


class ChangedDocumentsValidationTests(unittest.TestCase):
    @mock.patch.object(provenance, "run_git")
    def test_reads_changed_document_at_head_and_reports_its_missing_marker(self, run_git):
        path = "enhancements/OSAC-1-example/prd.md"
        run_git.side_effect = [f"{path}\0".encode(), b"# PRD\n"]

        self.assertEqual(
            provenance.validate_changed_documents("base", "head"),
            [f"{path}: missing ai-workflow-provenance comment"],
        )
        self.assertEqual(run_git.call_args_list[1].args[0], ["show", f"head:{path}"])


if __name__ == "__main__":
    unittest.main()
