import unittest
from unittest.mock import patch, mock_open
import os
import sys
import json
import io
import shutil

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.mcp_searcher import main, parse_arguments # Import parse_arguments as well
from src.cache_manager import CacheManager # Import for mocking its path

class TestMcpSearcher(unittest.TestCase):
    def setUp(self):
        self.test_dir = "temp_test_mcp_searcher_cli"
        os.makedirs(self.test_dir, exist_ok=True)
        # self.mock_open_for_searcher will be used by run_main_with_args
        # It's defined here to be accessible by the helper, but its behavior
        # might be overridden in specific tests if they interact with files differently.
        self.mock_open_for_searcher = mock_open()
        self.test_temp_cache_dir = os.path.join(self.test_dir, "cli_cache_test")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        if os.path.exists(self.test_temp_cache_dir):
            shutil.rmtree(self.test_temp_cache_dir)

    # --- Helper method to run main() ---
    def run_main_with_args(self, args_list):
        """Helper to run main() with patched argv and captured stdout/stderr."""
        # Attempt to force re-import of the report_elaborator module
        # to pick up signature changes, especially for elaborate_finding.
        if 'report_elaborator' in sys.modules:
            del sys.modules['report_elaborator']
        if 'src.report_elaborator' in sys.modules: # In case it's imported this way
            del sys.modules['src.report_elaborator']
        # Also attempt for mcp_elaborate as it's a direct dependency for elaborate_finding
        if 'mcp_elaborate' in sys.modules:
            del sys.modules['mcp_elaborate']
        if 'src.mcp_elaborate' in sys.modules:
            del sys.modules['src.mcp_elaborate']

        # Resetting builtins.open mock for each run to avoid interference between tests
        # This default mock_open is basic. Tests that need specific file interactions
        # (like creating dummy reports) will handle open() within their own scope or
        # temporarily replace self.mock_open_for_searcher.
        current_mock_open = mock_open()
        
        with patch('sys.argv', ['mcp_searcher.py'] + args_list),\
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout,\
             patch('sys.stderr', new_callable=io.StringIO) as mock_stderr,\
             patch('builtins.open', current_mock_open) as PatcherBuiltinsOpen: # Patch open for file ops within main
            
            # For tests involving config file loading via 'open' in mcp_searcher.main
            # We need to make sure the mocked 'open' behaves correctly.
            # If a test creates a file (e.g. report_path, config_path_good),
            # the mock_open needs to allow reading it.
            # This can be complex. A simpler approach for config files might be to also mock json.load
            # or have specific mock_open behaviors for those paths.
            # For now, tests creating files will use real open, and this mock handles other cases.
            # The mock_open in the context manager here will be the one seen by main().

            try:
                main()
                exit_code = 0 
            except SystemExit as e:
                exit_code = e.code if isinstance(e.code, int) else 1
            return mock_stdout.getvalue(), mock_stderr.getvalue(), exit_code, PatcherBuiltinsOpen

    # --- Tests for the 'elaborate' command ---

    @patch('src.mcp_searcher.elaborate_finding')
    @patch('os.getenv') # New patch for os.getenv
    def test_elaborate_command_success(self, mock_os_getenv, mock_elaborate_finding): # mock_os_getenv from inner patch, mock_elaborate_finding from outer
        mock_os_getenv.return_value = None # Ensure no env var API key is found
        mock_elaborate_finding.return_value = "Mocked elaboration successful!"
        
        report_path = os.path.join(self.test_dir, 'sample_report.json')
        dummy_report_content = [{"file_path": "a.py", "line_number": 1, "snippet": "snip", "match_text": "mt"}]
        # Use real open for creating this test-specific file
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(dummy_report_content, f)

        args = ['elaborate', '--report-file', report_path, '--finding-id', '0']
        # For this test, builtins.open will be mocked by run_main_with_args's default mock_open.
        # elaborate_finding is mocked, so it won't try to open the source file from the report.
        stdout, stderr, exit_code, _ = self.run_main_with_args(args)
        
        self.assertEqual(exit_code, 0)
        self.assertIn("Mocked elaboration successful!", stdout)
        self.assertEqual(stderr, "")
        mock_elaborate_finding.assert_called_once_with(
            report_path=report_path,
            finding_id=0,
            api_key=None,
            model_name='gemini/gemini-1.5-flash-latest',
            api_base=None,
            context_window_lines=10, # Default
            cache_manager=unittest.mock.ANY,
            no_cache=unittest.mock.ANY
        )

    @patch('src.mcp_searcher.elaborate_finding')
    def test_elaborate_command_with_api_key_and_context_lines(self, mock_elaborate_finding):
        mock_elaborate_finding.return_value = "Elaboration with params."
        report_path = os.path.join(self.test_dir, 'report_params.json')
        dummy_report_content = [{"file_path": "b.py", "line_number": 2, "snippet": "s", "match_text": "m"}]
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(dummy_report_content, f)

        args = [
            'elaborate',
            '--report-file', report_path, 
            '--finding-id', '0',
            '--api-key', 'test_key_123',
            '--context-lines', '5'
        ]
        stdout, stderr, exit_code, _ = self.run_main_with_args(args)
        
        self.assertEqual(exit_code, 0)
        self.assertIn("Elaboration with params.", stdout)
        mock_elaborate_finding.assert_called_once_with(
            report_path=report_path,
            finding_id=0,
            api_key='test_key_123',
            model_name='gemini/gemini-1.5-flash-latest',
            api_base=None,
            context_window_lines=5,
            cache_manager=unittest.mock.ANY,
            no_cache=unittest.mock.ANY
        )

    @patch('src.mcp_searcher.elaborate_finding')
    def test_elaborate_command_finding_returns_error(self, mock_elaborate_finding):
        mock_elaborate_finding.return_value = "Error: Mocked finding not found."
        report_path = os.path.join(self.test_dir, 'report_error.json')
        dummy_report_content = [{"file_path": "c.py", "line_number": 3, "snippet": "s3", "match_text": "m3"}]
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(dummy_report_content, f)

        args = ['elaborate', '--report-file', report_path, '--finding-id', '1']
        _stdout, stderr, exit_code, _ = self.run_main_with_args(args) # Capture stderr
        
        self.assertNotEqual(exit_code, 0)
        self.assertIn("Error: Mocked finding not found.", stderr) # Corrected: check stderr
        mock_elaborate_finding.assert_called_once()

    @patch('src.mcp_searcher.elaborate_finding')
    def test_elaborate_command_report_file_not_found(self, mock_elaborate_finding_direct):
        # Configure the direct mock to return the specific error string expected
        mock_elaborate_finding_direct.return_value = "Error: Report file not found at 'non_existent_report.json'."

        args = ['elaborate', '--report-file', 'non_existent_report.json', '--finding-id', '0']
        _stdout, stderr, exit_code, _ = self.run_main_with_args(args) # Capture stderr
        
        self.assertNotEqual(exit_code, 0)
        self.assertTrue(stderr.startswith("Error: Report file not found at 'non_existent_report.json'."), f"Stderr was: {stderr}")
        # Ensure our direct mock was called
        mock_elaborate_finding_direct.assert_called_once_with(
            report_path='non_existent_report.json', 
            finding_id=0, 
            api_key=unittest.mock.ANY, # main will determine this, allow ANY
            model_name=unittest.mock.ANY,
            api_base=unittest.mock.ANY,
            context_window_lines=10,   # Default from argparse
            cache_manager=unittest.mock.ANY,
            no_cache=False # Default from argparse
        )

    def test_elaborate_command_missing_required_args(self):
        args1 = ['elaborate', '--finding-id', '0']
        _stdout1, stderr1, exit_code1, _ = self.run_main_with_args(args1)
        self.assertNotEqual(exit_code1, 0)
        self.assertIn("the following arguments are required: --report-file", stderr1.lower())

        args2 = ['elaborate', '--report-file', 'some_report.json']
        _stdout2, stderr2, exit_code2, _ = self.run_main_with_args(args2)
        self.assertNotEqual(exit_code2, 0)
        self.assertIn("the following arguments are required: --finding-id", stderr2.lower())

    @patch('src.mcp_searcher.elaborate_finding')
    @patch('json.load') 
    @patch('os.getenv') # New patch for os.getenv
    def test_elaborate_command_config_file_logic(self, mock_os_getenv, mock_json_load, mock_elaborate_finding): # mock_os_getenv from innermost, then mock_json_load, then mock_elaborate_finding
        mock_os_getenv.return_value = None # Default to no env var API key for these tests
        mock_elaborate_finding.return_value = "Config key used."
        
        # 1. Test with config file that has the key
        config_path_good = os.path.join(self.test_dir, 'good_config.json')
        # We don't need to physically create config_path_good if we mock open AND json.load
        # json.load will be called by main() if --config-file is used and --api-key is not.
        mock_json_load.return_value = {"GOOGLE_API_KEY": "key_from_config"}
        
        report_path = os.path.join(self.test_dir, 'report_for_config.json')
        with open(report_path, 'w', encoding='utf-8') as f: # Real report file
            json.dump([{"file_path": "d.py", "line_number":1, "snippet":"s", "match_text":"m"}],f)

        args_good_cfg = ['elaborate', '--report-file', report_path, '--finding-id', '0', '--config-file', config_path_good]
        # run_main_with_args will mock builtins.open. When mcp_searcher tries to open config_path_good,
        # it will use the mocked open. Then it calls json.load, which we've mocked directly.
        stdout_good, stderr_good, exit_code_good, mock_open_used = self.run_main_with_args(args_good_cfg)
        
        self.assertEqual(exit_code_good, 0)
        self.assertIn("Config key used.", stdout_good)
        # Check that builtins.open was called for the config file
        # mock_open_used.assert_any_call(config_path_good, 'r', encoding='utf-8')
        # json.load should have been called
        mock_json_load.assert_called_once() 
        mock_elaborate_finding.assert_called_with(
            report_path=report_path, 
            finding_id=0, 
            api_key='key_from_config', 
            model_name='gemini/gemini-1.5-flash-latest',
            api_base=None,
            context_window_lines=10,
            cache_manager=unittest.mock.ANY,
            no_cache=unittest.mock.ANY
            )
        self.assertEqual(stderr_good, "")
        
        mock_elaborate_finding.reset_mock()
        mock_json_load.reset_mock()

        # 2. Test with config file that DOES NOT have the key
        mock_json_load.return_value = {"OTHER_KEY": "some_value"}
        config_path_bad_key = os.path.join(self.test_dir, 'bad_key_config.json') # Path still used for messages
        
        args_bad_key_cfg = ['elaborate', '--report-file', report_path, '--finding-id', '0', '--config-file', config_path_bad_key]
        _stdout_bad, stderr_bad, exit_code_bad, _ = self.run_main_with_args(args_bad_key_cfg)

        self.assertEqual(exit_code_bad, 0) 
        self.assertEqual(stderr_bad, "")
        mock_elaborate_finding.assert_called_with(
            report_path=report_path, 
            finding_id=0, 
            api_key=None, 
            model_name='gemini/gemini-1.5-flash-latest',
            api_base=None,
            context_window_lines=10,
            cache_manager=unittest.mock.ANY,
            no_cache=unittest.mock.ANY
            )
        mock_json_load.assert_called_once()
        
        mock_elaborate_finding.reset_mock()
        mock_json_load.reset_mock()

        # 3. Test with --api-key taking precedence over --config-file
        args_api_takes_precedence = [
            'elaborate', '--report-file', report_path, '--finding-id', '0', 
            '--config-file', config_path_good, # This has 'key_from_config'
            '--api-key', 'direct_api_key'      # This should be used
        ]
        _stdout_precedence, stderr_precedence, _exit_code_precedence, mock_open_prec = self.run_main_with_args(args_api_takes_precedence)
        mock_elaborate_finding.assert_called_with(
            report_path=report_path, 
            finding_id=0, 
            api_key='direct_api_key', 
            model_name='gemini/gemini-1.5-flash-latest',
            api_base=None,
            context_window_lines=10,
            cache_manager=unittest.mock.ANY,
            no_cache=unittest.mock.ANY
            )
        mock_json_load.assert_called_once() # json.load is still called to check for api_base/model_name
        self.assertEqual(stderr_precedence, "")

    def test_caching_cli_arguments_help_text(self):
        # Test that caching arguments appear in --help output
        # The main function calls parse_arguments, which will print help and exit cleanly.
        stdout, stderr, exit_code, _ = self.run_main_with_args(['--help'])
        
        self.assertEqual(exit_code, 0) # --help should exit with 0
        self.assertEqual(stderr, "") # No error output expected

        # Check for the argument group title
        self.assertIn("Caching Options:", stdout)

        # Check for each caching argument and its help text
        self.assertIn("--no-cache", stdout)
        self.assertIn("Disable caching for this run.", stdout)

        self.assertIn("--clear-cache", stdout)
        self.assertIn("Clear all cached data before proceeding.", stdout)

        self.assertIn("--cache-dir DIRECTORY", stdout)
        # The default path is os.path.expanduser("~/.cache/mcp_codebase_searcher")
        # The help string itself contains the literal "~/.cache/mcp_codebase_searcher"
        self.assertIn("Directory to store cache files (default: ~/.cache/mcp_codebase_searcher).", stdout)

        self.assertIn("--cache-expiry DAYS", stdout)
        self.assertIn("Default cache expiry in days (default: 7).", stdout)

        self.assertIn("--cache-size-limit MB", stdout)
        self.assertIn("Cache size limit in Megabytes (default: 100).", stdout)

    @patch('src.mcp_searcher.CacheManager') # Mock CacheManager at the source
    def test_clear_cache_functionality(self, MockCacheManager):
        mock_cache_instance = MockCacheManager.return_value
        mock_cache_instance.clear_all.return_value = 5 # Simulate 5 items cleared
        
        # args = ['--clear-cache'] # Original line
        # Argparse requires a command, so provide a dummy one.
        args = ['--clear-cache', 'search', 'dummy_query', os.devnull]
        stdout, stderr, exit_code, _ = self.run_main_with_args(args)
        
        MockCacheManager.assert_called_once() # Check it was instantiated
        mock_cache_instance.clear_all.assert_called_once()
        self.assertIn("Clearing cache at", stdout)
        self.assertIn("Successfully cleared 5 items", stdout)
        self.assertEqual(exit_code, 0) # Should exit cleanly
        mock_cache_instance.close.assert_called_once() # Ensure close is called before exit

    @patch('src.mcp_searcher.CacheManager')
    def test_cache_manager_instantiation_with_cli_args(self, MockCacheManager):
        # For this test, we don't need a command, just global cache args
        # However, argparse requires a command. We'll use 'search' with minimal valid args for it.
        # The focus is on CacheManager instantiation.
        custom_dir = self.test_temp_cache_dir
        custom_expiry_days = 15
        custom_size_limit_mb = 200

        # We need a dummy query and path for the search command to pass argparse
        # We will also mock Searcher to prevent actual search logic from running.
        with patch('src.mcp_searcher.Searcher') as MockSearcher:
            args = [
                '--cache-dir', custom_dir,
                '--cache-expiry', str(custom_expiry_days),
                '--cache-size-limit', str(custom_size_limit_mb),
                'search', # dummy command
                'dummy_query', # dummy query for search
                os.devnull # dummy path for search
            ]
            self.run_main_with_args(args)

        expected_expiry_seconds = custom_expiry_days * 24 * 60 * 60
        MockCacheManager.assert_called_once_with(
            cache_dir=custom_dir,
            expiry_seconds=expected_expiry_seconds,
            cache_size_limit_mb=custom_size_limit_mb
        )
        # Check that close was called (it's in the finally block of main)
        mock_cache_instance = MockCacheManager.return_value
        mock_cache_instance.close.assert_called_once()

    @patch('src.mcp_searcher.CacheManager')
    @patch('src.mcp_searcher.Searcher')
    @patch('src.mcp_searcher.FileScanner')
    def test_search_with_no_cache_flag(self, MockFileScanner, MockSearcher, MockCacheManager):
        mock_scanner_instance = MockFileScanner.return_value
        dummy_file_path = os.path.join(self.test_dir, 'dummy_search_file_no_cache.txt')
        with open(dummy_file_path, 'w') as f:
            f.write("content with query for no_cache test")
        
        # FileScanner.scan_directory returns a list of (path, timestamp) tuples
        # For a direct file path, main() calls os.path.isfile and then scanner._is_excluded / _is_binary
        mock_scanner_instance._is_excluded.return_value = False
        mock_scanner_instance._is_binary.return_value = False
        # If a directory were passed, scan_directory would be called. 
        # For a direct file, it's added if not excluded/binary.
        # The Searcher then receives a list of these validated file paths.

        mock_searcher_instance = MockSearcher.return_value
        mock_searcher_instance.search_files.return_value = [{'file_path': dummy_file_path, 'matches': [{'line_number': 1, 'line_text': 'content with query for no_cache test', 'match_text': 'query'}]}]

        mock_cache_manager_instance = MockCacheManager.return_value

        # Corrected: Global cache args before the subcommand 'search'
        args = ['--no-cache', '--cache-dir', self.test_temp_cache_dir, 'search', 'query', dummy_file_path]
        self.run_main_with_args(args)

        MockSearcher.assert_called_once()
        called_args, called_kwargs = MockSearcher.call_args
        self.assertTrue(called_kwargs.get('no_cache'))
        self.assertIs(called_kwargs.get('cache_manager'), mock_cache_manager_instance)

        mock_cache_manager_instance.get.assert_not_called()
        mock_cache_manager_instance.set.assert_not_called()
        mock_searcher_instance.search_files.assert_called()


    @patch('src.mcp_searcher.CacheManager')
    @patch('src.mcp_searcher.elaborate_finding')
    def test_elaborate_with_no_cache_flag(self, mock_elaborate_finding, MockCacheManager):
        mock_elaborate_finding.return_value = "Elaboration (no-cache) complete."
        mock_cache_manager_instance = MockCacheManager.return_value
        
        report_path = os.path.join(self.test_dir, 'report_for_nocache_elaborate.json')
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump([{"file_path": "e.py", "line_number":1, "snippet":"s", "match_text":"m"}],f)

        # Corrected: Global cache args before the subcommand 'elaborate'
        args = [
            '--no-cache', 
            '--cache-dir', self.test_temp_cache_dir,
            'elaborate', 
            '--report-file', report_path, 
            '--finding-id', '0'
        ]
        stdout, stderr, exit_code, _ = self.run_main_with_args(args)
        
        self.assertEqual(exit_code, 0, f"STDOUT: {stdout}\\nSTDERR: {stderr}")
        self.assertIn("Elaboration (no-cache) complete.", stdout)
        
        mock_elaborate_finding.assert_called_once()
        _, called_kwargs = mock_elaborate_finding.call_args
        self.assertTrue(called_kwargs.get('no_cache'))
        self.assertIs(called_kwargs.get('cache_manager'), mock_cache_manager_instance)

if __name__ == '__main__':
    unittest.main() 