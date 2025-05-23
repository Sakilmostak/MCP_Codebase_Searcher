import unittest
import os
import shutil
import tempfile
import fnmatch # Though not directly used in test, it's a core part of FileScanner

# Assuming file_scanner.py is in the same directory or accessible via PYTHONPATH
from file_scanner import FileScanner, DEFAULT_EXCLUDED_DIRS, DEFAULT_EXCLUDED_FILES, DEFAULT_BINARY_EXTENSIONS

class TestFileScanner(unittest.TestCase):

    def setUp(self):
        """Set up a temporary test directory and common scanner instance."""
        self.test_root_dir = tempfile.mkdtemp(prefix="test_filescanner_root_")
        # print(f"DEBUG: Test setUp created temp dir: {self.test_root_dir}") # Optional debug

        # Create a standard directory structure for many tests
        os.makedirs(os.path.join(self.test_root_dir, "documents"))
        os.makedirs(os.path.join(self.test_root_dir, "images"))
        os.makedirs(os.path.join(self.test_root_dir, ".git"))
        os.makedirs(os.path.join(self.test_root_dir, "venv"))
        os.makedirs(os.path.join(self.test_root_dir, "src", "temp_dir")) # For custom exclusion
        os.makedirs(os.path.join(self.test_root_dir, "src", "actual_code"))
        os.makedirs(os.path.join(self.test_root_dir, "empty_dir"))

        # Create common files
        self._create_file(os.path.join("documents", "report.txt"), "This is a text report.")
        self._create_file(os.path.join("src", "main.py"), "print('hello world')")
        self._create_file(os.path.join("src", "actual_code", "module.py"), "def func(): pass")
        self._create_file(os.path.join("documents", "notes.log"), "log entry") # Excluded by default
        self._create_file(os.path.join("src", "temp_script.tmp"), "temporary") # Excluded by default
        self._create_file("specific_custom_exclude.txt", "custom content") # For custom exclusion test
        self._create_file(os.path.join("src", "temp_dir", "in_temp.txt"), "inside temp dir") # Excluded by custom rule
        self._create_file(os.path.join("images", "logo.png"), b'\x89PNG\r\n\x1a\n', is_binary=True) # Binary by ext
        self._create_file(os.path.join("src", "compiled.o"), b'\xDE\xAD\xBE\xEF', is_binary=True) # Binary by ext
        self._create_file(os.path.join("documents", "binary_no_ext"), b'null\x00byte', is_binary=True) # Binary by heuristic
        self._create_file(os.path.join(".git", "config"), "git config content") # In excluded dir
        self._create_file(os.path.join("venv", "pyvenv.cfg"), "venv config content") # In excluded dir
        self._create_file("empty_file.txt", "") # Empty file, should be scanned

        self.scanner_default = FileScanner()
        self.scanner_custom = FileScanner(
            excluded_dirs=['.my_venv'],
            excluded_files=['*.customlog'],
            binary_extensions=['.custombin'],
            custom_exclude_patterns=['custom_dir/*', '*_custom_exclude_file.txt']
        )

    def _create_file(self, relative_path, content, is_binary=False):
        """Helper to create a file in the test_root_dir."""
        file_path = os.path.join(self.test_root_dir, relative_path)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        mode = 'wb' if is_binary else 'w'
        with open(file_path, mode) as f:
            f.write(content)
        return file_path

    def tearDown(self):
        """Clean up the temporary test directory."""
        # print(f"DEBUG: Test tearDown removing temp dir: {self.test_root_dir}") # Optional debug
        shutil.rmtree(self.test_root_dir)

    def test_scan_directory_default_exclusions(self):
        """Test scan_directory with default scanner settings."""
        found_files = self.scanner_default.scan_directory(self.test_root_dir)
        found_basenames = sorted([os.path.basename(f) for f in found_files])
        
        expected_basenames = sorted([
            "report.txt", 
            "main.py", 
            "module.py",
            "specific_custom_exclude.txt", # Not excluded by default scanner
            "in_temp.txt",                 # Not excluded by default scanner
            "empty_file.txt"
        ])
        
        self.assertEqual(found_basenames, expected_basenames,
                         f"Expected {expected_basenames} but got {found_basenames}")

    # --- Tests for _is_excluded --- 
    def test_is_excluded_directories_default(self):
        """Test _is_excluded for directories with default rules."""
        # Default excluded dirs
        self.assertTrue(self.scanner_default._is_excluded(os.path.join(self.test_root_dir, ".git"), self.test_root_dir, is_dir=True))
        self.assertTrue(self.scanner_default._is_excluded(os.path.join(self.test_root_dir, "venv"), self.test_root_dir, is_dir=True))
        # Non-excluded dirs
        self.assertFalse(self.scanner_default._is_excluded(os.path.join(self.test_root_dir, "documents"), self.test_root_dir, is_dir=True))
        self.assertFalse(self.scanner_default._is_excluded(os.path.join(self.test_root_dir, "src"), self.test_root_dir, is_dir=True))

    def test_is_excluded_files_default(self):
        """Test _is_excluded for files with default rules."""
        # Default excluded files by pattern
        self.assertTrue(self.scanner_default._is_excluded(os.path.join(self.test_root_dir, "some.log"), self.test_root_dir, is_dir=False))
        self.assertTrue(self.scanner_default._is_excluded(os.path.join(self.test_root_dir, "other.tmp"), self.test_root_dir, is_dir=False))
        # Non-excluded files
        self.assertFalse(self.scanner_default._is_excluded(os.path.join(self.test_root_dir, "report.txt"), self.test_root_dir, is_dir=False))
        self.assertFalse(self.scanner_default._is_excluded(os.path.join(self.test_root_dir, "main.py"), self.test_root_dir, is_dir=False))

    def test_is_excluded_directories_custom(self):
        """Test _is_excluded for directories with custom rules."""
        # Custom excluded dirs (from self.scanner_custom)
        # self.scanner_custom has custom_exclude_patterns=['custom_dir/*', '*_custom_exclude_file.txt']
        # and excluded_dirs=['.my_venv']
        
        # Test custom excluded_dirs list
        self._create_file(os.path.join(".my_venv", "some_file"), "content") # Directory will be created by _create_file
        self.assertTrue(self.scanner_custom._is_excluded(os.path.join(self.test_root_dir, ".my_venv"), self.test_root_dir, is_dir=True))
        
        # Test custom_exclude_patterns for directories
        self._create_file(os.path.join("custom_dir", "another_file.txt"), "content")
        self.assertTrue(self.scanner_custom._is_excluded(os.path.join(self.test_root_dir, "custom_dir"), self.test_root_dir, is_dir=True))
        # Check a non-matching dir for custom patterns
        self.assertFalse(self.scanner_custom._is_excluded(os.path.join(self.test_root_dir, "documents"), self.test_root_dir, is_dir=True))
        # Check default excluded (like .git) are NOT necessarily excluded if custom scanner overrides excluded_dirs
        # self.scanner_custom has excluded_dirs = ['.my_venv'] so .git should NOT be excluded by this list.
        self.assertFalse(self.scanner_custom._is_excluded(os.path.join(self.test_root_dir, ".git"), self.test_root_dir, is_dir=True))

    def test_is_excluded_files_custom(self):
        """Test _is_excluded for files with custom rules."""
        # Custom excluded_files list (from self.scanner_custom): ['*.customlog']
        self.assertTrue(self.scanner_custom._is_excluded(os.path.join(self.test_root_dir, "audit.customlog"), self.test_root_dir, is_dir=False))
        self.assertFalse(self.scanner_custom._is_excluded(os.path.join(self.test_root_dir, "normal.log"), self.test_root_dir, is_dir=False)) # Default still applies

        # Custom custom_exclude_patterns for files: ['*_custom_exclude_file.txt']
        self.assertTrue(self.scanner_custom._is_excluded(os.path.join(self.test_root_dir, "my_custom_exclude_file.txt"), self.test_root_dir, is_dir=False))
        self.assertFalse(self.scanner_custom._is_excluded(os.path.join(self.test_root_dir, "another_file.txt"), self.test_root_dir, is_dir=False))
        # Ensure pattern doesn't wrongly exclude directories
        self.assertFalse(self.scanner_custom._is_excluded(os.path.join(self.test_root_dir, "a_custom_exclude_file.txt_dir"), self.test_root_dir, is_dir=True))

    # --- Tests for _is_binary --- 
    def test_is_binary_by_extension(self):
        """Test _is_binary for files with known binary extensions."""
        # Using self.scanner_default which has DEFAULT_BINARY_EXTENSIONS
        self.assertTrue(self.scanner_default._is_binary(self._create_file("test.png", b"fake png data", is_binary=True)))
        self.assertTrue(self.scanner_default._is_binary(self._create_file("test.jpg", b"fake jpg data", is_binary=True)))
        self.assertTrue(self.scanner_default._is_binary(self._create_file("program.exe", b"binary", is_binary=True)))
        self.assertTrue(self.scanner_default._is_binary(self._create_file("archive.zip", b"zip", is_binary=True)))
        # Test with a custom binary extension scanner
        self.assertTrue(self.scanner_custom._is_binary(self._create_file("data.custombin", b"custom binary", is_binary=True)))
        # A default binary ext (like .png) is NOT binary for self.scanner_custom because binary_extensions was overridden.
        self.assertFalse(self.scanner_custom._is_binary(self._create_file("another.png", b"fake png data", is_binary=True)))
        # A non-binary extension
        self.assertFalse(self.scanner_default._is_binary(self._create_file("text_file.txt", "text")))

    def test_is_binary_by_null_byte(self):
        """Test _is_binary for files containing null bytes."""
        path_with_null = self._create_file("has_null.dat", b"hello\x00world", is_binary=True)
        self.assertTrue(self.scanner_default._is_binary(path_with_null))
        path_without_null = self._create_file("no_null.txt", "hello world")
        self.assertFalse(self.scanner_default._is_binary(path_without_null))

    def test_is_binary_by_heuristic_ratio(self):
        """Test _is_binary heuristic for non-text character ratio."""
        # Create content with more than 20% non-text chars (e.g., control chars 1-31)
        mostly_binary_content = b"abc" + bytes(range(1, 20)) # 3 text, 19 non-text (out of 22 total -> ~86% non-text)
        path_mostly_binary = self._create_file("mostly_binary.dat", mostly_binary_content, is_binary=True)
        self.assertTrue(self.scanner_default._is_binary(path_mostly_binary))

        mostly_text_content = b"This is mostly text with a few non-printable \x01\x02 characters."
        path_mostly_text = self._create_file("mostly_text.txt", mostly_text_content, is_binary=True) # is_binary=True for wb mode
        self.assertFalse(self.scanner_default._is_binary(path_mostly_text))
        
    def test_is_binary_text_files(self):
        """Test _is_binary for various simple text files."""
        self.assertFalse(self.scanner_default._is_binary(self._create_file("simple.txt", "Hello world.")))
        self.assertFalse(self.scanner_default._is_binary(self._create_file("code.py", "def foo():\n  pass")))
        long_text_content = '''# Markdown\nSome more text here with numbers 12345 and symbols !@#$%^&*()_+-={}|[]\\:';<>,.?/'''
        self.assertFalse(self.scanner_default._is_binary(self._create_file("longer_text.md", long_text_content)))

    def test_is_binary_empty_file(self):
        """Test _is_binary for empty files (should be False)."""
        empty_path = self._create_file("empty.txt", "")
        self.assertFalse(self.scanner_default._is_binary(empty_path))

    # --- Test for scan_directory with custom scanner ---
    def test_scan_directory_custom_scanner(self):
        """Test scan_directory with the custom scanner instance."""
        # self.scanner_custom definitions:
        # excluded_dirs=['.my_venv'],
        # excluded_files=['*.customlog'],
        # binary_extensions=['.custombin'],
        # custom_exclude_patterns=['custom_dir/*', '*_custom_exclude_file.txt']

        # Create files specific to custom scanner rules
        self._create_file(os.path.join(".my_venv", "config"), "my venv data")
        self._create_file("audit.customlog", "custom log data")
        self._create_file("archive.custombin", b"custom binary data", is_binary=True)
        self._create_file(os.path.join("custom_dir", "file_in_custom_dir.txt"), "should be excluded by dir pattern")
        self._create_file("a_real_custom_exclude_file.txt", "this file should be excluded by pattern")

        # Re-use some files from setUp that should behave differently or same with custom scanner
        # - "report.txt", "main.py", "module.py", "empty_file.txt" should still be found.
        # - "specific_custom_exclude.txt" (from setUp) is NOT matched by '*_custom_exclude_file.txt'
        # - "in_temp.txt" (from setUp, in src/temp_dir) is NOT matched by 'custom_dir/*'
        # - ".git", "venv" (default excluded dirs) are NOT in scanner_custom.excluded_dirs, so files within them should be found if not otherwise excluded.
        #   - .git/config, venv/pyvenv.cfg (created in setUp)
        # - logo.png, compiled.o (default binary extensions) are NOT in scanner_custom.binary_extensions
        #   so they will be scanned unless their content is deemed binary by heuristic (which is unlikely for their simple fake content)
        #   Let's assume "fake png data" and "0xDEADBEEF" are treated as text by heuristic for this test case.
        #   If not, the test needs more robust non-heuristic binary content for these.
        #   For simplicity, let's assume they pass the heuristic for now. Modifying their content to be simple text for custom scan test.
        self._create_file(os.path.join("images", "logo.png"), "actually text now") # Override for custom test
        self._create_file(os.path.join("src", "compiled.o"), "also text now")   # Override for custom test

        found_files = self.scanner_custom.scan_directory(self.test_root_dir)
        found_basenames = sorted([os.path.basename(f) for f in found_files])

        expected_basenames = sorted([
            "report.txt", 
            "main.py", 
            "module.py",
            "empty_file.txt",
            "specific_custom_exclude.txt", # Not excluded by this custom scanner's rules
            "in_temp.txt",                 # Not excluded by this custom scanner's rules
            "config",                      # From .git/config, .git dir not excluded by custom
            "pyvenv.cfg",                  # From venv/pyvenv.cfg, venv dir not excluded by custom
            "logo.png",                    # Default binary ext, but not for custom scanner + content is text
            "compiled.o",                  # Default binary ext, but not for custom scanner + content is text
            "notes.log",                   # Default excluded, but not by custom_scanner's excluded_files
            "temp_script.tmp",             # Default excluded, but not by custom_scanner's excluded_files
        ])

        self.assertEqual(found_basenames, expected_basenames,
                         f"Expected {expected_basenames} but got {found_basenames}")

if __name__ == '__main__':
    unittest.main() 