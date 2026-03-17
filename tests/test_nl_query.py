"""Tests for M17 — Natural Language Query engine."""
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestNlQuery(unittest.TestCase):
    @patch("engines.ai_engine.get_ai")
    def test_nl_query_returns_dict(self, mock_get_ai):
        mock_ai = MagicMock()
        mock_ai.ask.return_value = "SELECT COUNT(*) FROM systems"
        mock_get_ai.return_value = mock_ai

        # Mock NLQueryEngine.query
        with patch("engines.ai_engine.NLQueryEngine") as MockNLQ:
            mock_nlq_inst = MagicMock()
            mock_nlq_inst.query.return_value = {
                "question": "how many systems?",
                "generated_sql": "SELECT COUNT(*) FROM systems",
                "row_count": 1,
                "results": [{"cnt": 170}],
                "explanation": "There are 170 systems.",
            }
            MockNLQ.return_value = mock_nlq_inst

            from engines.nl_query import nl_query
            result = nl_query("how many systems?")
            self.assertIn("question", result)
            self.assertIn("generated_sql", result)
            self.assertIn("row_count", result)

    def test_nl_query_no_provider(self):
        """When no AI provider is available, should return error dict."""
        from engines.nl_query import nl_query
        with patch("engines.ai_engine.get_ai", side_effect=RuntimeError("No AI provider")):
            result = nl_query("test question")
            self.assertIn("error", result)


class TestRecommendModel(unittest.TestCase):
    @patch("engines.llm_detector.scan_lmstudio_models", return_value=[])
    @patch("engines.llm_detector.scan_ollama_models", return_value=[])
    @patch("engines.llm_detector.recommend_model", return_value=None)
    def test_no_models_found(self, _rec, _ol, _lms):
        from engines.nl_query import recommend_model_for_task
        result = recommend_model_for_task("agentic")
        self.assertIn("error", result)

    @patch("engines.llm_detector.scan_lmstudio_models", return_value=[])
    @patch("engines.llm_detector.scan_ollama_models", return_value=[])
    def test_recommend_with_mock_model(self, _ol, _lms):
        from engines.nl_query import recommend_model_for_task
        from engines.llm_detector import ModelInfo

        mock_model = ModelInfo(
            name="test-model", path="test/path", provider="lmstudio",
            size_gb=5.0, family="qwen3.5-9b", quant="Q8_0",
            fits_vram=True, is_vision=False, is_reasoning=False,
            is_coder=True, tags=["coding", "small"],
        )
        with patch("engines.llm_detector.recommend_model", return_value=mock_model):
            result = recommend_model_for_task("coding", "lmstudio")
            self.assertEqual(result["task"], "coding")
            self.assertEqual(result["provider"], "lmstudio")
            self.assertEqual(result["name"], "test-model")
            self.assertTrue(result["fits_vram"])


class TestFullAiReport(unittest.TestCase):
    @patch("engines.llm_detector.full_model_report")
    def test_report_structure(self, mock_report):
        mock_report.return_value = {
            "lmstudio": {"running": False, "total_models": 0},
            "ollama": {"running": False, "total_models": 0},
            "recommendations": {},
        }
        from engines.nl_query import full_ai_report
        result = full_ai_report()
        self.assertIn("lmstudio", result)
        self.assertIn("ollama", result)

    def test_report_handles_error(self):
        from engines.nl_query import full_ai_report
        with patch("engines.llm_detector.full_model_report", side_effect=Exception("boom")):
            result = full_ai_report()
            self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
