import unittest
from unittest.mock import patch, mock_open
import os
import sys
import re
import builtins
import io

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.mcp_search import Searcher

class TestSearcher(unittest.TestCase):
    def setUp(self):
        self.test_dir = "temp_test_dir_searcher"
        os.makedirs(self.test_dir, exist_ok=True)

        self.sample_files = {
            "file1.txt": "Hello world\nSecond line with world\nThird line, no match.",
            "file2.py": "# Python code\ndef hello_world():\n    print(\"HELLO WORLD\")",
            "empty.txt": "",
            "binary_like.dat": b"\x00\x01\x02hello\x03\x04", # To test reading non-utf8
            "accented.txt": "Héllo wørld\nSecønd line with wørld",
            "long_match.txt": "abc\ndefghijklmnopqrstuvwxyz\n0123456789"
        }

        for name, content in self.sample_files.items():
            mode = 'wb' if isinstance(content, bytes) else 'w'
            with open(os.path.join(self.test_dir, name), mode, encoding=None if isinstance(content, bytes) else 'utf-8') as f:
                f.write(content)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_init_regex_compilation(self):
        searcher_regex = Searcher(query="w.rld", is_regex=True)
        self.assertIsNotNone(searcher_regex.compiled_regex)
        searcher_no_regex = Searcher(query="world", is_regex=False)
        self.assertIsNone(searcher_no_regex.compiled_regex)
        with self.assertRaises(ValueError):
            Searcher(query="[", is_regex=True) # Invalid regex

    def test_read_file_content_success(self):
        searcher = Searcher("test")
        content = searcher._read_file_content(os.path.join(self.test_dir, "file1.txt"))
        self.assertEqual(content, self.sample_files["file1.txt"])

    def test_read_file_content_utf8_fallback_latin1(self):
        searcher = Searcher("test")
        # Create a file that is not UTF-8 but can be read by latin-1
        latin1_content = "Héllo Wørld".encode('latin-1')
        latin1_file_path = os.path.join(self.test_dir, "latin1_file.txt")
        with open(latin1_file_path, 'wb') as f:
            f.write(latin1_content)
        
        # Mock open to first raise UnicodeDecodeError with utf-8, then succeed with latin-1
        mock_calls = []
        original_open = builtins.open
        def mock_latin1_open_effect(file, mode, encoding=None, **kwargs):
            mock_calls.append((file, mode, encoding))
            if encoding == 'utf-8' and file == latin1_file_path:
                raise UnicodeDecodeError("utf-8", b'', 0, 1, "reason")
            return original_open(file, mode, encoding=encoding, **kwargs)

        with patch('builtins.open', side_effect=mock_latin1_open_effect):
            with patch('sys.stderr', new_callable=io.StringIO) as mock_err:
                content = searcher._read_file_content(latin1_file_path)
                self.assertEqual(content, "Héllo Wørld")
                # Check that it tried utf-8 first
                self.assertIn((latin1_file_path, 'r', 'utf-8'), mock_calls)
                # Then latin-1
                self.assertIn((latin1_file_path, 'r', 'latin-1'), mock_calls)
                self.assertIn("falling back to 'latin-1'", mock_err.getvalue().lower())

    def test_read_file_content_failure(self):
        searcher = Searcher("test")
        with patch('sys.stderr', new_callable=io.StringIO) as mock_err:
            content = searcher._read_file_content(os.path.join(self.test_dir, "non_existent.txt"))
            self.assertIsNone(content)
            self.assertIn(f"error reading file \'{os.path.join(self.test_dir, "non_existent.txt")}\':", mock_err.getvalue().lower())

        # Test unreadable file (UTF-16 BOM, which latin-1 will decode, but it's not UTF-8)
        unreadable_file_path = os.path.join(self.test_dir, "unreadable.txt")
        with open(unreadable_file_path, 'wb') as f:
            f.write(b'\xff\xfe') # UTF-16 BOM
        
        with patch('sys.stderr', new_callable=io.StringIO) as mock_err:
            content = searcher._read_file_content(unreadable_file_path)
            self.assertEqual(content, "\u00ff\u00fe") # Expect latin-1 decoded garbage 'ÿþ'
            self.assertIn(f"warning: file '{unreadable_file_path}' was not utf-8. falling back to 'latin-1' and succeeded.", mock_err.getvalue().lower())

    def test_search_in_content_string_case_insensitive(self):
        searcher = Searcher(query="world", is_case_sensitive=False)
        content = "Hello world\nHELLO WORLD\nNo match"
        matches = searcher._search_in_content(content, "test.txt")
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0]['line_number'], 1)
        self.assertEqual(matches[0]['char_start_in_line'], 6)
        self.assertEqual(matches[0]['char_end_in_line'], 11)
        self.assertEqual(matches[0]['match_text'], "world")
        self.assertEqual(matches[1]['line_number'], 2)
        self.assertEqual(matches[1]['char_start_in_line'], 6)
        self.assertEqual(matches[1]['char_end_in_line'], 11)
        self.assertEqual(matches[1]['match_text'], "WORLD")

    def test_search_in_content_string_case_sensitive(self):
        searcher = Searcher(query="world", is_case_sensitive=True)
        content = "Hello world\nHELLO WORLD\nNo match"
        matches = searcher._search_in_content(content, "test.txt")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['line_number'], 1)
        self.assertEqual(matches[0]['char_start_in_line'], 6)
        self.assertEqual(matches[0]['char_end_in_line'], 11)
        self.assertEqual(matches[0]['match_text'], "world")

    def test_search_in_content_regex_case_insensitive(self):
        searcher = Searcher(query="w.rld", is_regex=True, is_case_sensitive=False)
        content = "Hello world\nTest WØRLD\nNo match"
        matches = searcher._search_in_content(content, "test.txt")
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0]['match_text'], "world")
        self.assertEqual(matches[1]['match_text'], "WØRLD")

    def test_search_in_content_regex_case_sensitive(self):
        searcher = Searcher(query="w.rld", is_regex=True, is_case_sensitive=True)
        content = "Hello world\nTest WØRLD\nNo match"
        matches = searcher._search_in_content(content, "test.txt")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['match_text'], "world")

    def test_search_in_content_multiple_matches_on_line(self):
        searcher = Searcher(query="world")
        content = "world world world\nworld"
        matches = searcher._search_in_content(content, "test.txt")
        self.assertEqual(len(matches), 4)
        self.assertEqual(matches[0]['line_number'], 1)
        self.assertEqual(matches[0]['char_start_in_line'], 0)
        self.assertEqual(matches[1]['line_number'], 1)
        self.assertEqual(matches[1]['char_start_in_line'], 6)
        self.assertEqual(matches[2]['line_number'], 1)
        self.assertEqual(matches[2]['char_start_in_line'], 12)
        self.assertEqual(matches[3]['line_number'], 2)
        self.assertEqual(matches[3]['char_start_in_line'], 0)

    def test_search_in_content_accented(self):
        searcher = Searcher(query="wørld", is_case_sensitive=False)
        content = self.sample_files["accented.txt"]
        matches = searcher._search_in_content(content, "accented.txt")
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0]['match_text'], "wørld")
        self.assertEqual(matches[1]['match_text'], "wørld")

    def test_search_in_content_no_match(self):
        searcher = Searcher(query="nomatch")
        content = "Hello world"
        matches = searcher._search_in_content(content, "test.txt")
        self.assertEqual(len(matches), 0)

    def test_search_in_content_empty_query(self):
        searcher = Searcher(query="") # Empty string query
        content = "Hello world"
        matches = searcher._search_in_content(content, "test.txt")
        self.assertEqual(len(matches), 0, "Empty plain string query should return no matches")

        searcher_regex = Searcher(query="", is_regex=True)
        matches_regex = searcher_regex._search_in_content(content, "test.txt")
        # Current behavior: if not self.query returns empty list, even for regex.
        self.assertEqual(len(matches_regex), 0, "Empty regex query currently returns no matches due to initial query check")

    def test_generate_snippet_basic(self):
        searcher = Searcher("world", context_lines=1)
        content_lines = "Line 1\nHello world match\nLine 3".splitlines()
        # world is at line 1 (0-indexed in content_lines), char 6-11
        # Match info: line_number=2 (1-based for user), char_start_in_line=6, char_end_in_line=11
        snippet = searcher._generate_snippet(content_lines, 1, 6, 11)
        expected = "   1: Line 1\n   2: Hello >>>world<<< match\n   3: Line 3"
        self.assertEqual(snippet, expected)

    def test_generate_snippet_start_of_file(self):
        searcher = Searcher("Hello", context_lines=1)
        content_lines = "Hello world\nLine 2\nLine 3".splitlines()
        # Hello is at line 0 (0-indexed in content_lines), char 0-5
        snippet = searcher._generate_snippet(content_lines, 0, 0, 5)
        expected = "   1: >>>Hello<<< world\n   2: Line 2"
        self.assertEqual(snippet, expected)

    def test_generate_snippet_end_of_file(self):
        searcher = Searcher("Line 3", context_lines=1)
        content_lines = "Line 1\nLine 2\nLine 3 match".splitlines()
        # Line 3 is at line 2 (0-indexed in content_lines), char 0-6
        snippet = searcher._generate_snippet(content_lines, 2, 0, 6)
        expected = "   2: Line 2\n   3: >>>Line 3<<< match"
        self.assertEqual(snippet, expected)

    def test_generate_snippet_no_context_lines(self):
        searcher = Searcher("world", context_lines=0)
        content_lines = "Line 1\nHello world match\nLine 3".splitlines()
        snippet = searcher._generate_snippet(content_lines, 1, 6, 11)
        expected = "   2: Hello >>>world<<< match"
        self.assertEqual(snippet, expected)

    def test_generate_snippet_large_context(self):
        searcher = Searcher("Line 3", context_lines=3)
        content_lines = "Line 1\nLine 2\nLine 3 match\nLine 4\nLine 5".splitlines()
        snippet = searcher._generate_snippet(content_lines, 2, 0, 6)
        expected = "   1: Line 1\n   2: Line 2\n   3: >>>Line 3<<< match\n   4: Line 4\n   5: Line 5"
        self.assertEqual(snippet, expected)

    def test_generate_snippet_match_multiple_lines_highlights_first_occurrence_line(self):
        searcher = Searcher(query="unused", context_lines=1) # query doesn't matter for _generate_snippet directly
        content_lines = "abc\ndef ghijk lmnopqrstuvwxyz\n0123456789".splitlines()
        # Match 'ghijk' on line index 1 (0-indexed in content_lines)
        # Line content: "def ghijk lmnopqrstuvwxyz"
        # 'g' is at char index 4, 'k' ends at char index 9 (exclusive end)
        snippet = searcher._generate_snippet(content_lines, 1, 4, 9)
        # Expected: Line 1 (abc), Line 2 (def >>>ghijk<<< lmnopqrstuvwxyz), Line 3 (0123...)
        # Prefix is "N: "
        expected = (
            "   1: abc\n"
            "   2: def >>>ghijk<<< lmnopqrstuvwxyz\n"
            "   3: 0123456789"
        )
        self.assertEqual(snippet, expected)

    def test_generate_snippet_char_offset_handling(self):
        searcher = Searcher("char", context_lines=0)
        content_lines_single = "Test char offset".splitlines()
        snippet_single = searcher._generate_snippet(content_lines_single, 0, 5, 9)
        self.assertEqual(snippet_single, "   1: Test >>>char<<< offset")

        content_lines_multi = "First line\nSecond char line\nThird line".splitlines()
        snippet_multi = searcher._generate_snippet(content_lines_multi, 1, 7, 11)
        self.assertEqual(snippet_multi, "   2: Second >>>char<<< line")

    def test_generate_snippet_unicode_content(self):
        searcher = Searcher("wørld", context_lines=1)
        content_lines = self.sample_files["accented.txt"].splitlines() # "Héllo wørld\nSecønd line with wørld"
        snippet = searcher._generate_snippet(content_lines, 0, 6, 11)
        expected = "   1: Héllo >>>wørld<<<\n   2: Secønd line with wørld"
        self.assertEqual(snippet, expected)

    def test_search_files_single_file_match(self):
        searcher = Searcher("world")
        results = searcher.search_files([os.path.join(self.test_dir, "file1.txt")])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['file_path'], os.path.join(self.test_dir, "file1.txt"))
        self.assertIn(">>>world<<<", results[0]['snippet'])

    def test_search_files_multiple_files(self):
        searcher = Searcher("world", is_case_sensitive=False)
        file_paths = [
            os.path.join(self.test_dir, "file1.txt"), 
            os.path.join(self.test_dir, "file2.py")
        ]
        results = searcher.search_files(file_paths)
        self.assertEqual(len(results), 4) # 2 in file1, 2 in file2 (world in hello_world, and WORLD in HELLO WORLD)

    def test_search_files_no_match_in_any_file(self):
        searcher = Searcher("gibberish_no_match_anywhere")
        results = searcher.search_files([os.path.join(self.test_dir, "file1.txt")])
        self.assertEqual(len(results), 0)

    def test_search_files_empty_file(self):
        searcher = Searcher("world")
        results = searcher.search_files([os.path.join(self.test_dir, "empty.txt")])
        self.assertEqual(len(results), 0)

    def test_search_files_non_existent_file(self):
        searcher = Searcher("test")
        file_path = os.path.join(self.test_dir, "non_existent_file.txt")
        with patch('sys.stderr', new_callable=io.StringIO) as mock_err:
            results = searcher.search_files([file_path])
            self.assertEqual(len(results), 0)
            # Check if the warning about the non-existent file was printed to stderr
            self.assertIn(f"error reading file \'{file_path}\':", mock_err.getvalue().lower())

    def test_get_line_info_from_char_offset(self):
        searcher = Searcher("test")
        content = "First line\nSecond line\nThird line"
        # Test various offsets
        # "First line" (Line 0)
        line_num, offset = searcher._get_line_info_from_char_offset(content, 0) # Start of file
        self.assertEqual(line_num, 0) # Expect 0-based index
        self.assertEqual(offset, 0)
        line_num, offset = searcher._get_line_info_from_char_offset(content, 5) # Middle of "First"
        self.assertEqual(line_num, 0)
        self.assertEqual(offset, 5)
        line_num, offset = searcher._get_line_info_from_char_offset(content, 10) # End of "First line"
        self.assertEqual(line_num, 0)
        self.assertEqual(offset, 10)

        # "Second line" (Line 1)
        line_num, offset = searcher._get_line_info_from_char_offset(content, 11) # Start of "Second line" (after \n)
        self.assertEqual(line_num, 1)
        self.assertEqual(offset, 0)
        line_num, offset = searcher._get_line_info_from_char_offset(content, 18) # Middle of "Second line"
        self.assertEqual(line_num, 1)
        self.assertEqual(offset, 7)

        # "Third line" (Line 2)
        line_num, offset = searcher._get_line_info_from_char_offset(content, 23) # Start of "Third line"
        self.assertEqual(line_num, 2)
        self.assertEqual(offset, 0)
        
        # Offset past end of content (should still give last line info)
        line_num, offset = searcher._get_line_info_from_char_offset(content, 100)
        self.assertEqual(line_num, 2) # Stays on the last line
        self.assertEqual(offset, 100 - content.rfind('\n', 0, 100) -1)

    def test_get_line_info_from_char_offset_empty_content(self):
        searcher = Searcher("test")
        content = ""
        line_num, offset = searcher._get_line_info_from_char_offset(content, 0)
        self.assertEqual(line_num, 0) # Expect 0-based index for empty content
        self.assertEqual(offset, 0)
        line_num, offset = searcher._get_line_info_from_char_offset(content, 10) # Offset beyond empty
        self.assertEqual(line_num, 0)
        self.assertEqual(offset, 10)

    def test_get_line_info_from_char_offset_single_line(self):
        searcher = Searcher("test")
        content = "This is a single line."
        line_num, offset = searcher._get_line_info_from_char_offset(content, 0)
        self.assertEqual(line_num, 0) # Expect 0-based index
        self.assertEqual(offset, 0)
        line_num, offset = searcher._get_line_info_from_char_offset(content, 10)
        self.assertEqual(line_num, 0)
        self.assertEqual(offset, 10)
        line_num, offset = searcher._get_line_info_from_char_offset(content, len(content))
        self.assertEqual(line_num, 0)
        self.assertEqual(offset, len(content))


if __name__ == '__main__':
    unittest.main() 