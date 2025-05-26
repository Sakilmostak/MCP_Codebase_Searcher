import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import sys
import io

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# REMOVED: Global sys.modules mock for config
# config_mock = MagicMock()
# config_mock.load_api_key.return_value = None 
# sys.modules['config'] = config_mock

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold, GenerationConfig
from google.api_core.exceptions import GoogleAPIError, InternalServerError, ResourceExhausted, PermissionDenied
from google.generativeai.types import BlockedPromptException

# Now that config is (conditionally) imported by mcp_elaborate, we can import the module to be tested
from src.mcp_elaborate import ContextAnalyzer

# Helper to reset mocks that might persist across tests, especially for module-level mocks
@patch.dict(os.environ, {}, clear=True) # Clear os.environ for each test
# We will patch 'src.mcp_elaborate.config.load_api_key' if needed by a specific test directly
def reset_mocks():
    pass # This function is just a vehicle for the decorators

class TestContextAnalyzer(unittest.TestCase):

    def setUp(self):
        reset_mocks() # Call to ensure mocks are reset
        # Ensure GOOGLE_API_KEY is not set in environ for most tests unless specified
        if 'GOOGLE_API_KEY' in os.environ:
            del os.environ['GOOGLE_API_KEY']
        # Common setup for a successful model initialization
        self.mock_generative_model_instance = MagicMock()
        self.mock_generative_model_instance.generate_content.return_value = MagicMock(
            text="Successful elaboration.",
            prompt_feedback=MagicMock(block_reason=None),
            parts=[MagicMock(text="Successful elaboration.")]
        )
        self.patcher_generative_model = patch('google.generativeai.GenerativeModel', return_value=self.mock_generative_model_instance)
        self.MockGenerativeModel = self.patcher_generative_model.start()
        self.addCleanup(self.patcher_generative_model.stop)

        self.patcher_genai_configure = patch('google.generativeai.configure')
        self.mock_genai_configure = self.patcher_genai_configure.start()
        self.addCleanup(self.patcher_genai_configure.stop)

    def tearDown(self):
        pass 

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "env_key"}, clear=True)
    # No need to patch config.load_api_key if env key is present and used first
    def test_init_api_key_from_env(self):
        analyzer = ContextAnalyzer()
        self.assertEqual(analyzer.api_key, "env_key")
        self.mock_genai_configure.assert_called_once_with(api_key="env_key")
        self.MockGenerativeModel.assert_called_once()
        self.assertIsNotNone(analyzer.model)

    @patch('src.mcp_elaborate.config') # Patch 'config' as seen by mcp_elaborate
    @patch.dict(os.environ, {}, clear=True)
    def test_init_api_key_from_config(self, mock_config_module):
        mock_config_module.load_api_key.return_value = "config_key"
        # Ensure the config module itself is seen as existing
        mock_config_module.__name__ = "config" # Emulate a real module for hasattr checks

        analyzer = ContextAnalyzer(api_key=None) # Explicitly pass None to prioritize config/env
        self.assertEqual(analyzer.api_key, "config_key")
        mock_config_module.load_api_key.assert_called_once()
        self.mock_genai_configure.assert_called_once_with(api_key="config_key")
        self.MockGenerativeModel.assert_called_once()
        self.assertIsNotNone(analyzer.model)

    @patch.dict(os.environ, {}, clear=True) # Keep this one as a decorator for now
    def test_init_api_key_from_param(self): # Remove the problematic argument
        with patch('src.mcp_elaborate.config', None) as mock_config_module_is_none: # Use as context manager
            self.assertIsNone(mock_config_module_is_none) 

            analyzer = ContextAnalyzer(api_key="param_key")
            self.assertEqual(analyzer.api_key, "param_key")
            self.mock_genai_configure.assert_called_once_with(api_key="param_key")
            self.MockGenerativeModel.assert_called_once()
            self.assertIsNotNone(analyzer.model)

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "env_key_override"}, clear=True)
    @patch('src.mcp_elaborate.config')
    def test_init_api_key_priority_param_over_env_over_config(self, mock_config_module):
        mock_config_module.load_api_key.return_value = "config_key"
        mock_config_module.__name__ = "config"

        # Param has highest priority
        analyzer_param = ContextAnalyzer(api_key="param_key_wins")
        self.assertEqual(analyzer_param.api_key, "param_key_wins")
        self.mock_genai_configure.assert_called_with(api_key="param_key_wins")
        mock_config_module.load_api_key.assert_not_called() # Config should not be called if param is present

        self.mock_genai_configure.reset_mock() # Reset for next assert
        # Env key if param is None
        analyzer_env = ContextAnalyzer(api_key=None)
        self.assertEqual(analyzer_env.api_key, "env_key_override") # Should pick env key
        self.mock_genai_configure.assert_called_with(api_key="env_key_override")
        mock_config_module.load_api_key.assert_not_called() # Config still not called if env is present

    @patch.dict(os.environ, {}, clear=True)
    def test_init_no_api_key(self):
        with patch('src.mcp_elaborate.config', None) as mock_config_is_none:
            self.assertIsNone(mock_config_is_none)
            with patch('src.mcp_elaborate.sys.stderr', new_callable=io.StringIO) as mock_stderr:
                analyzer = ContextAnalyzer() # No key via param, env, or config
                self.assertIsNone(analyzer.api_key)
                self.assertIsNone(analyzer.model) # Model should not be initialized
                self.mock_genai_configure.assert_not_called()
                self.MockGenerativeModel.assert_not_called()
                # Check for the warning about config import failure too if it's part of the logic
                # self.assertIn("warning: could not import 'config' module", mock_stderr.getvalue().lower())
                self.assertIn("error: contextanalyzer initialized without an api key. elaboration will not function.", mock_stderr.getvalue().lower())

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "dummy_key"}, clear=True)
    # No need to patch config if env key is used
    @patch('google.generativeai.GenerativeModel', side_effect=Exception("Model init failed"))
    def test_init_model_initialization_failure(self, mock_gm_fail):
        with patch('src.mcp_elaborate.sys.stderr', new_callable=io.StringIO) as mock_stderr:
            analyzer = ContextAnalyzer()
            self.assertEqual(analyzer.api_key, "dummy_key")
            self.assertIsNone(analyzer.model)
            self.assertIn(f"error initializing google generative ai model ({analyzer.model_name}): model init failed", mock_stderr.getvalue().lower())

    def test_elaborate_on_match_success(self):
        analyzer = ContextAnalyzer(api_key="fake_key") # Assume model initializes successfully
        analyzer.model = self.mock_generative_model_instance # Ensure it uses our mocked model
        elaboration = analyzer.elaborate_on_match("path/file.py", 10, "snippet code")
        self.assertEqual(elaboration, "Successful elaboration.")
        self.mock_generative_model_instance.generate_content.assert_called_once()

    @patch.dict(os.environ, {}, clear=True) # Ensure no env key for this specific test
    @patch('src.mcp_elaborate.config') # Patch config, make its load_api_key return None
    def test_elaborate_on_match_model_not_initialized(self, mock_config_module):
        mock_config_module.load_api_key.return_value = None
        mock_config_module.__name__ = "config" # Make it look like a module
        # This test assumes __init__ has already printed to stderr if no API key was found.
        # Here, we verify that elaborate_on_match returns the correct error string
        # and does NOT print further to stderr for this specific condition.
        analyzer = ContextAnalyzer() # No API key, so model is None. __init__ would have printed.
        self.assertIsNone(analyzer.api_key) # Add this assertion for clarity
        self.assertIsNone(analyzer.model)
        
        with patch('src.mcp_elaborate.sys.stderr', new_callable=io.StringIO) as mock_stderr_elaborate_call:
            elaboration = analyzer.elaborate_on_match("path/file.py", 10, "snippet")
            self.assertEqual(elaboration, "Error: Elaboration model not initialized. Cannot elaborate.")
            # Check that elaborate_on_match itself didn't print to stderr for this case
            self.assertEqual(mock_stderr_elaborate_call.getvalue(), "") 

    def test_elaborate_on_match_api_error(self):
        analyzer = ContextAnalyzer(api_key="fake_key")
        self.mock_generative_model_instance.generate_content.side_effect = GoogleAPIError("API Error")
        analyzer.model = self.mock_generative_model_instance
        with patch('src.mcp_elaborate.sys.stderr', new_callable=io.StringIO) as mock_stderr:
            elaboration = analyzer.elaborate_on_match("path/file.py", 10, "snippet")
            self.assertTrue(elaboration.startswith("[API error during elaboration"))
            self.assertTrue(elaboration.endswith("]"))
            self.assertIn("googleapierror - api error", elaboration.lower())
            expected_stderr_msg = "warning: api error during elaboration for path/file.py:10: googleapierror - api error"
            self.assertIn(expected_stderr_msg, mock_stderr.getvalue().lower().strip())
    
    def test_elaborate_on_match_blocked_prompt_exception(self):
        analyzer = ContextAnalyzer(api_key="fake_key")
        self.mock_generative_model_instance.generate_content.side_effect = BlockedPromptException("Blocked prompt")
        analyzer.model = self.mock_generative_model_instance
        with patch('src.mcp_elaborate.sys.stderr', new_callable=io.StringIO) as mock_stderr:
            elaboration = analyzer.elaborate_on_match("path/file.py", 10, "snippet")
            self.assertTrue(elaboration.startswith("[Elaboration blocked by API"))
            self.assertTrue(elaboration.endswith("]"))
            self.assertIn("blocked prompt", elaboration.lower())
            expected_stderr_msg = "warning: elaboration for path/file.py:10 was explicitly blocked. blocked prompt"
            self.assertIn(expected_stderr_msg, mock_stderr.getvalue().lower().strip())

    def test_elaborate_on_match_general_exception(self):
        analyzer = ContextAnalyzer(api_key="fake_key")
        self.mock_generative_model_instance.generate_content.side_effect = Exception("Unexpected error")
        analyzer.model = self.mock_generative_model_instance
        with patch('src.mcp_elaborate.sys.stderr', new_callable=io.StringIO) as mock_stderr:
            elaboration = analyzer.elaborate_on_match("path/file.py", 10, "snippet")
            self.assertTrue(elaboration.startswith("[Unexpected error during elaboration"))
            self.assertTrue(elaboration.endswith("]"))
            self.assertIn("exception - unexpected error", elaboration.lower())
            expected_stderr_msg = "warning: unexpected error during elaboration for path/file.py:10: exception - unexpected error"
            self.assertIn(expected_stderr_msg, mock_stderr.getvalue().lower().strip())

    def test_elaborate_on_match_empty_or_unparseable_response(self):
        analyzer = ContextAnalyzer(api_key="fake_key")
        analyzer.model = self.mock_generative_model_instance

        # Test 1: Response with no parts
        self.mock_generative_model_instance.generate_content.return_value = MagicMock(parts=[], prompt_feedback=MagicMock(block_reason=None))
        with patch('src.mcp_elaborate.sys.stderr', new_callable=io.StringIO) as mock_stderr:
            elaboration = analyzer.elaborate_on_match("path/file.py", 10, "snippet1")
            self.assertEqual(elaboration, "[No content returned from API for elaboration]")
            self.assertIn("no parts found in api response", mock_stderr.getvalue().lower())
        self.mock_generative_model_instance.generate_content.reset_mock()

        # Test 2: Response with parts but no text attribute or empty text
        mock_part_no_text = MagicMock()
        del mock_part_no_text.text # Ensure text attribute is missing
        self.mock_generative_model_instance.generate_content.return_value = MagicMock(
            parts=[mock_part_no_text],
            prompt_feedback=MagicMock(block_reason=None)
        )
        with patch('src.mcp_elaborate.sys.stderr', new_callable=io.StringIO) as mock_stderr:
            elaboration = analyzer.elaborate_on_match("path/file.py", 11, "snippet2")
            self.assertEqual(elaboration, "[Elaboration from API was empty or unparsable]")
            expected_stderr_msg = "warning: received empty elaboration from api for path/file.py:11."
            self.assertIn(expected_stderr_msg, mock_stderr.getvalue().lower().strip())
        self.mock_generative_model_instance.generate_content.reset_mock()
        
        mock_part_empty_text = MagicMock(text=" ") # Test with only whitespace
        self.mock_generative_model_instance.generate_content.return_value = MagicMock(
            parts=[mock_part_empty_text],
            prompt_feedback=MagicMock(block_reason=None)
        )
        with patch('src.mcp_elaborate.sys.stderr', new_callable=io.StringIO) as mock_stderr:
            elaboration = analyzer.elaborate_on_match("path/file.py", 12, "snippet3")
            self.assertEqual(elaboration, "[Elaboration from API was empty or unparsable]")
            self.assertIn("received empty elaboration from api", mock_stderr.getvalue().lower())

    def test_elaborate_with_full_file_content(self):
        analyzer = ContextAnalyzer(api_key="fake_key_for_test")
        analyzer.model = self.mock_generative_model_instance

        full_content = "line1\nline2\nsnippet_line\nline4\nline5"
        analyzer.elaborate_on_match("test.py", 3, "snippet_line", full_file_content=full_content, context_window_lines=1)
        
        self.mock_generative_model_instance.generate_content.assert_called_once()
        called_prompt = self.mock_generative_model_instance.generate_content.call_args[0][0]
        
        self.assertIn("File: test.py", called_prompt)
        self.assertIn("Line: 3", called_prompt)
        self.assertIn("snippet_line", called_prompt)
        self.assertIn("Here is a broader context from the file (matched line marked with '>>'):", called_prompt)
        self.assertIn("     2: line2\n>>    3: snippet_line\n     4: line4", called_prompt)

    def test_elaborate_full_file_context_edge_cases(self):
        analyzer = ContextAnalyzer(api_key="fake_key_for_test")
        analyzer.model = self.mock_generative_model_instance

        full_content1 = "line1\nline2_match\nline3"
        analyzer.elaborate_on_match("test.py", 1, "line1", full_file_content=full_content1, context_window_lines=1)
        called_prompt_start = self.mock_generative_model_instance.generate_content.call_args[0][0]
        expected_context_for_line1_match = ">>    1: line1\n     2: line2_match"
        self.assertIn(expected_context_for_line1_match, called_prompt_start)
        self.mock_generative_model_instance.generate_content.reset_mock() # Reset for next call

        full_content2 = "line1\nline2_match\nline3_end"
        analyzer.elaborate_on_match("test.py", 3, "line3_end", full_file_content=full_content2, context_window_lines=1)
        called_prompt_end = self.mock_generative_model_instance.generate_content.call_args[0][0]
        self.assertIn("Here is a broader context from the file (matched line marked with '>>'):", called_prompt_end)
        self.assertIn("     2: line2_match\n>>    3: line3_end", called_prompt_end)


if __name__ == '__main__':
    unittest.main() 