import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Add project root to sys.path to allow direct import of mcp_elaborate
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '.'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from mcp_elaborate import ContextAnalyzer

# It's generally better to patch specific modules where they are looked up.
# So, we'll patch 'mcp_elaborate.config' within the tests themselves.

class TestContextAnalyzer(unittest.TestCase):

    def setUp(self):
        """Set up for each test."""
        self.api_key = "test_api_key"
        self.model_name = "test-model"
        self.dummy_file_path = "dummy/file.py"
        self.dummy_line_number = 10
        self.dummy_snippet = ">>> print('hello') <<<"

    @patch('mcp_elaborate.genai.configure')
    @patch('mcp_elaborate.genai.GenerativeModel')
    def test_initialization_success(self, mock_generative_model, mock_configure):
        """Test successful initialization of ContextAnalyzer."""
        mock_model_instance = MagicMock()
        mock_generative_model.return_value = mock_model_instance

        analyzer = ContextAnalyzer(api_key=self.api_key, model_name=self.model_name)
        
        mock_configure.assert_called_once_with(api_key=self.api_key)
        mock_generative_model.assert_called_once_with(
            model_name=self.model_name,
            generation_config=analyzer.generation_config, 
            safety_settings=analyzer.safety_settings
        )
        self.assertEqual(analyzer.model, mock_model_instance)
        self.assertEqual(analyzer.api_key, self.api_key)

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "env_api_key"})
    @patch('mcp_elaborate.config') # Patch config where it's imported in mcp_elaborate
    @patch('mcp_elaborate.genai.configure')
    @patch('mcp_elaborate.genai.GenerativeModel')
    def test_initialization_with_env_variable(self, mock_generative_model, mock_configure, mock_mcp_config):
        """Test initialization using GOOGLE_API_KEY environment variable."""
        mock_model_instance = MagicMock()
        mock_generative_model.return_value = mock_model_instance
        # Ensure the mocked config.load_api_key within mcp_elaborate returns None
        mock_mcp_config.load_api_key.return_value = None 
        
        analyzer = ContextAnalyzer(api_key=None, model_name=self.model_name)
        
        mock_configure.assert_called_once_with(api_key="env_api_key")
        self.assertEqual(analyzer.api_key, "env_api_key")

    @patch('mcp_elaborate.config.load_api_key', return_value="config_api_key")
    @patch('mcp_elaborate.genai.configure')
    @patch('mcp_elaborate.genai.GenerativeModel')
    def test_initialization_with_config_file(self, mock_generative_model, mock_configure, mock_load_config_key):
        """Test initialization using API key from mocked config.py."""
        # This test assumes mcp_elaborate.config.load_api_key is directly patched.
        mock_model_instance = MagicMock()
        mock_generative_model.return_value = mock_model_instance
        
        analyzer = ContextAnalyzer(api_key=None, model_name=self.model_name)
        
        mock_load_config_key.assert_called_once() # Verifies mcp_elaborate.config.load_api_key was called
        mock_configure.assert_called_once_with(api_key="config_api_key")
        self.assertEqual(analyzer.api_key, "config_api_key")

    @patch('mcp_elaborate.config') # Patch config where it's imported in mcp_elaborate
    @patch('mcp_elaborate.genai.configure')
    @patch('mcp_elaborate.genai.GenerativeModel')
    def test_initialization_failure_no_key(self, mock_generative_model, mock_configure, mock_mcp_config):
        """Test initialization failure when no API key is provided or found."""
        mock_mcp_config.load_api_key.return_value = None # Ensure mocked config load returns None
        # Ensure os.getenv also returns None for GOOGLE_API_KEY in this test's context
        with patch.dict(os.environ, clear=True):
            with patch('sys.stderr', new_callable=MagicMock) as mock_stderr:
                analyzer = ContextAnalyzer(api_key=None)
                self.assertIsNone(analyzer.model)
                # Check that the specific error message is present in the stderr output stream
                # The messages are printed in order: warning about config, warning about env, then error.
                # For this test, we care about the final error.
                stderr_output = "".join(call_args[0][0] for call_args in mock_stderr.write.call_args_list)
                self.assertIn("Error: ContextAnalyzer initialized without an API key. Elaboration will not function.", stderr_output)
                # Ensure configure was not called because no key was found
                mock_configure.assert_not_called()

    @patch('mcp_elaborate.genai.configure')
    @patch('mcp_elaborate.genai.GenerativeModel', side_effect=Exception("Test Model Init Error"))
    def test_initialization_model_exception(self, mock_generative_model, mock_configure):
        """Test initialization failure when genai.GenerativeModel raises an exception."""
        with patch('sys.stderr', new_callable=MagicMock) as mock_stderr:
            analyzer = ContextAnalyzer(api_key=self.api_key)
            self.assertIsNone(analyzer.model)
            stderr_output = "".join(call_args[0][0] for call_args in mock_stderr.write.call_args_list)
            self.assertIn("Error initializing Google Generative AI model", stderr_output)

    @patch('mcp_elaborate.genai.configure')
    @patch('mcp_elaborate.genai.GenerativeModel')
    def test_elaborate_on_match_success(self, mock_generative_model, mock_configure):
        """Test successful elaboration."""
        mock_model_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Successful elaboration."
        mock_response.parts = [MagicMock(text="Successful elaboration.")] 
        mock_response.prompt_feedback = None 
        mock_model_instance.generate_content.return_value = mock_response
        mock_generative_model.return_value = mock_model_instance

        analyzer = ContextAnalyzer(api_key=self.api_key)
        result = analyzer.elaborate_on_match(self.dummy_file_path, self.dummy_line_number, self.dummy_snippet)

        self.assertEqual(result, "Successful elaboration.")
        mock_model_instance.generate_content.assert_called_once()

    @patch('mcp_elaborate.config') # Patch config where it's imported in mcp_elaborate
    @patch('mcp_elaborate.genai.configure')
    @patch('mcp_elaborate.genai.GenerativeModel')
    def test_elaborate_on_match_model_not_initialized(self, mock_generative_model, mock_configure, mock_mcp_config):
        """Test elaboration when the model is not initialized."""
        mock_mcp_config.load_api_key.return_value = None
        with patch.dict(os.environ, clear=True):
            analyzer = ContextAnalyzer(api_key=None)
        
        self.assertIsNone(analyzer.model) 
        result = analyzer.elaborate_on_match(self.dummy_file_path, self.dummy_line_number, self.dummy_snippet)
        self.assertEqual(result, "Error: Elaboration model not initialized. Cannot elaborate.")

    @patch('mcp_elaborate.genai.configure')
    @patch('mcp_elaborate.genai.GenerativeModel')
    def test_elaborate_on_match_api_error(self, mock_generative_model, mock_configure):
        """Test elaboration failure due to an API error."""
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.side_effect = Exception("API communication error")
        mock_generative_model.return_value = mock_model_instance

        analyzer = ContextAnalyzer(api_key=self.api_key)
        with patch('sys.stderr', new_callable=MagicMock) as mock_stderr:
            result = analyzer.elaborate_on_match(self.dummy_file_path, self.dummy_line_number, self.dummy_snippet)
            self.assertIn("Error during AI model generation: Exception - API communication error", result)
            stderr_output = "".join(call_args[0][0] for call_args in mock_stderr.write.call_args_list)
            self.assertIn("API communication error", stderr_output)


    @patch('mcp_elaborate.genai.configure')
    @patch('mcp_elaborate.genai.GenerativeModel')
    def test_elaborate_on_match_content_blocked(self, mock_generative_model, mock_configure):
        """Test elaboration when content is blocked by safety settings."""
        mock_model_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.text = None 
        mock_response.parts = []  
        mock_feedback = MagicMock()
        mock_feedback.block_reason = "SAFETY"
        mock_response.prompt_feedback = mock_feedback
        mock_model_instance.generate_content.return_value = mock_response
        mock_generative_model.return_value = mock_model_instance

        analyzer = ContextAnalyzer(api_key=self.api_key)
        result = analyzer.elaborate_on_match(self.dummy_file_path, self.dummy_line_number, self.dummy_snippet)
        self.assertEqual(result, "Error: Content generation blocked. Reason: SAFETY.")

    @patch('mcp_elaborate.genai.configure')
    @patch('mcp_elaborate.genai.GenerativeModel')
    def test_elaborate_on_match_with_full_file_content(self, mock_generative_model, mock_configure):
        """Test prompt generation when full_file_content is provided."""
        mock_model_instance = MagicMock()
        mock_response = MagicMock(text="Elaboration with full content.")
        mock_response.parts = [MagicMock(text="Elaboration with full content.")]
        mock_response.prompt_feedback = None
        mock_model_instance.generate_content.return_value = mock_response
        mock_generative_model.return_value = mock_model_instance

        analyzer = ContextAnalyzer(api_key=self.api_key)
        
        full_content = "line1\nline2\nline3\nprint('hello')\nline5\nline6"
        snippet_from_searcher = "line3\n>>> print('hello') <<<\nline5" 
        
        result = analyzer.elaborate_on_match(
            self.dummy_file_path, 
            4,  
            snippet_from_searcher,
            full_file_content=full_content,
            context_window_lines=1 
        )
        self.assertEqual(result, "Elaboration with full content.")
        
        generated_prompt = mock_model_instance.generate_content.call_args[0][0]
        self.assertIn("line3", generated_prompt) 
        self.assertIn("print('hello')", generated_prompt) 
        self.assertIn("line5", generated_prompt) 
        self.assertIn("File: dummy/file.py", generated_prompt)
        self.assertIn("Line: 4", generated_prompt)
        self.assertIn("----------------FILE CONTEXT-----------------", generated_prompt)
        self.assertIn(">>    4: print('hello')", generated_prompt) 


    @patch('mcp_elaborate.genai.configure')
    @patch('mcp_elaborate.genai.GenerativeModel')
    def test_elaborate_on_match_empty_or_unparsable_response(self, mock_generative_model, mock_configure):
        """Test handling of an empty or unparsable response from the API."""
        mock_model_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.text = ""  
        mock_response.parts = [] 
        mock_response.prompt_feedback = None 
        mock_model_instance.generate_content.return_value = mock_response
        mock_generative_model.return_value = mock_model_instance

        analyzer = ContextAnalyzer(api_key=self.api_key)
        result = analyzer.elaborate_on_match(self.dummy_file_path, self.dummy_line_number, self.dummy_snippet)
        self.assertEqual(result, "Error: Received an empty or unparsable response from the AI model.")

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False) 