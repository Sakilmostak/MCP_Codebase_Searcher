# Module for mcp_search command logic

import re
import os # Added for file operations
import shutil # Added for cleanup
import sys # Added for printing to stderr

class Searcher:
    """Handles searching for a query within a list of files."""

    def __init__(self, query, is_case_sensitive=False, is_regex=False, context_lines=3):
        """
        Initializes the Searcher.

        Args:
            query (str): The search query (string or regex pattern).
            is_case_sensitive (bool, optional): Whether the search is case-sensitive. Defaults to False.
            is_regex (bool, optional): Whether the query is a regex pattern. Defaults to False.
            context_lines (int, optional): Number of lines of context to show before and after a match.
                                         Defaults to 3.
        """
        self.query = query
        self.is_case_sensitive = is_case_sensitive
        self.is_regex = is_regex
        self.context_lines = context_lines

        if self.is_regex:
            try:
                flags = 0 if self.is_case_sensitive else re.IGNORECASE
                self.compiled_regex = re.compile(self.query, flags)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: '{self.query}' - {e}")
        else:
            self.compiled_regex = None

    def _get_line_info_from_char_offset(self, content, char_offset):
        """Helper to get 0-based line index and 0-based char offset within that line."""
        if not hasattr(self, '_current_file_line_starts') or self._current_file_content_ref is not content:
            self._current_file_line_starts = [0] + [i + 1 for i, char in enumerate(content) if char == '\n']
            self._current_file_content_ref = content
        
        line_starts = self._current_file_line_starts
        line_idx = 0
        for i, start_idx in enumerate(line_starts):
            if char_offset >= start_idx:
                line_idx = i
            else:
                break
        char_offset_in_line = char_offset - line_starts[line_idx]
        return line_idx, char_offset_in_line

    def search_files(self, file_paths):
        """Searches for the query in a list of files."""
        all_results = []
        if not isinstance(file_paths, list):
            file_paths = [file_paths]

        for file_path in file_paths:
            content = self._read_file_content(file_path)
            if content is None:
                continue
            
            content_lines = content.splitlines() 
            matches_in_file = self._search_in_content(content, file_path)
            
            for match_info in matches_in_file:
                match_line_idx_0_based = match_info['line_number'] - 1

                if 0 <= match_line_idx_0_based < len(content_lines):
                    snippet = self._generate_snippet(
                        content_lines=content_lines, 
                        match_line_idx=match_line_idx_0_based, 
                        match_start_char_in_line=match_info['char_start_in_line'], 
                        match_end_char_in_line=match_info['char_end_in_line']
                    )
                    all_results.append({
                        'file_path': file_path,
                        'line_number': match_info['line_number'],
                        'match_text': match_info['match_text'],
                        'char_start_in_line': match_info['char_start_in_line'],
                        'char_end_in_line': match_info['char_end_in_line'],
                        'snippet': snippet
                    })
                else:
                    all_results.append({
                        'file_path': file_path,
                        'line_number': match_info['line_number'],
                        'match_text': match_info['match_text'],
                        'char_start_in_line': match_info['char_start_in_line'],
                        'char_end_in_line': match_info['char_end_in_line'],
                        'snippet': "[Error: Could not generate snippet due to line number mismatch]"
                    })
        return all_results

    def _read_file_content(self, file_path):
        """
        Reads the content of a text file.

        Args:
            file_path (str): The path to the file.

        Returns:
            str or None: The file content as a string, or None if reading fails.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    print(f"Warning: File '{file_path}' was not UTF-8. Falling back to 'latin-1' and succeeded.", file=sys.stderr)
                    return f.read()
            except Exception as e_fallback:
                print(f"Error: Could not decode file '{file_path}' with UTF-8 or latin-1. Error: {e_fallback}. Skipping file.", file=sys.stderr)
                return None
        except IOError as e:
            print(f"Error reading file '{file_path}': {e}. Skipping file.", file=sys.stderr)
            return None
        except Exception as e:
            print(f"Unexpected error when reading file '{file_path}': {e}. Skipping file.", file=sys.stderr)
            return None

    def _search_in_content(self, content, file_path):
        """
        Searches for the query within the given string content.

        Args:
            content (str): The text content to search within.
            file_path (str): The path of the file (for context/logging).

        Returns:
            list: A list of match information dicts with:
                  'line_number': 1-based line number in the file.
                  'match_text': The actual text that matched.
                  'char_start_in_line': 0-based start character offset of the match within its line.
                  'char_end_in_line': 0-based end character offset of the match within its line.
        """
        matches = []
        if not self.query or not content:
            return matches

        line_starts = [0] + [i + 1 for i, char in enumerate(content) if char == '\n']
        
        def get_line_info_from_char_offset(full_content_char_offset):
            line_num_1_based = 0
            char_offset_in_line_0_based = -1
            for i, start_idx_of_line in enumerate(line_starts):
                if full_content_char_offset >= start_idx_of_line:
                    line_num_1_based = i + 1 
                    char_offset_in_line_0_based = full_content_char_offset - start_idx_of_line
                else:
                    break
            return line_num_1_based, char_offset_in_line_0_based

        if self.is_regex:
            if self.compiled_regex:
                for match_obj in self.compiled_regex.finditer(content):
                    char_start_full = match_obj.span()[0]
                    match_text = match_obj.group(0)
                    line_number, char_start_in_line = get_line_info_from_char_offset(char_start_full)
                    char_end_in_line = char_start_in_line + len(match_text)
                    matches.append({
                        'line_number': line_number,
                        'match_text': match_text,
                        'char_start_in_line': char_start_in_line,
                        'char_end_in_line': char_end_in_line
                    })
        else:
            search_query_for_find = self.query
            haystack_for_find = content
            if not self.is_case_sensitive:
                search_query_for_find = search_query_for_find.lower()
                haystack_for_find = haystack_for_find.lower()
            
            current_pos = 0
            while current_pos < len(haystack_for_find):
                found_pos_full = haystack_for_find.find(search_query_for_find, current_pos)
                if found_pos_full == -1:
                    break
                char_start_full = found_pos_full 
                original_match_text = content[char_start_full : char_start_full + len(self.query)]
                line_number, char_start_in_line = get_line_info_from_char_offset(char_start_full)
                char_end_in_line = char_start_in_line + len(original_match_text)
                matches.append({
                    'line_number': line_number,
                    'match_text': original_match_text,
                    'char_start_in_line': char_start_in_line,
                    'char_end_in_line': char_end_in_line
                })
                current_pos = char_start_full + len(self.query)
        return matches

    def _generate_snippet(self, content_lines, match_line_idx, match_start_char_in_line, match_end_char_in_line):
        """
        Generates a context snippet around a match.
        
        Args:
            content_lines (list): List of strings, where each string is a line of the file.
            match_line_idx (int): The 0-based index of the line where the match occurred in content_lines.
            match_start_char_in_line (int): The 0-based start character index of the match within its line.
            match_end_char_in_line (int): The 0-based end character index of the match within its line.

        Returns:
            str: A formatted string snippet with context. Includes line numbers.
        """
        if not content_lines or match_line_idx < 0 or match_line_idx >= len(content_lines):
            return "[Error: Invalid match location for snippet generation]"

        start_line = max(0, match_line_idx - self.context_lines)
        end_line = min(len(content_lines), match_line_idx + self.context_lines + 1)

        snippet_lines = []
        for i in range(start_line, end_line):
            line_number = i + 1
            line_content = content_lines[i]
            prefix = f"{line_number: >4}: "

            if i == match_line_idx:
                actual_match_start = min(match_start_char_in_line, len(line_content))
                actual_match_end = min(match_end_char_in_line, len(line_content))
                
                # Ensure start <= end, even if original offsets were problematic
                if actual_match_start > actual_match_end:
                    actual_match_start = actual_match_end 

                # Defensive slicing and concatenation
                part_before = line_content[:actual_match_start] if actual_match_start > 0 else ""
                matched_part = line_content[actual_match_start:actual_match_end] if actual_match_start < actual_match_end else ""
                part_after = line_content[actual_match_end:] if actual_match_end < len(line_content) else ""
                
                # Ensure no empty string between >>> and <<< if matched_part is empty
                if matched_part:
                    highlighted_line = f"{prefix}{part_before}>>>{matched_part}<<<{part_after}"
                elif part_before or part_after: # If match is empty but line is not
                    highlighted_line = f"{prefix}{part_before}>>><<<{part_after}" # Show empty match location
                else: # Empty line with an empty match (edge case)
                     highlighted_line = f"{prefix}>>><<<"
                snippet_lines.append(highlighted_line)
            else:
                snippet_lines.append(f"{prefix}{line_content}")
        
        return "\n".join(snippet_lines)

if __name__ == '__main__':
    # Example Usage (primarily for testing during development)
    print("Searcher class defined. For comprehensive tests, see test_mcp_search.py")

    # Create dummy files for testing
    if not os.path.exists("_test_search_dir"):
        os.makedirs("_test_search_dir")
    with open("_test_search_dir/file1.txt", "w") as f:
        f.write("Hello world\nThis is a test file\nAnother line with world for testing")
    with open("_test_search_dir/file2.py", "w") as f:
        f.write("# Python code\ndef hello_world():\n    print(\"Hello world from Python\")")

    test_files = [
        os.path.join("_test_search_dir", "file1.txt"),
        os.path.join("_test_search_dir", "file2.py")
    ]

    print("\n--- Test 1: Simple string search (case-insensitive) ---")
    searcher1 = Searcher(query="world", is_case_sensitive=False, context_lines=1)
    results1 = searcher1.search_files(test_files)
    for res in results1:
        print(f"Found in {res['file_path']} at line {res['line_number']}:")
        print(res['snippet'])
        print("---")

    print("\n--- Test 2: Regex search (case-sensitive) ---")
    searcher2 = Searcher(query=r"Hello\\s*world", is_case_sensitive=True, is_regex=True, context_lines=2)
    results2 = searcher2.search_files(test_files)
    for res in results2:
        print(f"Found in {res['file_path']} at line {res['line_number']}:")
        print(res['snippet'])
        print("---")

    print("\n--- Test 3: No match ---")
    searcher3 = Searcher(query="nomatchstring")
    results3 = searcher3.search_files(test_files)
    if not results3:
        print("No matches found, as expected.")
    else:
        print(f"ERROR: Expected no matches, but found {len(results3)}")

    print("\n--- Test 4: Invalid Regex ---")
    try:
        Searcher(query="[", is_regex=True) # Invalid regex
        print("ERROR: Invalid regex did not raise ValueError")
    except ValueError as e:
        print(f"Caught expected error for invalid regex: {e}")
    
    # Cleanup dummy files
    if os.path.exists("_test_search_dir"):
        shutil.rmtree("_test_search_dir")
    print("\nCleanup complete.") 