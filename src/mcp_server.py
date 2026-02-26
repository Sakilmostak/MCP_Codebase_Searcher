
import json
import logging
import os
import re
from typing import List, Optional

from dotenv import load_dotenv

from mcp.server.fastmcp import FastMCP
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, INTERNAL_ERROR, INVALID_PARAMS

from file_scanner import FileScanner
from mcp_search import Searcher
from mcp_elaborate import ContextAnalyzer

# Initialize FastMCP server
mcp = FastMCP("mcp-codebase-searcher")

def _load_env_configuration():
    """Ensure we try to load .env variables locally for litellm settings."""
    dotenv_path = os.path.join(os.getcwd(), '.env')
    load_dotenv(dotenv_path=dotenv_path, override=True)

@mcp.tool()
def search_codebase(
    query: str, 
    paths: list[str] = ["."], 
    is_case_sensitive: bool = False, 
    is_regex: bool = False, 
    context_lines: int = 3,
    include_hidden: bool = False
) -> str:
    """
    Search the codebase for specific text or regex patterns to find implementations or context.
    
    Args:
        query: The search string or regex pattern.
        paths: List of directories or files to search within. Defaults to current directory.
        is_case_sensitive: Whether the search should be case sensitive.
        is_regex: Whether the query should be treated as a regular expression.
        context_lines: Number of lines of context to include before and after each match.
        include_hidden: Whether to include hidden files (starting with '.') in the search.
        
    Returns:
        A JSON string containing the list of search findings (file_path, line_number, snippet, match_text).
    """
    try:
        exclude_dirs_patterns = [
            re.compile(r"^\.git$"), 
            re.compile(r"^node_modules$"), 
            re.compile(r"^venv$"), 
            re.compile(r"^__pycache__$")
        ]
        exclude_files_patterns = [
            re.compile(r".*\.pyc$"), 
            re.compile(r".*\.log$")
        ]
        
        # In MCP context, scanner receives exclusion patterns at __init__
        scanner = FileScanner(
            custom_exclude_patterns=exclude_dirs_patterns + exclude_files_patterns,
            exclude_dot_items=not include_hidden
        )
        
        # We start scan from the paths provided
        # Since Searcher accepts a list of file paths & timestamps, we scan them consecutively
        matched_files_data = []
        for path in paths:
            matched_files_data.extend(scanner.scan_directory(path))
        
        searcher = Searcher(
            query=query,
            is_case_sensitive=is_case_sensitive,
            is_regex=is_regex,
            context_lines=context_lines
        )
        
        all_results = searcher.search_files(matched_files_data)
        
        return json.dumps(all_results, indent=2)
    except Exception as e:
        error_msg = f"Failed to search codebase: {str(e)}"
        logging.error(error_msg)
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=error_msg))

@mcp.tool()
def elaborate_finding(
    file_path: str,
    line_number: int,
    snippet: str,
    context_window_lines: int = 10
) -> str:
    """
    Use a sub-LLM agent to deeply elaborate and summarize what a specific code snippet or finding does based on its broader file context.
    
    Args:
        file_path: The absolute or relative path to the file containing the finding.
        line_number: The line number where the finding occurred.
        snippet: The specific code snippet (can be a few lines) that matched the query.
        context_window_lines: Lines of broader context to include from the surrounding file.
        
    Returns:
        A natural language summary and elaboration of the code snippet.
    """
    try:
        _load_env_configuration()
        
        api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('OPENAI_API_KEY') or os.getenv('API_KEY')
        model_name = os.getenv('LITELLM_MODEL_NAME') or os.getenv('MODEL_NAME') or 'gemini/gemini-1.5-flash-latest'
        api_base = os.getenv('LITELLM_API_BASE') or os.getenv('API_BASE')
        
        analyzer = ContextAnalyzer(
            api_key=api_key,
            model_name=model_name,
            api_base=api_base
        )
        
        full_file_content = None
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    full_file_content = f.read()
            except UnicodeDecodeError:
                with open(file_path, 'r', encoding='latin-1') as f:
                    full_file_content = f.read()
        
        elaboration = analyzer.elaborate_on_match(
            file_path=file_path,
            line_number=line_number,
            snippet=snippet,
            full_file_content=full_file_content,
            context_window_lines=context_window_lines
        )
        
        return elaboration
    except Exception as e:
        error_msg = f"Failed to elaborate finding: {str(e)}"
        logging.error(error_msg)
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=error_msg))

def main():
    """Start the FAST MCP server."""
    # Basic logging setup
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # FastMCP automatically routes over STDIO when run as a script.
    mcp.run()

if __name__ == "__main__":
    main()
