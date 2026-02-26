import unittest
from unittest.mock import patch, mock_open, MagicMock
import os
import sys
import json
import shutil
import io
import hashlib
import tempfile

import src.report_elaborator # MODIFIED: Changed import

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.report_elaborator import elaborate_finding
from src.cache_manager import CacheManager
from src.mcp_elaborate import ContextAnalyzer

DUMMY_API_KEY = "TEST_API_KEY_VALID_FORMAT"

# This will be a common mock for tests not intending to hit the actual Google API
# It prevents the actual genai.GenerativeModel() call within ContextAnalyzer.__init__
# It prevents the actual genai.GenerativeModel() call within ContextAnalyzer.__init__
# (No longer required because we use litellm and mock ContextAnalyzer instead)

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

    def test_elaborate_finding_success(self):
        
        # Configure the mock generative model instance (general defensive measure)
        mock_response = MagicMock()
        mock_response.prompt_feedback.block_reason = None
        mock_response.text = "Defensive Mocked LLM Text from genai.GenerativeModel"

        # Use patch as a context manager for ContextAnalyzer
        with patch.object(src.report_elaborator, 'ContextAnalyzer', autospec=True) as MockedCA_at_usage_point:
            primary_mock_analyzer_instance = MockedCA_at_usage_point.return_value
            primary_mock_analyzer_instance.model = True 
            primary_mock_analyzer_instance.api_key = DUMMY_API_KEY
            primary_mock_analyzer_instance.elaborate_on_match.return_value = "Successful elaboration."

            result = src.report_elaborator.elaborate_finding(self.report_file_path, 0, api_key=DUMMY_API_KEY)
            self.assertEqual(result, "Successful elaboration.")
            
            expected_finding = self.report_data[0]
            
            MockedCA_at_usage_point.assert_called_once_with(api_key=DUMMY_API_KEY, model_name='gemini/gemini-1.5-flash-latest', api_base=None)
            primary_mock_analyzer_instance.elaborate_on_match.assert_called_once_with(
                file_path=expected_finding['file_path'],
                line_number=expected_finding['line_number'],
                snippet=expected_finding['snippet'],
                full_file_content=self.mock_source_content,
                context_window_lines=10 # Default
            )

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

    @patch.object(src.report_elaborator, 'ContextAnalyzer', autospec=True)
    @patch('src.report_elaborator.logging.warning')
    def test_source_file_not_found_for_finding(self, mock_logging_warning, MockedContextAnalyzer):
        mock_analyzer_instance = MockedContextAnalyzer.return_value
        mock_analyzer_instance.model = True 
        mock_analyzer_instance.api_key = DUMMY_API_KEY
        mock_analyzer_instance.elaborate_on_match.return_value = "Elaboration based on snippet only."
        
        result = elaborate_finding(self.report_file_path, 1, api_key=DUMMY_API_KEY)
        self.assertEqual(result, "Elaboration based on snippet only.")
        
        expected_finding = self.report_data[1]
        mock_analyzer_instance.elaborate_on_match.assert_called_once_with(
            file_path=expected_finding['file_path'],
            line_number=expected_finding['line_number'],
            snippet=expected_finding['snippet'],
            full_file_content=None, 
            context_window_lines=10
        )
        expected_log_message = f"Source file '{expected_finding['file_path']}' for finding 1 not found. Proceeding with snippet only."
        called_with_expected = False
        for call_args in mock_logging_warning.call_args_list:
            if call_args[0][0] == expected_log_message:
                called_with_expected = True
                break
        self.assertTrue(called_with_expected, f"Expected log message not found: {expected_log_message}")
        MockedContextAnalyzer.assert_called_once_with(api_key=DUMMY_API_KEY, model_name='gemini/gemini-1.5-flash-latest', api_base=None)

    # Reverting to decorator-based patching, targeting mcp_elaborate for ContextAnalyzer and its deps
    @patch.object(src.report_elaborator, 'ContextAnalyzer', autospec=True)
    def test_context_analyzer_init_fails(self, MockedContextAnalyzer):
        mock_ca_instance = MockedContextAnalyzer.return_value
        mock_ca_instance.model = None
        mock_ca_instance.api_key = None 
        mock_ca_instance.elaborate_on_match = MagicMock()

        result = src.report_elaborator.elaborate_finding(self.report_file_path, 0, api_key=None)
        
        MockedContextAnalyzer.assert_called_once_with(api_key=None, model_name='gemini/gemini-1.5-flash-latest', api_base=None)
        self.assertEqual(result, "Error: ContextAnalyzer model could not be initialized. Cannot elaborate.")
        mock_ca_instance.elaborate_on_match.assert_not_called()

    @patch.object(src.report_elaborator, 'ContextAnalyzer', autospec=True)
    def test_elaboration_process_general_exception(self, MockedContextAnalyzer):
        mock_analyzer_instance = MockedContextAnalyzer.return_value
        mock_analyzer_instance.model = True 
        mock_analyzer_instance.api_key = DUMMY_API_KEY
        mock_analyzer_instance.elaborate_on_match.side_effect = Exception("LLM API broke")
    
        result = elaborate_finding(self.report_file_path, 0, api_key=DUMMY_API_KEY)
        self.assertEqual(result, "Error during elaboration process: LLM API broke")
        MockedContextAnalyzer.assert_called_once_with(api_key=DUMMY_API_KEY, model_name='gemini/gemini-1.5-flash-latest', api_base=None)

    @patch.object(src.report_elaborator, 'ContextAnalyzer', autospec=True)
    def test_elaborate_finding_custom_context_window(self, MockedContextAnalyzer):
        mock_analyzer_instance = MockedContextAnalyzer.return_value
        mock_analyzer_instance.model = True 
        mock_analyzer_instance.api_key = DUMMY_API_KEY
        mock_analyzer_instance.elaborate_on_match.return_value = "Elaborated with custom window."
            
        custom_window = 5
        result = elaborate_finding(self.report_file_path, 0, api_key=DUMMY_API_KEY, context_window_lines=custom_window)
        self.assertEqual(result, "Elaborated with custom window.")
                
        expected_finding = self.report_data[0]
        mock_analyzer_instance.elaborate_on_match.assert_called_once_with(
            file_path=expected_finding['file_path'],
            line_number=expected_finding['line_number'],
            snippet=expected_finding['snippet'],
            full_file_content=self.mock_source_content,
            context_window_lines=custom_window
        )
        MockedContextAnalyzer.assert_called_once_with(api_key=DUMMY_API_KEY, model_name='gemini/gemini-1.5-flash-latest', api_base=None)

    @patch.object(src.report_elaborator, 'ContextAnalyzer', autospec=True)
    @patch('src.report_elaborator.logging.info')
    def test_elaborate_finding_cache_hit(self, mock_logging_info, MockedContextAnalyzer):
        mock_analyzer_instance = MockedContextAnalyzer.return_value 
        mock_analyzer_instance.model = True
        mock_analyzer_instance.api_key = DUMMY_API_KEY

        mock_cache_manager = MagicMock(spec=CacheManager)
        cached_value = "Cached LLM Elaboration."
        mock_cache_manager.get.return_value = cached_value

        result = elaborate_finding(
            self.report_file_path, 0, api_key=DUMMY_API_KEY, 
            cache_manager=mock_cache_manager, no_cache=False
        )
        self.assertEqual(result, cached_value)
        
        cache_key_components = (
            'elaborate', 
            self.hash_finding(self.report_data[0]), 
            10, 
            DUMMY_API_KEY,
            'gemini/gemini-1.5-flash-latest',
            None
        )
        mock_cache_manager.get.assert_called_once_with(cache_key_components)
        MockedContextAnalyzer.assert_not_called()
        mock_analyzer_instance.elaborate_on_match.assert_not_called()

        expected_log_message_checking_cache = f"Checking cache for elaborate finding ID 0 (Operation: 'elaborate')"
        found_checking_log = False
        for call_args in mock_logging_info.call_args_list:
            if call_args[0][0] == expected_log_message_checking_cache:
                found_checking_log = True
                break
        self.assertTrue(found_checking_log, f"Expected log message for checking cache not found: {expected_log_message_checking_cache}")

    def hash_finding(self, finding_dict):
        "Helper to consistently hash a finding dictionary for cache key tests."
        finding_json_str = json.dumps(finding_dict, sort_keys=True)
        return hashlib.sha256(finding_json_str.encode('utf-8')).hexdigest()

    @patch.object(src.report_elaborator, 'ContextAnalyzer', autospec=True)
    @patch('src.report_elaborator.logging.info')
    def test_elaborate_finding_cache_miss_and_set(self, mock_logging_info, MockedContextAnalyzer):
        mock_analyzer_instance = MockedContextAnalyzer.return_value
        mock_analyzer_instance.model = True
        mock_analyzer_instance.api_key = DUMMY_API_KEY
        llm_elaboration = "Fresh LLM elaboration."
        mock_analyzer_instance.elaborate_on_match.return_value = llm_elaboration
        
        mock_cache_manager = MagicMock(spec=CacheManager)
        mock_cache_manager.get.return_value = None 

        result = elaborate_finding(
            self.report_file_path, 0, api_key=DUMMY_API_KEY, 
            cache_manager=mock_cache_manager, no_cache=False
        )
        self.assertEqual(result, llm_elaboration)

        MockedContextAnalyzer.assert_called_once_with(api_key=DUMMY_API_KEY, model_name='gemini/gemini-1.5-flash-latest', api_base=None)
        mock_analyzer_instance.elaborate_on_match.assert_called_once()
        
        cache_key_components = (
            'elaborate', 
            self.hash_finding(self.report_data[0]), 
            10, 
            DUMMY_API_KEY,
            'gemini/gemini-1.5-flash-latest',
            None
        )
        mock_cache_manager.get.assert_called_once_with(cache_key_components)
        mock_cache_manager.set.assert_called_once_with(cache_key_components, llm_elaboration)

        found_checking_log = False
        found_stored_log = False
        expected_log_checking_cache = "Checking cache for elaborate finding ID 0 (Operation: 'elaborate')"
        expected_log_cache_set = f"Stored elaborate result in cache for finding ID 0 (Operation: '{cache_key_components[0]}')"

        for call_args in mock_logging_info.call_args_list:
            log_msg = call_args[0][0]
            if log_msg == expected_log_checking_cache:
                found_checking_log = True
            if log_msg == expected_log_cache_set:
                found_stored_log = True
        
        self.assertTrue(found_checking_log, "Log for checking cache not found")
        self.assertTrue(found_stored_log, "Log for storing result in cache not found")

    @patch.object(src.report_elaborator, 'ContextAnalyzer', autospec=True)
    @patch('src.report_elaborator.logging.warning')
    def test_elaborate_finding_cache_get_exception(self, mock_logging_warning, MockedContextAnalyzer):
        mock_analyzer_instance = MockedContextAnalyzer.return_value
        mock_analyzer_instance.model = True # Mock that model is initialized
        mock_analyzer_instance.api_key = "test_api_key_get_exc"
        llm_elaboration_fallback = "LLM elaboration on GET exception."
        mock_analyzer_instance.elaborate_on_match.return_value = llm_elaboration_fallback

        mock_cache_manager = MagicMock(spec=CacheManager)
        mock_cache_manager.get.side_effect = Exception("Test cache GET exception")

        result = elaborate_finding(
            self.report_file_path, 0, api_key="test_api_key_get_exc", 
            cache_manager=mock_cache_manager, no_cache=False
        )
        
        # Should fallback to LLM call
        self.assertEqual(result, llm_elaboration_fallback)
        MockedContextAnalyzer.assert_called_once_with(api_key="test_api_key_get_exc", model_name='gemini/gemini-1.5-flash-latest', api_base=None)
        mock_analyzer_instance.elaborate_on_match.assert_called_once() # LLM call should happen

        expected_log_message = "Cache GET operation failed during elaborate finding ID 0: Test cache GET exception"
        found_log = False
        for call_args in mock_logging_warning.call_args_list:
            if expected_log_message in call_args[0][0]: 
                found_log = True
                break
        self.assertTrue(found_log, 
                        f"Expected log message containing '{expected_log_message}' not found. Actual logs: {[c[0][0] for c in mock_logging_warning.call_args_list]}")

    @patch.object(src.report_elaborator, 'ContextAnalyzer', autospec=True)
    @patch('src.report_elaborator.logging.warning')
    def test_elaborate_finding_cache_set_exception(self, mock_logging_warning, MockedContextAnalyzer):
        mock_analyzer_instance = MockedContextAnalyzer.return_value
        mock_analyzer_instance.model = True
        mock_analyzer_instance.api_key = "test_api_key_set_exc"
        llm_elaboration = "Fresh LLM elaboration for set exc test."
        mock_analyzer_instance.elaborate_on_match.return_value = llm_elaboration
        
        mock_cache_manager = MagicMock(spec=CacheManager)
        mock_cache_manager.get.return_value = None 
        mock_cache_manager.set.side_effect = Exception("Test cache SET exception")

        elaborate_finding(
            self.report_file_path, 0, api_key="test_api_key_set_exc", 
            cache_manager=mock_cache_manager, no_cache=False
        )
        
        MockedContextAnalyzer.assert_called_once_with(api_key="test_api_key_set_exc", model_name='gemini/gemini-1.5-flash-latest', api_base=None)
        mock_analyzer_instance.elaborate_on_match.assert_called_once()

        expected_log_message = "Cache SET operation failed during elaborate finding ID 0: Test cache SET exception"
        
        found_log = False
        for call_args in mock_logging_warning.call_args_list:
            if expected_log_message in call_args[0][0]:
                found_log = True
                break
        self.assertTrue(found_log, 
                        f"Expected log message containing '{expected_log_message}' not found. Actual logs: {[c[0][0] for c in mock_logging_warning.call_args_list]}")

    @patch.object(src.report_elaborator, 'ContextAnalyzer', autospec=True)
    @patch('src.report_elaborator.logging.info')
    def test_elaborate_finding_no_cache_flag_prevents_set(self, mock_logging_info, MockedContextAnalyzer):
        mock_analyzer_instance = MockedContextAnalyzer.return_value
        mock_analyzer_instance.model = True
        mock_analyzer_instance.api_key = "test_api_key_no_cache_set"
        llm_elaboration = "Fresh LLM elaboration (no_cache set True)."
        mock_analyzer_instance.elaborate_on_match.return_value = llm_elaboration
        
        mock_cache_manager = MagicMock(spec=CacheManager)

        result = elaborate_finding(
            self.report_file_path, 0, api_key="test_api_key_no_cache_set", 
            cache_manager=mock_cache_manager, 
            no_cache=True 
        )
        self.assertEqual(result, llm_elaboration)
        
        mock_cache_manager.get.assert_not_called() 
        mock_cache_manager.set.assert_not_called() 
        
        MockedContextAnalyzer.assert_called_once_with(api_key="test_api_key_no_cache_set", model_name='gemini/gemini-1.5-flash-latest', api_base=None)
        mock_analyzer_instance.elaborate_on_match.assert_called_once()
        
        for call_args in mock_logging_info.call_args_list:
            log_message = call_args[0][0]
            self.assertNotIn("Checking cache for elaborate", log_message, "Cache check log found when no_cache=True")
            self.assertNotIn("Stored elaborate result in cache", log_message, "Cache store log found when no_cache=True")

# New Test Class for Caching with Real CacheManager
class TestElaboratorCachingWithRealCache(unittest.TestCase):
    def setUp(self):
        self.test_files_dir = tempfile.mkdtemp(prefix="elab_files_")
        self.temp_cache_dir = tempfile.mkdtemp(prefix="elab_cache_")
        self.cache_manager = CacheManager(cache_dir=self.temp_cache_dir, expiry_seconds=300) # Use real CacheManager

        self.mock_source_content = "def important_function():\n    print(\"Hello from source\")"
        self.mock_source_file_path = os.path.join(self.test_files_dir, "source_code.py")
        with open(self.mock_source_file_path, 'w', encoding='utf-8') as f:
            f.write(self.mock_source_content)

        self.report_data = [
            {
                'file_path': self.mock_source_file_path, # Relative path in report, resolved by elaborate_finding
                'line_number': 1,
                'snippet': 'def >>>important_function<<<():',
                'match_text': 'important_function'
            }
        ]
        self.report_file_path = os.path.join(self.test_files_dir, "findings_report.json")
        with open(self.report_file_path, 'w', encoding='utf-8') as f:
            json.dump(self.report_data, f)

    def tearDown(self):
        if self.cache_manager:
            self.cache_manager.close()
        if os.path.exists(self.temp_cache_dir):
            shutil.rmtree(self.temp_cache_dir)
        if os.path.exists(self.test_files_dir):
            shutil.rmtree(self.test_files_dir)

    @patch.object(src.report_elaborator, 'ContextAnalyzer', autospec=True)
    def test_elaborate_cache_hit_and_miss(self, MockedContextAnalyzer):
        mock_analyzer_instance = MockedContextAnalyzer.return_value
        mock_analyzer_instance.model = True # Ensure the mocked analyzer thinks it has a model
        mock_analyzer_instance.api_key = "key_for_elaborate_cache_test"
        mock_elaboration_text = "This is a mock LLM elaboration for caching test."
        mock_analyzer_instance.elaborate_on_match.return_value = mock_elaboration_text

        test_api_key = "key_for_elaborate_cache_test"

        # First call: Cache Miss
        result1 = elaborate_finding(
            report_path=self.report_file_path,
            finding_id=0,
            api_key=test_api_key,
            cache_manager=self.cache_manager,
            no_cache=False
        )
        self.assertEqual(result1, mock_elaboration_text)
        MockedContextAnalyzer.assert_called_once_with(api_key=test_api_key, model_name='gemini/gemini-1.5-flash-latest', api_base=None)
        mock_analyzer_instance.elaborate_on_match.assert_called_once()

        # Second call: Cache Hit
        result2 = elaborate_finding(
            report_path=self.report_file_path,
            finding_id=0,
            api_key=test_api_key,
            cache_manager=self.cache_manager,
            no_cache=False
        )
        self.assertEqual(result2, mock_elaboration_text)
        # elaborate_on_match should STILL have been called only once in total (from the miss)
        mock_analyzer_instance.elaborate_on_match.assert_called_once()
        # ContextAnalyzer constructor should NOT be called again on a cache hit
        MockedContextAnalyzer.assert_called_once()

    @patch.object(src.report_elaborator, 'ContextAnalyzer', autospec=True)
    def test_elaborate_cache_invalidation_on_finding_change(self, MockedContextAnalyzer):
        mock_analyzer_instance = MockedContextAnalyzer.return_value
        mock_analyzer_instance.model = True 
        mock_analyzer_instance.api_key = "key_for_invalidation_test"
        mock_elaboration_text_v1 = "Elaboration for original finding."
        mock_elaboration_text_v2 = "Elaboration for MODIFIED finding."
        
        test_api_key = "key_for_invalidation_test"

        # --- First call with original finding (cache miss) --- 
        mock_analyzer_instance.elaborate_on_match.return_value = mock_elaboration_text_v1
        result1 = elaborate_finding(
            report_path=self.report_file_path, 
            finding_id=0, 
            api_key=test_api_key,
            cache_manager=self.cache_manager,
            no_cache=False
        )
        self.assertEqual(result1, mock_elaboration_text_v1)
        mock_analyzer_instance.elaborate_on_match.assert_called_once()
        MockedContextAnalyzer.assert_called_once_with(api_key=test_api_key, model_name='gemini/gemini-1.5-flash-latest', api_base=None)

        # --- Simulate finding modification --- 
        # To do this robustly for the test, we'll write a new report file with a modified finding at index 0.
        modified_report_data = [self.report_data[0].copy()] # Start with a copy of the original finding 0
        modified_report_data[0]['snippet'] = "MODIFIED snippet for finding 0"
        modified_report_data[0]['match_text'] = "MODIFIED_match_text"
        
        modified_report_file_path = os.path.join(self.test_files_dir, "modified_findings_report.json")
        with open(modified_report_file_path, 'w', encoding='utf-8') as f:
            json.dump(modified_report_data, f)

        # --- Second call with modified finding (should be a cache miss again) ---
        # Reconfigure return value for the same mock_analyzer_instance for the second call
        mock_analyzer_instance.elaborate_on_match.return_value = mock_elaboration_text_v2

        result2 = elaborate_finding(
            report_path=modified_report_file_path, # Use the MODIFIED report
            finding_id=0, 
            api_key=test_api_key, # Same API key
            cache_manager=self.cache_manager,
            no_cache=False
        )
        self.assertEqual(result2, mock_elaboration_text_v2)
        # elaborate_on_match should have been called again (total 2 times overall)
        self.assertEqual(mock_analyzer_instance.elaborate_on_match.call_count, 2, 
                         "elaborate_on_match should be called again for a modified finding.")
        # ContextAnalyzer constructor should be called again for the second miss (total 2 times overall)
        self.assertEqual(MockedContextAnalyzer.call_count, 2)
        # Check that the last call was with the correct api_key, or check all calls if necessary
        MockedContextAnalyzer.assert_called_with(api_key=test_api_key, model_name='gemini/gemini-1.5-flash-latest', api_base=None) 

if __name__ == '__main__':
    unittest.main() 
