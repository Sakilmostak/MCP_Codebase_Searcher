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
                # Consider how to handle this - raise, or store error and make search a no-op?
                # For now, let's re-raise to make it obvious during development.
                raise ValueError(f"Invalid regex pattern: '{self.query}' - {e}")
        else:
            self.compiled_regex = None
            # For non-regex, case sensitivity is handled during search

    def _get_line_info_from_char_offset(self, content, char_offset):
        """Helper to get 0-based line index and 0-based char offset within that line."""
        if not hasattr(self, '_current_file_line_starts') or self._current_file_content_ref is not content:
            # Cache line starts for the current content to avoid re-calculating for every match in the same file
            self._current_file_line_starts = [0] + [i + 1 for i, char in enumerate(content) if char == '\n']
            self._current_file_content_ref = content # Store a reference to the content these line_starts belong to
        
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
            if content is None: # If reading failed, skip this file
                # _read_file_content already prints an error to stderr if it can't read/decode
                continue
            
            # Split content into lines for _generate_snippet
            # We use splitlines() without keepends=True as _generate_snippet reassembles with its own newlines.
            content_lines = content.splitlines() 

            matches_in_file = self._search_in_content(content, file_path) 
            
            for match_info in matches_in_file:
                # Ensure line_number from match_info is valid for content_lines
                # match_info['line_number'] is 1-based
                match_line_idx_0_based = match_info['line_number'] - 1

                if 0 <= match_line_idx_0_based < len(content_lines):
                    snippet = self._generate_snippet(
                        content_lines=content_lines, 
                        match_line_idx=match_line_idx_0_based, 
                        match_start_char_in_line=match_info['char_start_in_line'], 
                        match_end_char_in_line=match_info['char_end_in_line']
                        # file_path is no longer passed to _generate_snippet
                    )
                    all_results.append({
                        'file_path': file_path,
                        'line_number': match_info['line_number'], # Keep 1-based for output
                        'match_text': match_info['match_text'],
                        'char_start_in_line': match_info['char_start_in_line'], # Keep for potential future use
                        'char_end_in_line': match_info['char_end_in_line'],   # Keep for potential future use
                        'snippet': snippet
                    })
                else:
                    # This case should ideally not happen if _search_in_content is correct
                    # and content_lines is derived from the same content string.
                    # print(f"Warning: Line number {match_info['line_number']} out of bounds for file {file_path}. Skipping snippet.", file=sys.stderr)
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
            # Try latin-1 as a fallback
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
        if not self.query: # If the original query string is empty, return no matches.
            return matches
        if not content: # Ensure content is not None or empty
            return matches

        # Pre-calculate line start indices for quick line number lookup
        # line_starts[i] is the character offset of the start of line i+1 in the full content.
        line_starts = [0] + [i + 1 for i, char in enumerate(content) if char == '\n']
        
        def get_line_info_from_char_offset(full_content_char_offset):
            # Finds the 1-based line number and 0-based char offset within that line
            # for a given character offset in the full content.
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
                        'line_number': line_number, # 1-based
                        'match_text': match_text,
                        'char_start_in_line': char_start_in_line, # 0-based
                        'char_end_in_line': char_end_in_line    # 0-based
                    })
        else: # Plain string search
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
                # For plain string search, the length of the match is simply len(self.query)
                # We need the original casing for match_text from the original content.
                original_match_text = content[char_start_full : char_start_full + len(self.query)]
                
                line_number, char_start_in_line = get_line_info_from_char_offset(char_start_full)
                char_end_in_line = char_start_in_line + len(original_match_text) # Use len of original_match_text

                matches.append({
                    'line_number': line_number, # 1-based
                    'match_text': original_match_text,
                    'char_start_in_line': char_start_in_line, # 0-based
                    'char_end_in_line': char_end_in_line    # 0-based
                })
                current_pos = char_start_full + len(self.query) # Advance position
        
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
            line_number = i + 1 # 1-based line number for display
            line_content = content_lines[i]
            prefix = f"{line_number: >4}: " # Prefix already ends with a space

            if i == match_line_idx:
                actual_match_start = min(match_start_char_in_line, len(line_content))
                actual_match_end = min(match_end_char_in_line, len(line_content))

                before_match = line_content[:actual_match_start]
                match_text = line_content[actual_match_start:actual_match_end]
                after_match = line_content[actual_match_end:]

                # Ensure one space around markers, but respect original spacing if at start/end of line parts
                # If before_match is empty, no leading space for >>>. If it's not empty, ensure one space.
                # If after_match is empty, no trailing space for <<<. If it's not empty, ensure one space.
                
                # Simpler: just insert the markers. The original spacing of before_match and after_match is preserved.
                snippet_lines.append(f"{prefix}{before_match}>>>{match_text}<<<{after_match}")
            else:
                snippet_lines.append(f"{prefix}{line_content}") # Corrected: remove extra space here
        
        return "\n".join(snippet_lines)

# The __main__ block below was for temporary manual testing during Task 4 development.
# It has been superseded by the main CLI script mcp_searcher.py and unit tests.
# It is now removed to avoid confusion and potential SyntaxWarnings during import.

# if __name__ == '__main__':
#     print("MCP Search module direct execution (for testing during dev)")

#     # Create a temporary directory for test files
#     temp_dir = "temp_search_test_dir"
#     os.makedirs(temp_dir, exist_ok=True)

#     sample_file_1 = os.path.join(temp_dir, "sample1.txt")
#     with open(sample_file_1, "w") as f:
#         f.write("This is a sample file.\n")
#         f.write("It contains the word example several times.\n")
#         f.write("Another line with Example, and EXAMPLE.\n")
#         f.write("An example of a longer line with example repeated example example.\n")

#     sample_file_2 = os.path.join(temp_dir, "sample2.py")
#     with open(sample_file_2, "w") as f:
#         f.write("# Python example code\n")
#         f.write("def example_function():\n")
#         f.write("    # This function is an example\n")
#         f.write("    return \"example_string\"\n")
    
#     files_to_scan = [sample_file_1, sample_file_2]

#     print(f"\n--- Test 1: Plain string search (case-insensitive) for 'example' ---")
#     searcher1 = Searcher(query="example", is_case_sensitive=False, context_lines=1)
#     results1 = searcher1.search_files(files_to_scan)
#     for res in results1:
#         print(f"  File: {os.path.basename(res['file_path'])}, Line: {res['line_number']}, Match: '{res['match_text']}'")
#         print(f"  Snippet:\n{res['snippet']}")
#         print("  ----")

#     print(f"\n--- Test 2: Regex search (case-insensitive) for r'example\\w*' ---") 
#     # searcher2 = Searcher(query=r"example\w*", is_regex=True, is_case_sensitive=False, context_lines=1)
#     # Fixed regex: remove extra backslash if not intended to be literal
#     searcher2 = Searcher(query=r"example\\w*", is_regex=True, is_case_sensitive=False, context_lines=1)
#     try:
#         results2 = searcher2.search_files(files_to_scan)
#         for res in results2:
#             print(f"  File: {os.path.basename(res['file_path'])}, Line: {res['line_number']}, Match: '{res['match_text']}'")
#             print(f"  Snippet:\n{res['snippet']}")
#             print("  ----")
#     except ValueError as e:
#         print(f"Error during regex search: {e}")

#     print(f"\n--- Test 3: Plain string search (case-sensitive) for 'example' ---")
#     searcher3 = Searcher(query="example", is_case_sensitive=True, context_lines=2)
#     results3 = searcher3.search_files(files_to_scan)
#     for res in results3:
#         print(f"  File: {os.path.basename(res['file_path'])}, Line: {res['line_number']}, Match: '{res['match_text']}'")
#         print(f"  Snippet:\n{res['snippet']}")
#         print("  ----")

#     print(f"\n--- Test 4: No match search ---")
#     searcher4 = Searcher(query="nonexistentquery")
#     results4 = searcher4.search_files(files_to_scan)
#     if not results4:
#         print("  No matches found, as expected.")

    # # Clean up temporary directory
    # # import shutil
    # # shutil.rmtree(temp_dir)
    # print(f"\nNote: Temporary test directory '{temp_dir}' was NOT removed automatically.")
    # print("Please remove it manually if desired.") 