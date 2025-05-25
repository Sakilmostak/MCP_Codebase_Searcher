#!/usr/bin/env python3

import argparse
import os
import sys

# Assuming file_scanner.py and mcp_search.py are in the same directory or PYTHONPATH
from file_scanner import FileScanner #, DEFAULT_EXCLUDED_DIRS, DEFAULT_EXCLUDED_FILES # Might need these if modifying defaults
from mcp_search import Searcher

def main():
    parser = argparse.ArgumentParser(
        description="Search for code patterns in a specified set of files or directories.",
        formatter_class=argparse.RawTextHelpFormatter # To allow for better help text formatting
    )

    # Positional arguments
    parser.add_argument("query", help="The search term or regex pattern.")
    parser.add_argument("paths", nargs='+', help="One or more file or directory paths to search within.")

    # Optional search behavior arguments
    parser.add_argument(
        "-r", "--regex", 
        action="store_true", 
        help="Treat the query as a regular expression."
    )
    parser.add_argument(
        "-c", "--case-sensitive", 
        action="store_true", 
        help="Perform a case-sensitive search. Default is case-insensitive."
    )
    parser.add_argument(
        "-C", "--context", 
        type=int, 
        default=3, 
        metavar="LINES",
        help="Number of lines of context to show before and after a match (default: 3)."
    )

    # Optional file/directory filtering arguments
    parser.add_argument(
        "--exclude-dirs", 
        type=str, 
        default="",
        metavar="DIRS_STR",
        help=("Comma-separated list of directory names/patterns to exclude (e.g., \".git,build/*\"). "
              "These are passed to FileScanner's `excluded_dirs` parameter.")
    )
    parser.add_argument(
        "--exclude-files", 
        type=str, 
        default="", 
        metavar="FILES_STR",
        help=("Comma-separated list of file name patterns to exclude (e.g., \"*.log,temp.*\"). "
              "These are passed to FileScanner's `excluded_files` parameter.")
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden files and directories (those starting with '.'). "
             "Sets FileScanner's `exclude_dot_items` to False."
    )

    # Placeholder for future LLM elaboration
    parser.add_argument(
        "-e", "--elaborate",
        action="store_true",
        help="(Future Feature) Elaborate on search results using an LLM."
    )

    args = parser.parse_args()

    cli_excluded_dirs = [d.strip() for d in args.exclude_dirs.split(',') if d.strip()] if args.exclude_dirs else None
    cli_excluded_files = [f.strip() for f in args.exclude_files.split(',') if f.strip()] if args.exclude_files else None

    try:
        file_scanner = FileScanner(
            excluded_dirs=cli_excluded_dirs, 
            excluded_files=cli_excluded_files,
            exclude_dot_items=(not args.include_hidden) # Pass the inverse of include_hidden
        )
    except Exception as e:
        print(f"Error initializing FileScanner: {e}", file=sys.stderr)
        sys.exit(1)

    # Collect target files
    files_to_search = set() # Use a set to automatically handle duplicates
    has_valid_search_path = False
    for path_arg in args.paths:
        abs_path_arg = os.path.abspath(os.path.expanduser(path_arg))
        if not os.path.exists(abs_path_arg):
            print(f"Warning: Path does not exist: {abs_path_arg}. Skipping.", file=sys.stderr)
            continue
        
        has_valid_search_path = True # At least one path is valid
        if os.path.isdir(abs_path_arg):
            scanned_files = file_scanner.scan_directory(abs_path_arg)
            files_to_search.update(scanned_files)
        elif os.path.isfile(abs_path_arg):
            parent_dir_of_file = os.path.dirname(abs_path_arg)
            if not file_scanner._is_excluded(abs_path_arg, parent_dir_of_file, is_dir=False):
                 files_to_search.add(abs_path_arg)
            else:
                # Check if it was excluded *only* because it's a dotfile and we are *not* including hidden items.
                # This is a bit complex because _is_excluded now has multiple reasons to exclude.
                # For now, the generic message is okay.
                print(f"Info: Direct file path {abs_path_arg} is excluded by FileScanner rules. Skipping.", file=sys.stderr)
        else:
            print(f"Warning: Path is not a valid file or directory: {abs_path_arg}. Skipping.", file=sys.stderr)

    if not has_valid_search_path:
        print("Error: No valid search paths provided or all provided paths were invalid.", file=sys.stderr)
        sys.exit(1)
        
    if not files_to_search:
        print("No files found to search after scanning and filtering from valid paths.", file=sys.stderr)
        sys.exit(0)

    # Initialize Searcher
    try:
        searcher = Searcher(
            query=args.query,
            is_case_sensitive=args.case_sensitive,
            is_regex=args.regex,
            context_lines=args.context
        )
    except ValueError as e:
        print(f"Error initializing Searcher: {e}", file=sys.stderr)
        sys.exit(1)

    # Perform search
    results = searcher.search_files(list(files_to_search))

    # Display results (basic)
    if results:
        print(f"\nFound {len(results)} match(es) in {len(set(r['file_path'] for r in results))} file(s):\n")
        for res in results:
            print(f"File: {res['file_path']}")
            print(f"Line: {res['line_number']}, Match: '{res['match_text']}'")
            print(f"Snippet:\n{res['snippet']}")
            print("--------------------------------------------------")
    else:
        print("No matches found.")

    if args.elaborate:
        print("\n(Placeholder: LLM elaboration would happen here if results were found.)")

if __name__ == "__main__":
    main() 