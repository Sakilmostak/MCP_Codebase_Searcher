import unittest
from unittest.mock import patch, mock_open, MagicMock
import os
import sys
import json
import shutil
import io

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.report_elaborator import elaborate_finding
# We will mock ContextAnalyzer from src.mcp_elaborate

class TestReportElaborator(unittest.TestCase):
    def setUp(self):
        self.test_dir = "temp_test_report_elab_dir"
        os.makedirs(self.test_dir, exist_ok=True)

        # Mock source file content
        self.mock_source_content = "line1\ndef func():\n  important_code_line\nline4"
        self.mock_source_file_path = os.path.join(self.test_dir, "mock_source.py")
        with open(self.mock_source_file_path, 'w', encoding='utf-8') as f:
            f.write(self.mock_source_content)

        # Sample report data
        self.report_data = [
            {
                'file_path': self.mock_source_file_path,
                'line_number': 3,
                'snippet': 'snippet for finding 0',
                'match_text': 'important_code_line'
            },
            {
                'file_path': "another_mock_source.py", # This file won't exist for one test
                'line_number': 1,
                'snippet': 'snippet for finding 1',
                'match_text': 'another_match'
            }
        ]
        self.report_file_path = os.path.join(self.test_dir, "report.json")
        with open(self.report_file_path, 'w', encoding='utf-8') as f:
            json.dump(self.report_data, f)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    @patch('src.report_elaborator.ContextAnalyzer')
    def test_elaborate_finding_success(self, MockContextAnalyzer):
        mock_analyzer_instance = MockContextAnalyzer.return_value
        mock_analyzer_instance.model = True # Simulate successful model init
        mock_analyzer_instance.elaborate_on_match.return_value = "Successful elaboration."

        result = elaborate_finding(self.report_file_path, 0, api_key="fake_key")
        self.assertEqual(result, "Successful elaboration.")
        
        # Check that ContextAnalyzer was called with correct args
        expected_finding = self.report_data[0]
        mock_analyzer_instance.elaborate_on_match.assert_called_once_with(
            file_path=expected_finding['file_path'],
            line_number=expected_finding['line_number'],
            snippet=expected_finding['snippet'],
            full_file_content=self.mock_source_content,
            context_window_lines=10 # Default
        )
        MockContextAnalyzer.assert_called_once_with(api_key="fake_key")

    def test_report_file_not_found(self):
        result = elaborate_finding("non_existent_report.json", 0)
        self.assertTrue(result.startswith("Error: Report file not found"))

    def test_invalid_json_report(self):
        invalid_json_path = os.path.join(self.test_dir, "invalid.json")
        with open(invalid_json_path, 'w', encoding='utf-8') as f:
            f.write("this is not json")
        result = elaborate_finding(invalid_json_path, 0)
        self.assertTrue(result.startswith("Error: Could not decode JSON"))

    def test_report_not_a_list(self):
        not_list_report_path = os.path.join(self.test_dir, "not_list.json")
        with open(not_list_report_path, 'w', encoding='utf-8') as f:
            json.dump({"not": "a list"}, f)
        result = elaborate_finding(not_list_report_path, 0)
        self.assertEqual(result, "Error: Report data is not in the expected list format.")

    def test_finding_id_out_of_range(self):
        result = elaborate_finding(self.report_file_path, len(self.report_data))
        self.assertTrue(result.startswith("Error: Finding ID"))
        self.assertIn("out of range", result)

    def test_finding_id_invalid_type(self):
        result = elaborate_finding(self.report_file_path, "abc")
        self.assertEqual(result, "Error: Finding ID 'abc' must be an integer index.")

    def test_finding_invalid_structure(self):
        faulty_data = [{ 'file_path': 'a', 'line_number': 1}] # Missing snippet, match_text
        faulty_report_path = os.path.join(self.test_dir, "faulty.json")
        with open(faulty_report_path, 'w', encoding='utf-8') as f:
            json.dump(faulty_data, f)
        result = elaborate_finding(faulty_report_path, 0)
        self.assertTrue(result.startswith("Error: Finding at index 0 has an invalid structure"))

    @patch('src.report_elaborator.ContextAnalyzer')
    @patch('src.report_elaborator.sys.stderr', new_callable=io.StringIO)
    def test_source_file_not_found_for_finding(self, mock_stderr, MockContextAnalyzer):
        mock_analyzer_instance = MockContextAnalyzer.return_value
        mock_analyzer_instance.model = True
        mock_analyzer_instance.elaborate_on_match.return_value = "Elaboration based on snippet only."

        # Finding 1 refers to "another_mock_source.py" which doesn't exist
        result = elaborate_finding(self.report_file_path, 1, api_key="fake_key")
        self.assertEqual(result, "Elaboration based on snippet only.")
        
        expected_finding = self.report_data[1]
        mock_analyzer_instance.elaborate_on_match.assert_called_once_with(
            file_path=expected_finding['file_path'],
            line_number=expected_finding['line_number'],
            snippet=expected_finding['snippet'],
            full_file_content=None, # Should be None as source file not found
            context_window_lines=10
        )
        self.assertIn(f"Warning: Source file '{expected_finding['file_path']}' for finding 1 not found", mock_stderr.getvalue())

    @patch('src.report_elaborator.ContextAnalyzer')
    def test_context_analyzer_init_fails(self, MockContextAnalyzer):
        mock_analyzer_instance = MockContextAnalyzer.return_value
        mock_analyzer_instance.model = None # Simulate model init failure (e.g. no API key)
        # ContextAnalyzer __init__ prints to its own stderr, elaborate_finding returns an error string.
        
        result = elaborate_finding(self.report_file_path, 0, api_key=None) # No API key passed
        self.assertEqual(result, "Error: ContextAnalyzer model could not be initialized. Cannot elaborate.")
        MockContextAnalyzer.assert_called_once_with(api_key=None)

    @patch('src.report_elaborator.ContextAnalyzer')
    def test_elaboration_process_general_exception(self, MockContextAnalyzer):
        mock_analyzer_instance = MockContextAnalyzer.return_value
        mock_analyzer_instance.model = True
        mock_analyzer_instance.elaborate_on_match.side_effect = Exception("LLM API broke")

        result = elaborate_finding(self.report_file_path, 0, api_key="fake_key")
        self.assertEqual(result, "Error during elaboration process: LLM API broke")

    def test_elaborate_finding_custom_context_window(self):
        # This test might be better if we can verify the content passed to ContextAnalyzer 
        # without a full mock if ContextAnalyzer itself is reliable.
        # For now, we'll mock to check the arg.
        with patch('src.report_elaborator.ContextAnalyzer') as MockCA:
            mock_instance = MockCA.return_value
            mock_instance.model = True
            mock_instance.elaborate_on_match.return_value = "Elaborated with custom window."

            custom_window = 5
            result = elaborate_finding(self.report_file_path, 0, api_key="fake_key", context_window_lines=custom_window)
            self.assertEqual(result, "Elaborated with custom window.")
            
            expected_finding = self.report_data[0]
            mock_instance.elaborate_on_match.assert_called_once_with(
                file_path=expected_finding['file_path'],
                line_number=expected_finding['line_number'],
                snippet=expected_finding['snippet'],
                full_file_content=self.mock_source_content,
                context_window_lines=custom_window
            )

if __name__ == '__main__':
    unittest.main() 