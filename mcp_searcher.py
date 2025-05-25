#!/usr/bin/env python3

import argparse
import os
import sys
import re # For Searcher's regex compilation and potential re.error
import json # For output_generator

# Assuming file_scanner.py and mcp_search.py are in the same directory or PYTHONPATH
from file_scanner import FileScanner #, DEFAULT_EXCLUDED_DIRS, DEFAULT_EXCLUDED_FILES # Might need these if modifying defaults
from mcp_search import Searcher
from output_generator import OutputGenerator # Added for Task 7.5

# Conditionally import ContextAnalyzer if elaboration is a feature we want to control
# For now, assume it's always available if the module exists.
try:
    from mcp_elaborate import ContextAnalyzer
    ELABORATE_AVAILABLE = True
except ImportError:
    ContextAnalyzer = None
    ELABORATE_AVAILABLE = False
    # print("Warning: mcp_elaborate or config module not found. Elaboration feature disabled.", file=sys.stderr)

def parse_arguments():
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

    # Output formatting arguments (Task 7.5)
    parser.add_argument(
        "--output-format",
        choices=['console', 'json', 'md'],
        default='console',
        help="Format for the output (default: console)."
    )
    parser.add_argument(
        "--output-file",
        type=str,
        metavar="FILE",
        help="Optional: File to write the output to. If not specified, output goes to stdout."
    )

    # Placeholder for future LLM elaboration
    if ELABORATE_AVAILABLE:
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

    if args.context < 0:
        parser.error("Number of context lines cannot be negative.")
        
    return args

def main():
    args = parse_arguments()

    # This is the main try block that should encapsulate most of the program logic
    try:
        scanner_excluded_dirs = [p.strip() for p in args.exclude_dirs.split(',') if p.strip()] if args.exclude_dirs else None
        scanner_excluded_files = [p.strip() for p in args.exclude_files.split(',') if p.strip()] if args.exclude_files else None

        try:
            scanner = FileScanner(
                excluded_dirs=scanner_excluded_dirs,
                excluded_files=scanner_excluded_files,
                exclude_dot_items=(not args.include_hidden)
            )
        except Exception as e:
            print(f"Error initializing FileScanner: {type(e).__name__} - {e}", file=sys.stderr)
            sys.exit(1)

        all_files_to_scan = []
        direct_files_provided = []

        for p_item in args.paths:
            abs_path_item = os.path.abspath(os.path.expanduser(p_item))
            if not os.path.exists(abs_path_item):
                print(f"Warning: Path '{p_item}' does not exist. Skipping.", file=sys.stderr)
                continue
            
            if os.path.isfile(abs_path_item):
                is_excluded_direct_file = scanner._is_excluded(
                    abs_path_item, 
                    scan_root_path=os.path.dirname(abs_path_item), 
                    is_dir=False
                )
                is_binary_direct_file = scanner._is_binary(abs_path_item)

                if not is_excluded_direct_file and not is_binary_direct_file:
                    direct_files_provided.append(abs_path_item)
                elif is_excluded_direct_file:
                    print(f"Info: Directly specified file '{p_item}' is excluded by patterns. Skipping.", file=sys.stderr)
                elif is_binary_direct_file:
                    print(f"Info: Directly specified file '{p_item}' appears to be binary. Skipping.", file=sys.stderr)

            elif os.path.isdir(abs_path_item):
                scanned_from_dir = scanner.scan_directory(abs_path_item)
                all_files_to_scan.extend(scanned_from_dir)
            else:
                print(f"Warning: Path '{p_item}' is neither a file nor a directory. Skipping.", file=sys.stderr)

        all_files_to_scan.extend(direct_files_provided)
        if not all_files_to_scan:
            print("No files found to scan based on the provided paths and exclusions. Ensure paths are correct and not fully excluded.", file=sys.stderr)
            sys.exit(0) # Successful exit, but no work to do.
        
        unique_files_to_scan = sorted(list(set(all_files_to_scan)))

        try:
            searcher = Searcher(
                query=args.query,
                is_case_sensitive=args.case_sensitive,
                is_regex=args.regex,
                context_lines=args.context
            )
        except ValueError as e: # Catches re.error for invalid regex patterns
            print(f"Error initializing Searcher: Invalid regular expression: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error initializing Searcher: {type(e).__name__} - {e}", file=sys.stderr)
            sys.exit(1)

        processed_results = []
        elaborator = None

        # Setup elaborator if requested and available
        user_wants_to_elaborate = hasattr(args, 'elaborate') and args.elaborate

        if user_wants_to_elaborate:
            if ELABORATE_AVAILABLE:
                try:
                    elaborator = ContextAnalyzer() # API key is loaded within ContextAnalyzer
                    if not elaborator.api_key:
                        print("Warning: Elaboration disabled. GOOGLE_API_KEY not found or not loaded.", file=sys.stderr)
                        elaborator = None 
                    elif not elaborator.model:
                        print("Warning: Elaboration disabled. Gemini model could not be initialized.", file=sys.stderr)
                        elaborator = None
                except Exception as e:
                    print(f"Error initializing ContextAnalyzer for elaboration: {type(e).__name__} - {e}. Elaboration will be disabled.", file=sys.stderr)
                    elaborator = None
            else: # User wants to elaborate, but feature isn't available
                print("Warning: Elaboration requested (-e) but feature is unavailable (e.g., mcp_elaborate.py missing or import error). Elaboration disabled.", file=sys.stderr)

        for file_path in unique_files_to_scan:
            try:
                matches = searcher.search_files([file_path])
                for match_info in matches:
                    processed_match = {
                        'file_path': match_info['file_path'],
                        'line_number': match_info['line_number'],
                        'match_text': match_info['match_text'],
                        'snippet': match_info['snippet'],
                        'elaboration': None
                    }

                    if elaborator:
                        if args.output_format == 'console':
                            print(f"✨ Elaborating on match in {match_info['file_path']}:{match_info['line_number']}...", end='\r', file=sys.stderr)
                        
                        full_content_for_llm = None
                        try:
                            with open(match_info['file_path'], 'r', encoding='utf-8') as f_llm:
                                full_content_for_llm = f_llm.read()
                        except Exception: # pylint: disable=broad-except
                            if args.output_format == 'console':
                                print(f"Warning: Could not read full file {match_info['file_path']} for deep elaboration context.", file=sys.stderr)
                                sys.stderr.flush()

                        elaboration_text = elaborator.elaborate_on_match(
                            file_path=match_info['file_path'],
                            line_number=match_info['line_number'],
                            snippet=match_info['snippet'],
                            full_file_content=full_content_for_llm
                        )
                        processed_match['elaboration'] = elaboration_text
                        if args.output_format == 'console':
                            print(" " * 80, end='\r', file=sys.stderr)
                            sys.stderr.flush()
                    processed_results.append(processed_match)
            except Exception as e:
                # Error during search/elaboration for a specific file
                print(f"Error processing file {file_path}: {type(e).__name__} - {e}. Skipping this file.", file=sys.stderr)
                continue 

        output_gen = OutputGenerator(output_format=args.output_format)
        formatted_output_str = output_gen.generate_output(processed_results)

        if args.output_file:
            try:
                with open(args.output_file, 'w', encoding='utf-8') as f_out:
                    f_out.write(formatted_output_str)
                # If successfully written to file, print a confirmation to stderr
                print(f"Output successfully written to {args.output_file}", file=sys.stderr)
            except IOError as e:
                print(f"Error writing to output file {args.output_file}: {e}", file=sys.stderr)
                print("Falling back to console output:\n", file=sys.stderr)
                print(formatted_output_str)
        else:
            print(formatted_output_str)

    except Exception as e:
        print(f"An unexpected error occurred: {type(e).__name__} - {e}", file=sys.stderr)
        # In a debug mode, we might print the full traceback
        # import traceback
        # traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 