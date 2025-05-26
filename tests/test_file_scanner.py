import unittest
from unittest.mock import patch, mock_open, MagicMock
import os
import sys
import fnmatch
import shutil

# Add project root to sys.path to allow direct import of file_scanner
# Corrected project_root path for test discovery
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now import the module
from src.file_scanner import FileScanner, DEFAULT_EXCLUDED_DIRS, DEFAULT_EXCLUDED_FILES, DEFAULT_BINARY_EXTENSIONS

class TestFileScanner(unittest.TestCase):
    def setUp(self):
        # Basic scanner for most tests
        self.scanner = FileScanner()
        # Scanner configured to include hidden items
        self.hidden_scanner = FileScanner(exclude_dot_items=False)

        # Create a temporary directory structure for testing
        self.test_dir = "temp_test_dir_scanner"
        os.makedirs(os.path.join(self.test_dir, "subdir", ".hidden_subdir"), exist_ok=True)

        # Create test files
        self.test_files = {
            "file1.txt": "text content",
            "file2.py": "python code",
            ".hiddenfile.txt": "hidden text",
            "file.jpg": b"binarydata", # Actual binary content for jpg
            "archive.zip": b"PK...",   # Mock binary
            "document.pdf": b"%PDF-", # Mock binary
            "custom_exclude.ceu": "custom content",
            "another.txt": "some more text",
            os.path.join("subdir", "subfile.txt"): "subdir text",
            os.path.join("subdir", ".hidden_subfile.txt"): "hidden subdir text",
            os.path.join(".hidden_subdir", "another_hidden.txt"): "text in hidden_subdir"
        }
        for name, content in self.test_files.items():
            file_path = os.path.join(self.test_dir, name)
            os.makedirs(os.path.dirname(file_path), exist_ok=True) # Ensure subdir exists
            mode = 'wb' if isinstance(content, bytes) else 'w'
            with open(file_path, mode) as f:
                f.write(content)

    def tearDown(self):
        # Clean up the temporary directory
        if os.path.exists(self.test_dir):
            for root, dirs, files in os.walk(self.test_dir):
                for name in files:
                    try:
                        os.chmod(os.path.join(root, name), 0o777)
                    except OSError:
                        pass
                for name in dirs:
                    try:
                        os.chmod(os.path.join(root, name), 0o777)
                    except OSError:
                        pass
            shutil.rmtree(self.test_dir)

    def test_initialization_default_exclusions(self):
        scanner = FileScanner() # Default exclusions
        # Compare as sets to ignore order
        self.assertEqual(set(scanner.excluded_dirs), set(DEFAULT_EXCLUDED_DIRS))
        self.assertEqual(set(scanner.excluded_files), set(DEFAULT_EXCLUDED_FILES))
        self.assertEqual(set(scanner.binary_extensions), set(DEFAULT_BINARY_EXTENSIONS))
        self.assertEqual(scanner.custom_exclude_patterns, [])
        self.assertTrue(scanner.exclude_dot_items) # Default

    def test_initialization_custom_exclusions(self):
        custom_dirs = ["/custom_dir/", "*.tmp"]
        custom_files = ["specific.log", "*.bak"]
        custom_bin_exts = [".dat", ".custombin"]
        custom_patterns = ["skip_this*"]

        scanner = FileScanner(
            excluded_dirs=custom_dirs,
            excluded_files=custom_files,
            binary_extensions=custom_bin_exts,
            custom_exclude_patterns=custom_patterns,
            exclude_dot_items=False
        )
        # Compare as sets to ignore order
        self.assertEqual(set(scanner.excluded_dirs), set(custom_dirs))
        self.assertEqual(set(scanner.excluded_files), set(custom_files))
        self.assertEqual(set(scanner.binary_extensions), set(custom_bin_exts))
        self.assertEqual(set(scanner.custom_exclude_patterns), set(custom_patterns))
        self.assertFalse(scanner.exclude_dot_items)

    def test_is_excluded_defaults(self):
        # Default: exclude_dot_items=True
        scanner = FileScanner(exclude_dot_items=True) 
        # Directories
        self.assertTrue(scanner._is_excluded(os.path.join(self.test_dir, ".git"), self.test_dir, is_dir=True), ".git dir should be excluded")
        self.assertTrue(scanner._is_excluded(os.path.join(self.test_dir, "node_modules"), self.test_dir, is_dir=True), "node_modules dir should be excluded")
        self.assertTrue(scanner._is_excluded(os.path.join(self.test_dir, "subdir", ".hidden_subdir"), self.test_dir, is_dir=True), "subdir/.hidden_subdir should be excluded")
        self.assertFalse(scanner._is_excluded(os.path.join(self.test_dir, "subdir"), self.test_dir, is_dir=True), "subdir should not be excluded by default dot rule")

        # Files
        self.assertTrue(scanner._is_excluded(os.path.join(self.test_dir, ".hiddenfile.txt"), self.test_dir, is_dir=False), ".hiddenfile.txt should be excluded")
        # .pyc is excluded by binary checks, not by default file exclusion patterns.
        self.assertFalse(scanner._is_excluded(os.path.join(self.test_dir, "file.pyc"), self.test_dir, is_dir=False), ".pyc should NOT be excluded by default file patterns, but by binary check")
        self.assertTrue(scanner._is_excluded(os.path.join(self.test_dir, "path", ".config.json"), self.test_dir, is_dir=False), "path/.config.json should be excluded")
        self.assertFalse(scanner._is_excluded(os.path.join(self.test_dir, "regular.txt"), self.test_dir, is_dir=False), "regular.txt should not be excluded")
        self.assertFalse(scanner._is_excluded(os.path.join(self.test_dir, "subdir", "another.py"), self.test_dir, is_dir=False), "subdir/another.py should not be excluded")

    def test_is_excluded_hidden_items(self):
        # Test with exclude_dot_items=True (default behavior, should exclude)
        scanner_exclude_dots = FileScanner(exclude_dot_items=True)
        self.assertTrue(scanner_exclude_dots._is_excluded(os.path.join(self.test_dir, ".hidden_dir"), self.test_dir, is_dir=True), "Hidden dir should be excluded when exclude_dot_items=True")
        self.assertTrue(scanner_exclude_dots._is_excluded(os.path.join(self.test_dir, "dir", ".config"), self.test_dir, is_dir=True), "Nested hidden dir should be excluded when exclude_dot_items=True")
        self.assertTrue(scanner_exclude_dots._is_excluded(os.path.join(self.test_dir, ".hidden_file.txt"), self.test_dir, is_dir=False), "Hidden file should be excluded when exclude_dot_items=True")
        self.assertTrue(scanner_exclude_dots._is_excluded(os.path.join(self.test_dir, "dir", ".another.cfg"), self.test_dir, is_dir=False), "Nested hidden file should be excluded when exclude_dot_items=True")

        # Test with exclude_dot_items=False (should NOT exclude based on dot, but other rules might apply)
        scanner_include_dots = FileScanner(exclude_dot_items=False, excluded_dirs=[], excluded_files=[]) # No other rules
        self.assertFalse(scanner_include_dots._is_excluded(os.path.join(self.test_dir, ".hidden_dir"), self.test_dir, is_dir=True), "Hidden dir should NOT be excluded by dot rule when exclude_dot_items=False")
        self.assertFalse(scanner_include_dots._is_excluded(os.path.join(self.test_dir, "dir", ".config"), self.test_dir, is_dir=True), "Nested hidden dir should NOT be excluded by dot rule when exclude_dot_items=False")
        self.assertFalse(scanner_include_dots._is_excluded(os.path.join(self.test_dir, ".hidden_file.txt"), self.test_dir, is_dir=False), "Hidden file should NOT be excluded by dot rule when exclude_dot_items=False")
        self.assertFalse(scanner_include_dots._is_excluded(os.path.join(self.test_dir, "dir", ".another.cfg"), self.test_dir, is_dir=False), "Nested hidden file should NOT be excluded by dot rule when exclude_dot_items=False")

        # Test that scan root itself, if a dot-path, is not excluded by the dot rule
        dot_scan_root = os.path.join(self.test_dir, ".root_is_dot")
        os.makedirs(dot_scan_root, exist_ok=True)
        self.assertFalse(scanner_exclude_dots._is_excluded(dot_scan_root, dot_scan_root, is_dir=True), "Scan root itself (.root_is_dot) should not be excluded by dot rule")

    def test_is_excluded_custom_patterns(self):
        custom_patterns = ["skip_this_dir/", "*.log", "specific_file.txt", "path/to/exclude/*", "another_path/specific.py"]
        scanner = FileScanner(custom_exclude_patterns=custom_patterns, excluded_dirs=[], excluded_files=[])

        # Directories
        self.assertTrue(scanner._is_excluded(os.path.join(self.test_dir, "skip_this_dir"), self.test_dir, is_dir=True))
        self.assertTrue(scanner._is_excluded(os.path.join(self.test_dir, "path", "to", "exclude"), self.test_dir, is_dir=True))
        self.assertFalse(scanner._is_excluded(os.path.join(self.test_dir, "other_dir"), self.test_dir, is_dir=True))

        # Files
        self.assertTrue(scanner._is_excluded(os.path.join(self.test_dir, "app.log"), self.test_dir, is_dir=False))
        self.assertTrue(scanner._is_excluded(os.path.join(self.test_dir, "specific_file.txt"), self.test_dir, is_dir=False))
        self.assertTrue(scanner._is_excluded(os.path.join(self.test_dir, "path", "to", "exclude", "somefile.txt"), self.test_dir, is_dir=False), "File under dir/* pattern")
        self.assertTrue(scanner._is_excluded(os.path.join(self.test_dir, "another_path", "specific.py"), self.test_dir, is_dir=False))
        self.assertFalse(scanner._is_excluded(os.path.join(self.test_dir, "another.txt"), self.test_dir, is_dir=False))
        self.assertFalse(scanner._is_excluded(os.path.join(self.test_dir, "another_path", "other.py"), self.test_dir, is_dir=False))

    def test_is_binary_by_extension(self):
        self.assertTrue(self.scanner._is_binary(os.path.join(self.test_dir, "file.jpg")))
        self.assertTrue(self.scanner._is_binary(os.path.join(self.test_dir, "archive.zip")))
        self.assertTrue(self.scanner._is_binary(os.path.join(self.test_dir, "document.pdf")))
        self.assertFalse(self.scanner._is_binary(os.path.join(self.test_dir, "file1.txt")))

    @patch('builtins.open', new_callable=mock_open)
    def test_is_binary_by_heuristic(self, mock_file_open):
        # Create a scanner that does not consider .txt or .custom as binary by extension for these tests
        scanner_for_heuristic_test = FileScanner(binary_extensions=[".bin", ".exe"]) # Ensure .txt, .custom are not here

        # Mock a file that contains null bytes - use .custom extension
        mock_file_open.return_value.read.return_value = b'This is text with a \x00 null byte.'
        self.assertTrue(scanner_for_heuristic_test._is_binary("some_file_null.custom"))

        # Mock a file with high proportion of non-text chars - use .custom extension
        mock_file_open.return_value.read.return_value = b'\x01\x02\x03\x04\x05abcde\x06\x07\x08\x09\x0a'
        self.assertTrue(scanner_for_heuristic_test._is_binary("some_file_nontext.custom"))

        # Mock a regular text file (no nulls, mostly text) - use .custom extension
        mock_file_open.return_value.read.return_value = b'This is a normal text file content.'
        self.assertFalse(scanner_for_heuristic_test._is_binary("normal_text_file.custom"))

        # Test with an empty file (should not be considered binary by heuristic) - use .custom
        mock_file_open.return_value.read.return_value = b''
        self.assertFalse(scanner_for_heuristic_test._is_binary("empty_for_binary_check.custom"))

        # Test file that fails to open (IOError) - should assume non-binary. Use non-binary ext for this.
        mock_file_open.side_effect = IOError("File not found")
        # Use the main self.scanner for this part, as it has default binary extensions
        # or scanner_for_heuristic_test, as long as .faux is not a binary ext for it.
        self.assertFalse(scanner_for_heuristic_test._is_binary("non_existent_file.faux"))

    def test_is_binary_empty_file(self):
        mock_file_path = os.path.join(self.test_dir, "empty.txt")
        with open(mock_file_path, 'w') as f:
            pass # Create empty file
        self.assertFalse(self.scanner._is_binary(mock_file_path))


    def test_scan_directory_default(self):
        # Test with default exclusions
        scanner = FileScanner() # exclude_dot_items is True by default
        # Make self.test_dir absolute for comparison
        abs_test_dir = os.path.abspath(self.test_dir)
        scanned_files = set(scanner.scan_directory(abs_test_dir))

        expected_files = set([
            os.path.join(abs_test_dir, "file1.txt"),
            os.path.join(abs_test_dir, "file2.py"),
            os.path.join(abs_test_dir, "another.txt"),
            os.path.join(abs_test_dir, "custom_exclude.ceu"), # Not excluded by default
            os.path.join(abs_test_dir, "subdir", "subfile.txt"),
            # .hiddenfile.txt, .git/config, venv/file should be excluded by default
        ])
        self.assertEqual(scanned_files, expected_files)

    def test_scan_directory_include_hidden(self):
        scanner = FileScanner(exclude_dot_items=False)
        abs_test_dir = os.path.abspath(self.test_dir)
        scanned_files = set(scanner.scan_directory(abs_test_dir))
        expected_files = set([
            os.path.join(abs_test_dir, "file1.txt"),
            os.path.join(abs_test_dir, "file2.py"),
            os.path.join(abs_test_dir, "another.txt"),
            os.path.join(abs_test_dir, "custom_exclude.ceu"),
            os.path.join(abs_test_dir, "subdir", "subfile.txt"),
            os.path.join(abs_test_dir, ".hiddenfile.txt"), # Included
            # os.path.join(abs_test_dir, ".git", "config"), # .git dir is excluded by default dirs
            # os.path.join(abs_test_dir, "venv", "file.py"), # venv dir is excluded by default dirs
            os.path.join(abs_test_dir, ".hidden_subdir", "another_hidden.txt"), # Included
            os.path.join(abs_test_dir, "subdir", ".hidden_subfile.txt") # Included
        ])
        # Filter out files that might be excluded by default dir/file exclusions 
        # because scan_directory itself applies these exclusions.
        filtered_expected = set()
        for f_path in expected_files:
            # Check if any part of the *relative* path from abs_test_dir would match default excluded dirs
            relative_to_test_dir = os.path.relpath(f_path, abs_test_dir)
            path_parts = relative_to_test_dir.split(os.sep)
            is_in_default_excluded_dir = False
            # Check if any parent directory name of the file is in DEFAULT_EXCLUDED_DIRS
            current_check_path = os.path.dirname(f_path)
            while current_check_path != abs_test_dir and current_check_path != os.path.dirname(abs_test_dir):
                if os.path.basename(current_check_path) in DEFAULT_EXCLUDED_DIRS:
                    is_in_default_excluded_dir = True
                    break
                current_check_path = os.path.dirname(current_check_path)
            
            if not is_in_default_excluded_dir:
                 filtered_expected.add(f_path)
        self.assertEqual(scanned_files, filtered_expected)


    def test_scan_directory_custom_exclude(self):
        custom_dirs = ["subdir"]
        custom_files = ["file1.txt"]
        custom_patterns = ["*.ceu"]
        scanner = FileScanner(
            excluded_dirs=custom_dirs,
            excluded_files=custom_files,
            custom_exclude_patterns=custom_patterns,
            exclude_dot_items=True # Explicitly keep dot items excluded for this test
        )
        abs_test_dir = os.path.abspath(self.test_dir)
        scanned_files = set(scanner.scan_directory(abs_test_dir))
        expected_files = set([
            # os.path.join(abs_test_dir, "file1.txt"), # Excluded by custom_files
            os.path.join(abs_test_dir, "file2.py"),
            os.path.join(abs_test_dir, "another.txt"),
            # os.path.join(abs_test_dir, "custom_exclude.ceu"), # Excluded by custom_patterns
            # os.path.join(abs_test_dir, "subdir", "subfile.txt"), # Excluded by custom_dirs
        ])
        self.assertEqual(scanned_files, expected_files)

if __name__ == '__main__':
    unittest.main() 