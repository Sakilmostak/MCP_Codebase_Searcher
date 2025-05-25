#!/usr/bin/env python3

import argparse
import os
import sys

# Assuming file_scanner.py and mcp_search.py are in the same directory or PYTHONPATH
from file_scanner import FileScanner #, DEFAULT_EXCLUDED_DIRS, DEFAULT_EXCLUDED_FILES # Might need these if modifying defaults
from mcp_search import Searcher

# Attempt to import ContextAnalyzer and config for elaboration feature
try:
    from mcp_elaborate import ContextAnalyzer
    import config as app_config # Renamed to avoid conflict if user has a module named 'config'
    elaboration_possible = True
except ImportError:
    ContextAnalyzer = None
    app_config = None
    elaboration_possible = False
    # print("Warning: mcp_elaborate or config module not found. Elaboration feature disabled.", file=sys.stderr)

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
        help="Number of context lines to show around each match (default: 3)."
    )

    # Optional file/directory filtering arguments
    parser.add_argument(
        "--exclude-dirs", 
        type=str, 
        metavar="PATTERNS",
        help="Comma-separated list of directory name patterns to exclude (e.g., .git,node_modules). Wildcards supported."
    )
    parser.add_argument(
        "--exclude-files", 
        type=str, 
        metavar="PATTERNS",
        help="Comma-separated list of file name patterns to exclude (e.g., *.log,*.tmp). Wildcards supported."
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden files and directories (starting with '.') in the scan."
    )

    # Placeholder for future LLM elaboration
    if elaboration_possible:
        parser.add_argument(
            "-e", "--elaborate",
            action="store_true",
            help="Elaborate on each match using a generative AI model (requires GOOGLE_API_KEY)."
        )
    else:
        # Provide a dummy argument if elaboration is not possible, so help text still mentions it if user expects it.
        # Or simply omit it. For now, let's make it clear it's unavailable if modules are missing.
        pass # Not adding -e if imports failed

    args = parser.parse_args()

    custom_excluded_dirs = [p.strip() for p in args.exclude_dirs.split(',') if p.strip()] if args.exclude_dirs else []
    custom_excluded_files = [p.strip() for p in args.exclude_files.split(',') if p.strip()] if args.exclude_files else []

    try:
        scanner = FileScanner(
            excluded_dirs=custom_excluded_dirs,
            excluded_files=custom_excluded_files,
            exclude_dot_items=(not args.include_hidden)
        )
    except Exception as e:
        print(f"Error initializing FileScanner: {e}", file=sys.stderr)
        sys.exit(1)

    all_files_to_search = []
    valid_initial_paths = []

    for path_arg in args.paths:
        abs_path_arg = os.path.abspath(path_arg)
        if not os.path.exists(abs_path_arg):
            print(f"Warning: Path does not exist: {abs_path_arg}. Skipping.", file=sys.stderr)
            continue
        
        valid_initial_paths.append(abs_path_arg)
        if os.path.isfile(abs_path_arg):
            # For direct file paths, scan_root_path is its own directory
            scan_root_for_file = os.path.dirname(abs_path_arg)
            if not scanner._is_excluded(abs_path_arg, scan_root_path=scan_root_for_file, is_dir=False) and \
               not scanner._is_binary(abs_path_arg):
                 all_files_to_search.append(abs_path_arg)
            elif scanner._is_excluded(abs_path_arg, scan_root_path=scan_root_for_file, is_dir=False):
                print(f"Info: Direct file path {abs_path_arg} is excluded by FileScanner rules. Skipping.", file=sys.stderr)
            # No specific message for binary if explicitly provided, _is_binary check is mostly for directory scan
        elif os.path.isdir(abs_path_arg):
            all_files_to_search.extend(scanner.scan_directory(abs_path_arg))
        else:
            print(f"Warning: Path is not a valid file or directory: {abs_path_arg}. Skipping.", file=sys.stderr)
    
    all_files_to_search = sorted(list(set(all_files_to_search)))

    if not valid_initial_paths:
        print("Error: No valid search paths provided after checking existence.", file=sys.stderr)
        sys.exit(1)
        
    if not all_files_to_search:
        print("No files found to search after applying exclusions and checking paths.")
        sys.exit(0)

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

    results_found_count = 0
    context_analyzer = None

    # Initialize ContextAnalyzer once if elaboration is enabled
    if elaboration_possible and hasattr(args, 'elaborate') and args.elaborate: # Check if args.elaborate exists
        api_key = None
        try:
            if app_config: 
                api_key = app_config.load_api_key()
            if not api_key: 
                api_key = os.getenv('GOOGLE_API_KEY')
            
            if not api_key:
                print("Warning: GOOGLE_API_KEY not found. AI Elaboration will be disabled.", file=sys.stderr)
            else:
                context_analyzer = ContextAnalyzer(api_key=api_key)
                if not context_analyzer.model:
                    print("Warning: Failed to initialize ContextAnalyzer model. Elaboration disabled.", file=sys.stderr)
                    context_analyzer = None 
        except Exception as e:
            print(f"Warning: Error setting up ContextAnalyzer: {e}. Elaboration disabled.", file=sys.stderr)
            context_analyzer = None

    # Main processing loop
    for file_path in all_files_to_search:
        # Searcher.search_files expects a list of files, so pass a list containing the single file_path
        matches_in_file = searcher.search_files([file_path]) 
        
        if matches_in_file:
            for match in matches_in_file:
                results_found_count += 1
                print(f"\nMatch in: {match['file_path']}")
                print(f"Line {match['line_number']}:")
                print(f"{match['snippet']}")

                if context_analyzer:
                    print("\n    ✨ Elaborating...\n")
                    full_content_for_elaboration = None
                    try:
                        # Ensure we use the correct file path from the match dictionary
                        with open(match['file_path'], 'r', encoding='utf-8', errors='replace') as f_content:
                            full_content_for_elaboration = f_content.read()
                    except Exception as e_read:
                        print(f"    Warning: Could not read full file {match['file_path']} for elaboration context: {e_read}", file=sys.stderr)
                    
                    try:
                        elaboration = context_analyzer.elaborate_on_match(
                            file_path=match['file_path'],
                            line_number=match['line_number'],
                            snippet=match['snippet'],
                            full_file_content=full_content_for_elaboration
                        )
                        elaboration_lines = elaboration.split('\n')
                        for el_line in elaboration_lines:
                            print(f"    💡 {el_line}")
                    except Exception as e_elab:
                        print(f"    Error during elaboration: {e_elab}", file=sys.stderr)
                        print(f"    💡 Elaboration failed.")
                    print("    --------------------") # Print separator after each elaboration

    # Final summary
    if results_found_count == 0:
        print("No matches found.")
    else:
        print(f"\nFound {results_found_count} match(es) in total.")

if __name__ == "__main__":
    main() 