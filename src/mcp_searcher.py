#!/usr/bin/env python3

import argparse
import os
import sys
import re # For Searcher's regex compilation and potential re.error
import json # For output_generator
from dotenv import load_dotenv # Added for explicit .env loading
import logging # Added import
from datetime import datetime

# Direct absolute imports, as these modules are installed at the top level
try:
    from file_scanner import FileScanner
    from mcp_search import Searcher
    from output_generator import OutputGenerator
    from report_elaborator import elaborate_finding
    from mcp_elaborate import ContextAnalyzer
    from cache_manager import CacheManager # Corrected import
    ELABORATE_AVAILABLE = True
except ImportError as e:
    print(f"Critical Error: Failed to import necessary modules. This typically means the package is not installed correctly or there's an issue with PYTHONPATH. Please ensure 'mcp-codebase-searcher' is installed. Error: {e}", file=sys.stderr)
    sys.exit(1)

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="MCP Codebase Searcher: Searches codebases and elaborates on findings.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    # --- Global Caching Arguments ---
    cache_group = parser.add_argument_group('Caching Options')
    cache_group.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable caching for this run."
    )
    cache_group.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear all cached data before proceeding."
    )
    cache_group.add_argument(
        "--cache-dir",
        type=str,
        default=os.path.expanduser("~/.cache/mcp_codebase_searcher"),
        metavar="DIRECTORY",
        help="Directory to store cache files (default: ~/.cache/mcp_codebase_searcher)."
    )
    cache_group.add_argument(
        "--cache-expiry",
        type=int,
        default=7,
        metavar="DAYS",
        help="Default cache expiry in days (default: 7)."
    )
    cache_group.add_argument(
        "--cache-size-limit",
        type=int,
        default=100, # Defaulting to 100MB as per plan
        metavar="MB",
        help="Cache size limit in Megabytes (default: 100)."
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
    elaborate_parser.add_argument('--api-key', type=str, default=None, help="Optional API key (e.g. for OpenAI). If not provided, it will be sourced from --config-file, config.py, or environment (e.g. OPENAI_API_KEY).")
    elaborate_parser.add_argument('--config-file', type=str, default=None, help="Optional path to a JSON configuration file containing API keys.")
    elaborate_parser.add_argument('--model-name', type=str, default='gemini/gemini-1.5-flash-latest', help="The name of the Litellm model to use (default: gemini/gemini-1.5-flash-latest).")
    elaborate_parser.add_argument('--api-base', type=str, default=None, help="Optional custom API base URL (e.g. for local Ollama endpoints).")
    elaborate_parser.add_argument('--context-lines', type=int, default=10, help="Number of lines of broader context from the source file to provide to the LLM (default: 10).")
    elaborate_parser.add_argument(
        "--output-format",
        choices=['console', 'json', 'md', 'markdown'],
        default='console',
        help="Format for the elaboration output (default: console)."
    )
    elaborate_parser.add_argument(
        "--output-file",
        type=str,
        metavar="FILE",
        help="Path to save the elaboration output. If not provided, prints to console."
    )

    args = parser.parse_args()
    return args

def main():
    """Main function to parse arguments and orchestrate the search or elaboration."""
    # Basic logging configuration
    logging.basicConfig(level=logging.INFO, 
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')

    args = parse_arguments()
    
    cache_manager = None # Initialize to None
    try:
        expiry_seconds = args.cache_expiry * 24 * 60 * 60 if args.cache_expiry is not None else None
        
        # Instantiate CacheManager
        cache_manager = CacheManager(
            cache_dir=args.cache_dir,
            expiry_seconds=expiry_seconds,
            cache_size_limit_mb=args.cache_size_limit
        )

        if args.clear_cache:
            if cache_manager:
                print(f"Clearing cache at {cache_manager.cache_dir}...")
                cleared_count = cache_manager.clear_all()
                print(f"Successfully cleared {cleared_count} items from the cache.")
            else: # Should not happen if instantiation is successful
                print("Error: CacheManager not available for clearing cache.", file=sys.stderr)
            sys.exit(0)

        # --- Subcommand logic ---
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
                    sys.exit(0) # Exit cleanly if no files
                
                unique_files_to_scan = sorted(list(set(all_files_to_scan)))

                try:
                    # Pass cache_manager and no_cache to Searcher (Task 7 will handle internal usage)
                    searcher = Searcher(
                        query=args.query,
                        is_case_sensitive=args.case_sensitive,
                        is_regex=args.regex,
                        context_lines=args.context,
                        cache_manager=cache_manager,
                        no_cache=args.no_cache
                    )
                except ValueError as e: 
                    print(f"Error initializing Searcher: Invalid regular expression: {e}", file=sys.stderr)
                    sys.exit(1)
                except Exception as e:
                    print(f"Error initializing Searcher: {type(e).__name__} - {e}", file=sys.stderr)
                    sys.exit(1)

                results = []
                # Search logic will be modified in Task 7 to use cache_manager and args.no_cache
                for file_path in unique_files_to_scan:
                    try:
                        # This call will eventually use caching
                        matches_in_file = searcher.search_files([file_path]) 
                        results.extend(matches_in_file)
                    except Exception as e:
                        print(f"Error searching file {file_path}: {type(e).__name__} - {e}", file=sys.stderr)
                
                output_gen = OutputGenerator(output_format=args.output_format)
                formatted_output = output_gen.generate_output(results)

                if args.output_file:
                    try:
                        with open(args.output_file, 'w', encoding='utf-8') as f:
                            f.write(formatted_output)
                        print(f"Output successfully saved to {args.output_file}")
                        if not results:
                            if args.output_format == 'json':
                                print("(The file contains an empty JSON array `[]` as no matches were found.)")
                            else:
                                print("(The file indicates no matches were found.)")
                    except IOError as e:
                        print(f"Error: Could not write to output file '{args.output_file}': {e}", file=sys.stderr)
                        if args.output_format != 'console':
                            print("\n--- Outputting to Console as Fallback ---")
                        print(formatted_output) # Print to console if file write fails
                        sys.exit(1)
                else:
                    print(formatted_output)

                sys.exit(0) # Success for search command

            except Exception as e: # Catch-all for search command unexpected errors
                print(f"An unexpected error occurred during search: {type(e).__name__} - {e}", file=sys.stderr)
                sys.exit(1)

        elif args.command == 'elaborate':
            if not ELABORATE_AVAILABLE:
                print("Elaborate command is unavailable due to missing dependencies (e.g., google.generativeai).", file=sys.stderr)
                sys.exit(1)

            # --- API key sourcing logic (Restored and maintained) ---
            api_key_to_use = args.api_key
            source_of_key = "command line --api-key argument" if api_key_to_use else None

            model_name_to_use = args.model_name
            api_base_to_use = args.api_base

            if args.config_file:
                try:
                    with open(args.config_file, 'r', encoding='utf-8') as f_cfg:
                        config_data = json.load(f_cfg)
                        
                        if not api_key_to_use:
                            api_key_from_config_file = config_data.get('api_key') or config_data.get('API_KEY') or config_data.get('GOOGLE_API_KEY') or config_data.get('OPENAI_API_KEY')
                            if api_key_from_config_file:
                                api_key_to_use = api_key_from_config_file
                                source_of_key = f"config file ('{args.config_file}')"

                        if args.model_name == 'gemini/gemini-1.5-flash-latest':
                            config_model = config_data.get('model_name') or config_data.get('MODEL_NAME')
                            if config_model:
                                model_name_to_use = config_model
                        
                        if not api_base_to_use:
                            config_api_base = config_data.get('api_base') or config_data.get('API_BASE')
                            if config_api_base:
                                api_base_to_use = config_api_base
                except FileNotFoundError:
                    logging.warning(f"Config file '{args.config_file}' not found.")
                except json.JSONDecodeError:
                    logging.warning(f"Could not decode JSON from config file '{args.config_file}'.")
                except Exception as e_cfg_load:
                    logging.warning(f"Error reading config file '{args.config_file}': {e_cfg_load}.")
            
            if not api_key_to_use:
                # Load .env from current working directory to check for GOOGLE_API_KEY
                # This explicitly loads .env here, overriding any system env var if key is present in .env
                # ContextAnalyzer's internal config loading might also call load_dotenv,
                # but this ensures CLI-level .env takes precedence if no direct arg or config file key.
                original_env_key_value = os.getenv('GOOGLE_API_KEY') # For logging/comparison if needed
                dotenv_path = os.path.join(os.getcwd(), '.env')
                dotenv_loaded = load_dotenv(dotenv_path=dotenv_path, override=True) # Override existing env vars
                
                key_from_dotenv_cwd = os.getenv('GOOGLE_API_KEY') or os.getenv('OPENAI_API_KEY') or os.getenv('API_KEY')
                
                if args.model_name == 'gemini/gemini-1.5-flash-latest':
                    env_model = os.getenv('LITELLM_MODEL_NAME') or os.getenv('MODEL_NAME')
                    if env_model:
                        model_name_to_use = env_model
                        
                if not api_base_to_use:
                    env_api_base = os.getenv('LITELLM_API_BASE') or os.getenv('API_BASE')
                    if env_api_base:
                        api_base_to_use = env_api_base

                if key_from_dotenv_cwd: # If key is now in os.environ after load_dotenv
                    api_key_to_use = key_from_dotenv_cwd
                    if dotenv_loaded: # Indicates that the .env file was found and loaded
                        source_of_key = f".env file in CWD ('{dotenv_path}')"
                    elif original_env_key_value != key_from_dotenv_cwd: 
                        # This case is less likely with override=True, but covers if os.environ changed
                        source_of_key = ".env file affecting environment"
                    elif not source_of_key: # Only if it wasn't already set by --api-key or --config-file
                         source_of_key = "GOOGLE_API_KEY from environment (possibly set by .env)"


            if not api_key_to_use: # Fallback to check environment if still not found
                env_api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('OPENAI_API_KEY') or os.getenv('API_KEY')
                if env_api_key:
                    api_key_to_use = env_api_key
                    # Avoid overwriting a more specific source like .env
                    if not source_of_key or source_of_key == "command line --api-key argument" and not args.api_key:
                        source_of_key = "GOOGLE_API_KEY environment variable (system/shell)"

            if source_of_key:
                logging.info(f"Using Google API Key sourced from: {source_of_key}.")
            elif not api_key_to_use: # Still no key
                logging.warning("No Google API Key found from --api-key, --config-file, .env, or global environment variables. Elaboration may fail or use a default/mocked API.")
            # --- End of API key sourcing logic ---

            try:
                finding_id_int = int(args.finding_id)
            except ValueError:
                print(f"Error: Finding ID '{args.finding_id}' must be an integer index.", file=sys.stderr)
                sys.exit(1)
            
            elaboration_text = elaborate_finding(
                report_path=args.report_file,
                finding_id=finding_id_int,
                api_key=api_key_to_use, # Use the correctly sourced API key
                model_name=model_name_to_use,
                api_base=api_base_to_use,
                context_window_lines=args.context_lines,
                cache_manager=cache_manager,
                no_cache=args.no_cache
            )

            if elaboration_text.startswith("Error:"):
                print(elaboration_text, file=sys.stderr)
                sys.exit(1)

            # --- New output handling logic ---
            output_to_write = ""
            # Treat 'markdown' as 'md' for format checking
            effective_output_format = 'md' if args.output_format == 'markdown' else args.output_format
            is_json_output = effective_output_format == 'json'

            if is_json_output:
                output_to_write = json.dumps({"elaboration": elaboration_text}, indent=4)
            else: # md or console
                output_to_write = elaboration_text

            if args.output_file:
                try:
                    with open(args.output_file, 'w', encoding='utf-8') as f:
                        f.write(output_to_write)
                    print(f"Elaboration successfully saved to {args.output_file}")
                    if is_json_output:
                         print(f"(The file contains the elaboration in JSON format.)")
                except IOError as e:
                    print(f"Error: Could not write to output file '{args.output_file}': {e}", file=sys.stderr)
                    if effective_output_format != 'console': 
                         print("\n--- Outputting to Console as Fallback ---")
                    print(output_to_write) 
                    sys.exit(1)
            else: 
                print(output_to_write)
            
            sys.exit(0) # Success for elaborate command

        else: # Should not be reached due to argparse 'required=True' for subparsers
            print(f"Error: Unknown command '{args.command}'", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if cache_manager:
            # print("DEBUG: Closing CacheManager...") # Optional debug print
            cache_manager.close()

if __name__ == "__main__":
    main() 