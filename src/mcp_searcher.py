#!/usr/bin/env python3

import argparse
import os
import sys
import re # For Searcher's regex compilation and potential re.error
import json # For output_generator

# Direct absolute imports, as these modules are installed at the top level
try:
    from file_scanner import FileScanner
    from mcp_search import Searcher
    from output_generator import OutputGenerator
    from report_elaborator import elaborate_finding
    from mcp_elaborate import ContextAnalyzer
    ELABORATE_AVAILABLE = True
except ImportError as e:
    print(f"Critical Error: Failed to import necessary modules. This typically means the package is not installed correctly or there's an issue with PYTHONPATH. Please ensure 'mcp-codebase-searcher' is installed. Error: {e}", file=sys.stderr)
    sys.exit(1)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="MCP Codebase Searcher: Searches codebases and elaborates on findings.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands', required=True)

    # --- Search command ---
    search_parser = subparsers.add_parser('search', help='Search for a query in specified paths.')
    search_parser.add_argument("query", help="The search term or regex pattern.")
    search_parser.add_argument("paths", nargs='+', help="One or more file or directory paths to search within.")
    search_parser.add_argument(
        "-r", "--regex", 
        action="store_true", 
        help="Treat the query as a regular expression."
    )
    search_parser.add_argument(
        "-c", "--case-sensitive", 
        action="store_true", 
        help="Perform a case-sensitive search. Default is case-insensitive."
    )
    search_parser.add_argument(
        "-C", "--context", 
        type=int, 
        default=3, 
        metavar="LINES",
        help="Number of context lines to show around each match (default: 3)."
    )
    search_parser.add_argument(
        "--exclude-dirs", 
        type=str, 
        metavar="PATTERNS",
        help="Comma-separated list of directory name patterns to exclude (e.g., .git,node_modules). Wildcards supported."
    )
    search_parser.add_argument(
        "--exclude-files", 
        type=str, 
        metavar="PATTERNS",
        help="Comma-separated list of file name patterns to exclude (e.g., *.log,*.tmp). Wildcards supported."
    )
    search_parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden files and directories (starting with '.') in the scan."
    )
    search_parser.add_argument(
        "--output-format",
        choices=['console', 'json', 'md', 'markdown'],
        default='console',
        help="Format for the output (default: console)."
    )
    search_parser.add_argument(
        "--output-file",
        type=str,
        metavar="FILE",
        help="Path to save the output. If not provided, prints to console."
    )

    # --- Elaborate command ---
    elaborate_parser = subparsers.add_parser('elaborate', help='Elaborate on a specific finding from a JSON report.')
    elaborate_parser.add_argument('--report-file', required=True, help="Path to the JSON search report file.")
    elaborate_parser.add_argument('--finding-id', required=True, type=str, help="The 0-based index (ID) of the finding in the report to elaborate on.")
    elaborate_parser.add_argument('--api-key', type=str, default=None, help="Optional Google API key. If not provided, it will be sourced from --config-file, config.py, or environment.")
    elaborate_parser.add_argument('--config-file', type=str, default=None, help="Optional path to a JSON configuration file containing GOOGLE_API_KEY.")
    elaborate_parser.add_argument('--context-lines', type=int, default=10, help="Number of lines of broader context from the source file to provide to the LLM (default: 10).")

    args = parser.parse_args()
    return args

def main():
    args = parse_arguments()

    if args.command == 'search':
        if args.context < 0:
            print("Error: Number of context lines cannot be negative.", file=sys.stderr)
            sys.exit(1)

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
                    if not scanner._is_excluded(abs_path_item, os.path.dirname(abs_path_item), False) and not scanner._is_binary(abs_path_item):
                        direct_files_provided.append(abs_path_item)
                elif os.path.isdir(abs_path_item):
                    scanned_from_dir = scanner.scan_directory(abs_path_item)
                    all_files_to_scan.extend(scanned_from_dir)

            all_files_to_scan.extend(direct_files_provided)
            if not all_files_to_scan:
                print("No files found to scan based on the provided paths and exclusions. Ensure paths are correct and not fully excluded.", file=sys.stderr)
                sys.exit(0)
            
            unique_files_to_scan = sorted(list(set(all_files_to_scan)))

            try:
                searcher = Searcher(
                    query=args.query,
                    is_case_sensitive=args.case_sensitive,
                    is_regex=args.regex,
                    context_lines=args.context
                )
            except ValueError as e: 
                print(f"Error initializing Searcher: Invalid regular expression: {e}", file=sys.stderr)
                sys.exit(1)
            except Exception as e:
                print(f"Error initializing Searcher: {type(e).__name__} - {e}", file=sys.stderr)
                sys.exit(1)

            results = []
            for file_path in unique_files_to_scan:
                try:
                    matches_in_file = searcher.search_files([file_path])
                    results.extend(matches_in_file)
                except Exception as e:
                    print(f"Error searching file {file_path}: {type(e).__name__} - {e}", file=sys.stderr)
            
            if not results:
                print("No matches found for your query.")
                sys.exit(0)

            output_gen = OutputGenerator(output_format=args.output_format)
            formatted_output = output_gen.generate_output(results)

            if args.output_file:
                try:
                    with open(args.output_file, 'w', encoding='utf-8') as f:
                        f.write(formatted_output)
                    print(f"Output successfully saved to {args.output_file}")
                except IOError as e:
                    print(f"Error: Could not write to output file '{args.output_file}': {e}", file=sys.stderr)
                    if args.output_format == 'console':
                        print("\n--- Outputting to Console as Fallback ---")
                        print(formatted_output)
                    else:
                        print(formatted_output)
                    sys.exit(1)
            else:
                print(formatted_output)

        except Exception as e:
            print(f"An unexpected error occurred during search: {type(e).__name__} - {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == 'elaborate':
        api_key_to_use = args.api_key
        
        if not api_key_to_use and args.config_file:
            try:
                with open(args.config_file, 'r', encoding='utf-8') as f_cfg:
                    config_data = json.load(f_cfg)
                    api_key_to_use = config_data.get('GOOGLE_API_KEY')
                if not api_key_to_use:
                    print(f"Info: GOOGLE_API_KEY not found in config file '{args.config_file}'. Relying on other methods (env var, config.py).", file=sys.stderr)
            except FileNotFoundError:
                print(f"Warning: Config file '{args.config_file}' not found. Relying on other methods for API key.", file=sys.stderr)
            except json.JSONDecodeError:
                print(f"Warning: Could not decode JSON from config file '{args.config_file}'. Relying on other methods for API key.", file=sys.stderr)
            except Exception as e:
                print(f"Warning: Error reading config file '{args.config_file}': {e}. Relying on other methods for API key.", file=sys.stderr)

        try:
            elaboration_result = elaborate_finding(
                report_path=args.report_file,
                finding_id=args.finding_id,
                api_key=api_key_to_use,
                context_window_lines=args.context_lines
            )
            print(elaboration_result)
            if elaboration_result.startswith("Error:"):
                sys.exit(1)
        except Exception as e:
            print(f"An unexpected error occurred during elaboration: {type(e).__name__} - {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main() 