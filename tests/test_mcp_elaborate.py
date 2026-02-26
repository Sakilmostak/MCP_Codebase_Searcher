import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import io
import litellm

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.mcp_elaborate import ContextAnalyzer

class TestContextAnalyzer(unittest.TestCase):

    def setUp(self):
        if 'GOOGLE_API_KEY' in os.environ:
            del os.environ['GOOGLE_API_KEY']
        if 'OPENAI_API_KEY' in os.environ:
            del os.environ['OPENAI_API_KEY']

    def test_init_sets_properties(self):
        analyzer = ContextAnalyzer(api_key="param_key", model_name="gpt-4o", api_base="http://localhost")
        self.assertEqual(analyzer.api_key, "param_key")
        self.assertEqual(analyzer.model_name, "gpt-4o")
        self.assertEqual(analyzer.api_base, "http://localhost")
        self.assertTrue(analyzer.model)

    def test_init_defaults(self):
        analyzer = ContextAnalyzer()
        self.assertEqual(analyzer.model_name, "gemini/gemini-1.5-flash-latest")
        self.assertIsNone(analyzer.api_key)
        self.assertIsNone(analyzer.api_base)
        self.assertTrue(analyzer.model)

    @patch('src.mcp_elaborate.litellm.completion')
    def test_elaborate_on_match_success(self, mock_completion):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Successful elaboration."))]
        mock_completion.return_value = mock_response

        analyzer = ContextAnalyzer(api_key="fake_key", model_name="gpt-4o")
        elaboration = analyzer.elaborate_on_match("path/file.py", 10, "snippet code")
        
        self.assertEqual(elaboration, "Successful elaboration.")
        mock_completion.assert_called_once()
        kwargs = mock_completion.call_args[1]
        self.assertEqual(kwargs['model'], "gpt-4o")
        self.assertEqual(kwargs['api_key'], "fake_key")

    @patch('src.mcp_elaborate.litellm.completion')
    def test_elaborate_on_match_api_error(self, mock_completion):
        mock_completion.side_effect = litellm.exceptions.AuthenticationError("Invalid API key", None, None, None)
        
        analyzer = ContextAnalyzer(api_key="invalid_key", model_name="gpt-4o")
        elaboration = analyzer.elaborate_on_match("test.py", 1, "snippet")
        
        self.assertTrue(elaboration.startswith("Error: API error during elaboration"))

    @patch('src.mcp_elaborate.litellm.completion')
    def test_elaborate_on_match_general_exception(self, mock_completion):
        mock_completion.side_effect = Exception("Unexpected runtime error")
        
        analyzer = ContextAnalyzer(api_key="fake_key")
        elaboration = analyzer.elaborate_on_match("test.py", 1, "snippet")
        
        self.assertTrue(elaboration.startswith("Error: API error during elaboration for test.py:1 (litellm): Exception - Unexpected runtime error"))

    @patch('src.mcp_elaborate.litellm.completion')
    def test_elaborate_on_match_empty_response(self, mock_completion):
        # Empty choices array
        mock_response_empty = MagicMock()
        mock_response_empty.choices = []
        mock_completion.return_value = mock_response_empty
        
        analyzer = ContextAnalyzer(api_key="fake_key")
        elaboration = analyzer.elaborate_on_match("test.py", 1, "snippet")
        
        self.assertEqual(elaboration, "Error: No content returned from API for elaboration")

        # Empty content string
        mock_response_empty_text = MagicMock()
        mock_response_empty_text.choices = [MagicMock(message=MagicMock(content=""))]
        mock_completion.return_value = mock_response_empty_text
        
        elaboration2 = analyzer.elaborate_on_match("test.py", 1, "snippet")
        self.assertEqual(elaboration2, "Error: Elaboration from API was empty or unparsable")

    @patch('src.mcp_elaborate.litellm.completion')
    def test_elaborate_with_full_file_content(self, mock_completion):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Success."))]
        mock_completion.return_value = mock_response

        analyzer = ContextAnalyzer(api_key="fake_key_for_test")
        full_content = "line1\nline2\nsnippet_line\nline4\nline5"
        analyzer.elaborate_on_match("test.py", 3, "snippet_line", full_file_content=full_content, context_window_lines=1)
        
        mock_completion.assert_called_once()
        messages_passed = mock_completion.call_args[1]['messages']
        user_prompt = messages_passed[0]['content']
        
        self.assertIn("File: test.py", user_prompt)
        self.assertIn("Line: 3", user_prompt)
        self.assertIn("snippet_line", user_prompt)
        self.assertIn("Here is a broader context from the file (matched line marked with '>>'):", user_prompt)
        self.assertIn("     2: line2\n>>    3: snippet_line\n     4: line4", user_prompt)

if __name__ == '__main__':
    unittest.main()