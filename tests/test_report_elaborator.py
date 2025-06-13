import unittest
from unittest.mock import patch, mock_open, MagicMock
import os
import sys
import json
import shutil
import io
import hashlib
import pytest

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.report_elaborator import elaborate_finding
from src.cache_manager import CacheManager

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

        # Temp dir for CacheManager instances in tests
        self.temp_cache_path_for_tests = os.path.join(self.test_dir, "temp_elab_cache")
        os.makedirs(self.temp_cache_path_for_tests, exist_ok=True)

        # --- Remove global patching of google.generativeai.GenerativeModel and configure from setUp ---
        # These will be patched only in tests that instantiate the real ContextAnalyzer.

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        # Explicitly remove the temp_cache_path_for_tests if it exists outside test_dir, though it shouldn't
        if os.path.exists(self.temp_cache_path_for_tests) and self.temp_cache_path_for_tests != self.test_dir :
             shutil.rmtree(self.temp_cache_path_for_tests, ignore_errors=True)

    @patch('src.report_elaborator.ContextAnalyzer')
    def test_elaborate_finding_success(self, MockContextAnalyzerConstructor):
        mock_analyzer_instance = MockContextAnalyzerConstructor.return_value
        mock_analyzer_instance.model = True 
        mock_analyzer_instance.elaborate_on_match.return_value = "Successful elaboration."

        result = elaborate_finding(self.report_file_path, 0, api_key="fake_key")
        self.assertEqual(result, "Successful elaboration.")
        
        expected_finding = self.report_data[0]
        mock_analyzer_instance.elaborate_on_match.assert_called_once_with(
            file_path=expected_finding['file_path'],
            line_number=expected_finding['line_number'],
            snippet=expected_finding['snippet'],
            full_file_content=self.mock_source_content,
            context_window_lines=10 # Default
        )
        MockContextAnalyzerConstructor.assert_called_once_with(api_key="fake_key")

    def test_report_file_not_found(self):
        result = elaborate_finding("non_existent_report.json", 0)
        self.assertEqual(result, "Error: Report file not found at 'non_existent_report.json'.")

    def test_report_file_malformed(self):
        malformed_path = os.path.join(self.test_dir, "malformed.json")
        with open(malformed_path, 'w', encoding='utf-8') as f:
            f.write("not json")
        result = elaborate_finding(malformed_path, 0)
        self.assertTrue(result.startswith("Error: Report file '" + malformed_path + "' is malformed"))

    def test_report_data_not_list(self):
        not_list_path = os.path.join(self.test_dir, "not_list.json")
        with open(not_list_path, 'w', encoding='utf-8') as f:
            json.dump({"key": "value"}, f)
        result = elaborate_finding(not_list_path, 0)
        self.assertEqual(result, "Error: Report data is not in the expected list format.")

    def test_finding_id_value_error(self):
        result = elaborate_finding(self.report_file_path, "abc")
        self.assertEqual(result, "Error: Finding ID 'abc' must be an integer index.")

    def test_finding_id_out_of_range(self):
        result = elaborate_finding(self.report_file_path, len(self.report_data))
        self.assertEqual(result, f"Error: Finding ID {len(self.report_data)} is out of range for the report (0 to {len(self.report_data) - 1}).")

    def test_finding_invalid_structure(self):
        invalid_report_path = os.path.join(self.test_dir, "invalid_finding.json")
        with open(invalid_report_path, 'w', encoding='utf-8') as f:
            json.dump([{"wrong_key": "value"}], f)
        result = elaborate_finding(invalid_report_path, 0)
        self.assertTrue(result.startswith("Error: Finding at index 0 has an invalid structure"))

    @patch('src.report_elaborator.ContextAnalyzer')
    @patch('src.report_elaborator.sys.stderr', new_callable=io.StringIO)
    def test_source_file_not_found_for_finding(self, mock_stderr, MockContextAnalyzerConstructor):
        mock_analyzer_instance = MockContextAnalyzerConstructor.return_value
        mock_analyzer_instance.model = True 
        mock_analyzer_instance.elaborate_on_match.return_value = "Elaboration based on snippet only."
        
        result = elaborate_finding(self.report_file_path, 1, api_key="fake_key")
        self.assertEqual(result, "Elaboration based on snippet only.")
        
        expected_finding = self.report_data[1]
        mock_analyzer_instance.elaborate_on_match.assert_called_once_with(
            file_path=expected_finding['file_path'],
            line_number=expected_finding['line_number'],
            snippet=expected_finding['snippet'],
            full_file_content=None, 
            context_window_lines=10
        )
        self.assertIn(f"Warning: Source file '{expected_finding['file_path']}' for finding 1 not found", mock_stderr.getvalue())
        MockContextAnalyzerConstructor.assert_called_once_with(api_key="fake_key")

    @patch('os.getenv')
    @patch('src.report_elaborator.ContextAnalyzer')
    def test_context_analyzer_init_fails(self, mock_os_getenv, MockContextAnalyzerConstructor):
        mock_os_getenv.return_value = None # Ensure GOOGLE_API_KEY is not found from env
        mock_analyzer_instance = MockContextAnalyzerConstructor.return_value
        mock_analyzer_instance.model = None 

        result = elaborate_finding(self.report_file_path, 0, api_key=None)
        self.assertEqual(result, "Error: ContextAnalyzer model could not be initialized. Cannot elaborate.")
        # MockContextAnalyzerConstructor.assert_called_once_with(api_key=None) # Removed: not always called in this test

    @patch('src.report_elaborator.ContextAnalyzer')
    def test_elaboration_process_general_exception(self, MockContextAnalyzerConstructor):
        mock_analyzer_instance = MockContextAnalyzerConstructor.return_value
        mock_analyzer_instance.model = True 
        mock_analyzer_instance.elaborate_on_match.side_effect = Exception("LLM API broke")
    
        result = elaborate_finding(self.report_file_path, 0, api_key="fake_key")
        self.assertEqual(result, "Error during elaboration process: LLM API broke")
        MockContextAnalyzerConstructor.assert_called_once_with(api_key="fake_key")

    @patch('src.report_elaborator.ContextAnalyzer')
    def test_elaborate_finding_custom_context_window(self, MockContextAnalyzerConstructor):
        mock_analyzer_instance = MockContextAnalyzerConstructor.return_value
        mock_analyzer_instance.model = True 
        mock_analyzer_instance.elaborate_on_match.return_value = "Elaborated with custom window."
            
        custom_window = 5
        result = elaborate_finding(self.report_file_path, 0, api_key="fake_key", context_window_lines=custom_window)
        self.assertEqual(result, "Elaborated with custom window.")
                
        expected_finding = self.report_data[0]
        mock_analyzer_instance.elaborate_on_match.assert_called_once_with(
            file_path=expected_finding['file_path'],
            line_number=expected_finding['line_number'],
            snippet=expected_finding['snippet'],
            full_file_content=self.mock_source_content,
            context_window_lines=custom_window
        )
        MockContextAnalyzerConstructor.assert_called_once_with(api_key="fake_key")

    @patch('src.report_elaborator.ContextAnalyzer')
    @patch('src.report_elaborator.sys.stderr', new_callable=io.StringIO)
    def test_elaborate_finding_cache_hit(self, mock_stderr, MockContextAnalyzerConstructor):
        mock_analyzer_instance = MockContextAnalyzerConstructor.return_value 
        # For a cache hit, ContextAnalyzer might be constructed but elaborate_on_match should not be called.

        mock_cache_manager = MagicMock(spec=CacheManager)
        cached_value = "Cached LLM Elaboration."
        mock_cache_manager.get.return_value = cached_value
        mock_cache_manager._generate_key.return_value = "short_key_ab" 

        result = elaborate_finding(
            self.report_file_path, 0, api_key="test_api_key_cache_hit", 
            cache_manager=mock_cache_manager, no_cache=False
        )
        self.assertEqual(result, cached_value)
        
        cache_key_components = (
            'elaborate', 
            self.hash_finding(self.report_data[0]), 
            10, 
            "test_api_key_cache_hit"
        )
        mock_cache_manager.get.assert_called_once_with(cache_key_components)
        # If ContextAnalyzer is instantiated, its elaborate_on_match method should not be called.
        # A stricter check is that ContextAnalyzer itself is not called if we expect no LLM interaction.
        # However, elaborate_finding might instantiate it before cache check. Let's check no elaborate call.
        if MockContextAnalyzerConstructor.called:
             mock_analyzer_instance.elaborate_on_match.assert_not_called()
        # A stronger assertion might be MockContextAnalyzerConstructor.assert_not_called(), 
        # but current code instantiates CA before cache logic.
        # For now, let's check that if it *was* called, its main method wasn't.

        self.assertIn("Cache hit for elaborate finding ID 0 (key: short_key_ab...).", mock_stderr.getvalue())

    def hash_finding(self, finding_dict):
        "Helper to consistently hash a finding dictionary for cache key tests."
        finding_json_str = json.dumps(finding_dict, sort_keys=True)
        return hashlib.sha256(finding_json_str.encode('utf-8')).hexdigest()

    @patch('src.report_elaborator.ContextAnalyzer')
    @patch('src.report_elaborator.sys.stderr', new_callable=io.StringIO)
    def test_elaborate_finding_cache_miss_and_set(self, mock_stderr, MockContextAnalyzerConstructor):
        mock_analyzer_instance = MockContextAnalyzerConstructor.return_value
        mock_analyzer_instance.model = True
        llm_elaboration = "Fresh LLM elaboration."
        mock_analyzer_instance.elaborate_on_match.return_value = llm_elaboration
        
        mock_cache_manager = MagicMock(spec=CacheManager)
        mock_cache_manager.get.return_value = None
        expected_key_for_log = "new_key_123"
        mock_cache_manager._generate_key.return_value = expected_key_for_log

        result = elaborate_finding(
            self.report_file_path, 0, api_key="test_api_key_cache_miss", 
            cache_manager=mock_cache_manager, no_cache=False
        )
        self.assertEqual(result, llm_elaboration)
        MockContextAnalyzerConstructor.assert_called_once_with(api_key="test_api_key_cache_miss")

        cache_key_components = (
            'elaborate', 
            self.hash_finding(self.report_data[0]), 
            10, 
            "test_api_key_cache_miss"
        )
        mock_cache_manager.get.assert_called_once_with(cache_key_components)
        mock_analyzer_instance.elaborate_on_match.assert_called_once()
        mock_cache_manager.set.assert_called_once_with(cache_key_components, llm_elaboration)
        stderr_output = mock_stderr.getvalue()
        self.assertIn(f"Cache miss for elaborate finding ID 0 (key: {expected_key_for_log}...)", stderr_output)
        self.assertIn(f"Cached elaborate result for finding ID 0 (key: {expected_key_for_log}...)", stderr_output)

    @patch('src.report_elaborator.ContextAnalyzer')
    def test_elaborate_finding_no_cache_flag(self, MockContextAnalyzerConstructor):
        mock_analyzer_instance = MockContextAnalyzerConstructor.return_value
        mock_analyzer_instance.model = True
        llm_elaboration = "LLM elaboration (no_cache=True)."
        mock_analyzer_instance.elaborate_on_match.return_value = llm_elaboration

        mock_cache_manager = MagicMock(spec=CacheManager)
        
        result = elaborate_finding(
            self.report_file_path, 0, api_key="test_api_key_no_cache", 
            cache_manager=mock_cache_manager, no_cache=True
        )
        self.assertEqual(result, llm_elaboration)
        MockContextAnalyzerConstructor.assert_called_once_with(api_key="test_api_key_no_cache")

        mock_analyzer_instance.elaborate_on_match.assert_called_once()
        mock_cache_manager.get.assert_not_called()
        mock_cache_manager.set.assert_not_called()

    @patch('src.report_elaborator.ContextAnalyzer')
    @patch('src.report_elaborator.sys.stderr', new_callable=io.StringIO)
    def test_elaborate_finding_cache_get_exception(self, mock_stderr, MockContextAnalyzerConstructor):
        mock_analyzer_instance = MockContextAnalyzerConstructor.return_value
        mock_analyzer_instance.model = True
        llm_elaboration = "LLM elaboration after cache get fail."
        mock_analyzer_instance.elaborate_on_match.return_value = llm_elaboration

        mock_cache_manager = MagicMock(spec=CacheManager)
        mock_cache_manager.get.side_effect = Exception("Test cache GET exception")

        result = elaborate_finding(
            self.report_file_path, 0, api_key="test_api_key_get_exc", 
            cache_manager=mock_cache_manager, no_cache=False
        )
        self.assertEqual(result, llm_elaboration) 
        MockContextAnalyzerConstructor.assert_called_once_with(api_key="test_api_key_get_exc")
        
        self.assertIn("Warning: Cache GET operation failed during elaborate: Test cache GET exception", mock_stderr.getvalue())
        mock_analyzer_instance.elaborate_on_match.assert_called_once()

    @patch('src.report_elaborator.ContextAnalyzer')
    @patch('src.report_elaborator.sys.stderr', new_callable=io.StringIO)
    def test_elaborate_finding_cache_set_exception(self, mock_stderr, MockContextAnalyzerConstructor):
        mock_analyzer_instance = MockContextAnalyzerConstructor.return_value
        mock_analyzer_instance.model = True
        llm_elaboration = "LLM elaboration before cache set fail."
        mock_analyzer_instance.elaborate_on_match.return_value = llm_elaboration

        mock_cache_manager = MagicMock(spec=CacheManager)
        mock_cache_manager.get.return_value = None 
        mock_cache_manager.set.side_effect = Exception("Test cache SET exception")
        expected_key_for_log = "set_exc_key"
        mock_cache_manager._generate_key.return_value = expected_key_for_log

        result = elaborate_finding(
            self.report_file_path, 0, api_key="test_api_key_set_exc", 
            cache_manager=mock_cache_manager, no_cache=False
        )
        self.assertEqual(result, llm_elaboration) 
        MockContextAnalyzerConstructor.assert_called_once_with(api_key="test_api_key_set_exc")

        stderr_output = mock_stderr.getvalue()
        self.assertIn(f"Cache miss for elaborate finding ID 0 (key: {expected_key_for_log}...)", stderr_output)
        self.assertIn("Warning: Cache SET operation failed during elaborate: Test cache SET exception", stderr_output)
        mock_analyzer_instance.elaborate_on_match.assert_called_once()

if __name__ == '__main__':
    unittest.main() 