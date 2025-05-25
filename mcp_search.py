# Module for mcp_search command logic

import re
import os # Added for file operations
import shutil # Added for cleanup

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
        """
        Searches for the query in the provided list of file paths.

        Args:
            file_paths (list): A list of absolute paths to files to search.

        Returns:
            list: A list of search results. Each result is a dictionary containing:
                  {'file_path': str, 'line_number': int, 'match_text': str, 'snippet': str}
        """
        all_results = []
        # Clear any cached line_starts from a previous call to search_files
        if hasattr(self, '_current_file_line_starts'):
            del self._current_file_line_starts
        if hasattr(self, '_current_file_content_ref'):
            del self._current_file_content_ref

        if not isinstance(file_paths, list):
            file_paths = [file_paths]

        for file_path in file_paths:
            content = self._read_file_content(file_path)
            if content is None:
                continue

            content_lines = content.splitlines() # Keep newlines for char offsets, but split for line iteration
            matches_in_file = self._search_in_content(content, file_path)

            for match_info in matches_in_file:
                # match_info contains: line_number (1-based), match_text, char_start, char_end (global in content)
                
                # Get 0-based line index and 0-based char offset within that line for snippet generation
                match_line_idx, match_start_char_in_line = self._get_line_info_from_char_offset(content, match_info['char_start'])
                _, match_end_char_in_line = self._get_line_info_from_char_offset(content, match_info['char_end'])
                
                # Adjust end char if it's at the start of a new line due to the match ending exactly on \n
                # This adjustment is tricky. If a match ends with \n, char_end is after \n.
                # The line identified by match_line_idx will be correct.
                # match_end_char_in_line might be 0 for the *next* line if match ends exactly at \n.
                # However, _generate_snippet expects char_end_in_line to be within the match_line_idx.
                # If char_end_in_line is 0 and it came from char_end pointing to the start of next line,
                # it means the match consumed the entire current line up to its newline.
                # So, end_char_in_line for snippet on match_line_idx should be len(content_lines[match_line_idx])
                if match_info['char_end'] > match_info['char_start'] and \
                   match_end_char_in_line == 0 and \
                   match_info['char_end'] > 0 and content[match_info['char_end']-1] == '\n':
                    match_end_char_in_line = len(content_lines[match_line_idx]) 

                snippet = self._generate_snippet(
                    content_lines,
                    match_line_idx, 
                    match_start_char_in_line, 
                    match_end_char_in_line
                )
                all_results.append({
                    'file_path': file_path,
                    'line_number': match_info['line_number'], # Already 1-based from _search_in_content
                    'match_text': match_info['match_text'],
                    'snippet': snippet
                })
            
            # Clear cached line_starts for the next file
            if hasattr(self, '_current_file_line_starts'):
                del self._current_file_line_starts
            if hasattr(self, '_current_file_content_ref'):
                del self._current_file_content_ref
        
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
            # print(f"Warning: Could not decode file {file_path} as UTF-8. Skipping.") # Consider logging
            # For now, we'll try a fallback encoding if UTF-8 fails.
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    # print(f"Successfully decoded {file_path} with latin-1.") # Consider logging
                    return f.read()
            except Exception as e_fallback: # Catches UnicodeDecodeError for latin-1 or other IOErrors
                # print(f"Warning: Could not decode file {file_path} with UTF-8 or latin-1. Error: {e_fallback}. Skipping.")
                return None
        except IOError as e:
            # print(f"Warning: IOError when reading file {file_path}: {e}. Skipping.") # Consider logging
            return None
        except Exception as e:
            # Catch-all for other unexpected errors during file reading
            # print(f"Warning: Unexpected error when reading file {file_path}: {e}. Skipping.")
            return None

    def _search_in_content(self, content, file_path):
        """
        Searches for the query within the given string content.

        Args:
            content (str): The text content to search within.
            file_path (str): The path of the file (for context/logging, not used in core logic yet).

        Returns:
            list: A list of match information (e.g., dicts with line_number, match_text, char_start, char_end).
                  char_start and char_end are 0-based character offsets within the entire content.
        """
        matches = []
        if not content: # Ensure content is not None or empty
            return matches

        # Pre-calculate line start indices for quick line number lookup
        line_starts = [0] + [i + 1 for i, char in enumerate(content) if char == '\n']
        
        def get_line_number_and_offset(char_offset):
            line_num = 0
            for i, start_idx in enumerate(line_starts):
                if char_offset >= start_idx:
                    line_num = i + 1 # 1-based line number
                else:
                    break
            # Character offset within the found line
            offset_in_line = char_offset - line_starts[line_num -1]
            return line_num, offset_in_line

        if self.is_regex:
            if self.compiled_regex:
                for match_obj in self.compiled_regex.finditer(content):
                    char_start, char_end = match_obj.span()
                    match_text = match_obj.group(0)
                    line_number, _ = get_line_number_and_offset(char_start)
                    matches.append({
                        'line_number': line_number,
                        'match_text': match_text,
                        'char_start': char_start, # Offset in entire content
                        'char_end': char_end      # Offset in entire content
                    })
        else: # Plain string search
            search_query = self.query
            haystack = content
            if not self.is_case_sensitive:
                search_query = search_query.lower()
                haystack = haystack.lower()
            
            current_pos = 0
            # match_num_debug = 0 # DEBUG
            # print(f"DEBUG: Plain search for '{search_query}' in haystack (first 60 chars): {haystack[:60].replace('\n', '\\n')}") # DEBUG
            while current_pos < len(haystack):
                # print(f"DEBUG: Match Loop: {match_num_debug}, current_pos: {current_pos}") # DEBUG
                found_pos = haystack.find(search_query, current_pos)
                # print(f"DEBUG: search_query='{search_query}', haystack[current_pos:current_pos+30]='{haystack[current_pos:current_pos+30].replace('\n','\\n')}...', found_pos (raw from find): {found_pos}") # DEBUG

                if found_pos == -1:
                    # print(f"DEBUG: found_pos is -1, breaking.") # DEBUG
                    break
                
                char_start = found_pos
                char_end = found_pos + len(search_query)
                # print(f"DEBUG: char_start={char_start}, char_end={char_end}") # DEBUG
                
                original_match_text = content[char_start:char_end]
                line_number, _ = get_line_number_and_offset(char_start)

                matches.append({
                    'line_number': line_number,
                    'match_text': original_match_text,
                    'char_start': char_start,
                    'char_end': char_end
                })
                current_pos = char_end
                # match_num_debug += 1 # DEBUG
        
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
            prefix = f"{line_number: >4}: "

            if i == match_line_idx:
                # Highlight the match: before_match + INDICATOR + match_text + INDICATOR + after_match
                # For now, simple indication. Could use ANSI codes for terminal, or markdown for other outputs.
                # Using simple `>>>` and `<<<` as indicators.
                # Ensure match_start/end are within the line_content bounds
                actual_match_start = min(match_start_char_in_line, len(line_content))
                actual_match_end = min(match_end_char_in_line, len(line_content))

                before_match = line_content[:actual_match_start]
                match_text = line_content[actual_match_start:actual_match_end]
                after_match = line_content[actual_match_end:]

                # Ensure there are spaces around the highlight markers and handle spaces from BM/AM
                snippet_lines.append(f"{prefix}{before_match.rstrip()} >>> {match_text} <<< {after_match.lstrip()}")
            else:
                snippet_lines.append(f"{prefix} {line_content}")
        
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