import tempfile
import unittest
from pathlib import Path

from infra_agents.rag import LocalKnowledgeBase


class RagTests(unittest.TestCase):
    def test_retrieve_returns_relevant_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "modules.md").write_text("terraform-aws-modules/vpc/aws\nterraform-aws-modules/rds/aws\n", encoding="utf-8")
            (root / "providers.md").write_text("hashicorp/aws ~> 5.0\n", encoding="utf-8")

            kb = LocalKnowledgeBase(root=root)
            hits = kb.retrieve("aws modules vpc rds", top_k=2)

            self.assertGreaterEqual(len(hits), 1)
            self.assertEqual(hits[0].source, "modules.md")

    def test_render_context_includes_source_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "naming-and-tagging.md").write_text("owner\ncost_center\n", encoding="utf-8")
            kb = LocalKnowledgeBase(root=root)

            hits = kb.retrieve("tags owner cost_center", top_k=1)
            context = kb.render_context(hits)

            self.assertIn("### naming-and-tagging.md", context)
            self.assertIn("owner", context)


if __name__ == "__main__":
    unittest.main()
