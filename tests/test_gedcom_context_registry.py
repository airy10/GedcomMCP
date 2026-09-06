import unittest
from types import SimpleNamespace

from src.gedcom_mcp.gedcom_context import (
    DEFAULT_DATASET_ID,
    GedcomContext,
    clear_gedcom_contexts,
    get_gedcom_context,
)


class TestGedcomContextRegistry(unittest.TestCase):
    def setUp(self):
        clear_gedcom_contexts()

    def tearDown(self):
        clear_gedcom_contexts()

    def test_contexts_are_isolated_by_dataset_id(self):
        first = get_gedcom_context(dataset_id="first")
        second = get_gedcom_context(dataset_id="second")

        first.gedcom_file_path = "first.ged"
        first.individual_lookup["@I1@"] = object()

        self.assertIs(get_gedcom_context(dataset_id="first"), first)
        self.assertIs(get_gedcom_context(dataset_id="second"), second)
        self.assertEqual(first.gedcom_file_path, "first.ged")
        self.assertEqual(second.gedcom_file_path, None)
        self.assertNotIn("@I1@", second.individual_lookup)

    def test_context_and_caches_survive_lookup(self):
        context = get_gedcom_context(dataset_id="research")
        context.person_details_cache["@I1@"] = "cached"

        resolved = get_gedcom_context(dataset_id="research")

        self.assertIs(resolved, context)
        self.assertEqual(resolved.person_details_cache["@I1@"], "cached")

    def test_fastmcp_sessions_select_isolated_datasets(self):
        first_session = SimpleNamespace()
        second_session = SimpleNamespace()
        first_ctx = SimpleNamespace(session=first_session, session_id="first")
        second_ctx = SimpleNamespace(session=second_session, session_id="second")

        first = get_gedcom_context(first_ctx)
        second = get_gedcom_context(second_ctx)
        first.gedcom_file_path = "first.ged"

        self.assertIs(get_gedcom_context(first_ctx), first)
        self.assertIs(get_gedcom_context(second_ctx), second)
        self.assertEqual(first.gedcom_file_path, "first.ged")
        self.assertIsNone(second.gedcom_file_path)
        self.assertEqual(first_session._gedcom_dataset_id, "session:first")
        self.assertEqual(second_session._gedcom_dataset_id, "session:second")
        self.assertNotIn("gedcom_parser", first_session.__dict__)

    def test_request_metadata_selects_dataset(self):
        request_context = SimpleNamespace(meta={"dataset_id": "from-request"})
        ctx = SimpleNamespace(request_context=request_context)

        selected = get_gedcom_context(ctx)

        self.assertIs(selected, get_gedcom_context(dataset_id="from-request"))
        self.assertIsNot(selected, get_gedcom_context(dataset_id=DEFAULT_DATASET_ID))

    def test_missing_metadata_uses_legacy_default(self):
        selected = get_gedcom_context(SimpleNamespace(request_context=None))

        self.assertIs(selected, get_gedcom_context(dataset_id=DEFAULT_DATASET_ID))


if __name__ == "__main__":
    unittest.main()
