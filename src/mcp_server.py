
import json
import logging
import os
import re
from typing import List, Optional

from dotenv import load_dotenv

from mcp.server.fastmcp import FastMCP, Context
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, INTERNAL_ERROR, INVALID_PARAMS

from file_scanner import FileScanner
from mcp_search import Searcher
from mcp_elaborate import ContextAnalyzer

import logging.handlers

# Configure basic logging for debugging
log_file = os.path.expanduser("~/.mcp_searcher.log")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("mcp-codebase-searcher")

# Add a rotating file handler to dump logs specifically for the user to debug
try:
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5*1024*1024, backupCount=2
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
except Exception:
    pass # Failsafe if we can't write to their home directory

# Initialize FastMCP server
mcp = FastMCP("mcp-codebase-searcher")

def _load_env_configuration():
    """Ensure we try to load .env variables locally for litellm settings."""
    dotenv_path = os.path.join(os.getcwd(), '.env')
    load_dotenv(dotenv_path=dotenv_path, override=True)

AI_USAGE_GUIDELINES = """
# System Rules: MCP Codebase Searcher Guidelines

*If you are an AI assistant reading this file, you have been equipped with the `mcp-codebase-searcher` server integration. You must abide by the following operational rules when executing user prompts involving your available codebase tools.*

## Tool 1: `search_codebase`
You have access to a lightning-fast regex and text scanner mapped to the underlying filesystem. 
**When to use:**
- When the user asks you to "find", "locate", or "where is" a feature or function.
- When you do not have the complete repository loaded in your prompt context and need to discover where an API endpoint, class, or variable is defined.
- Always prefer `search_codebase` BEFORE attempting to guess file structures or writing new code that relies on internal implementations.

**Usage Rules:**
- **CRITICAL: EXCLUSIVELY USE ABSOLUTE PATHS.** The MCP server environment may execute from the filesystem root (`/`) rather than the workspace you are currently in. Relative paths like `.` or `src/` will fail silently or throw security errors. You MUST resolve the full absolute path of the user's workspace (e.g. `/Users/name/project`) before calling this tool.
- Keep your `query` extremely concise. Search for unique identifiers like `"def my_function"`, `class UserLogin`, or custom error names. Avoid full sentence queries.
- It returns an array of JSON objects containing `file_path`, `line_number`, and `snippet`. Only use this snippet for brief verification. If you need to deeply understand the file, pass this output to `elaborate_finding`.

## Tool 2: `elaborate_finding`
You have access to an out-of-band LLM context-analyzer (`elaborate_finding`) that uses LiteLLM to deeply analyze a codebase file without bloating your own primary context window.
**When to use:**
- When `search_codebase` returns a `snippet` that is too small for you to see the full picture.
- When the user asks you to explain, summarize, or debug a specific file/function you found.

**Usage Rules:**
- Instead of using native commands to print/cat the entire file into your context (which burns tokens and causes OOMs), pipe the `file_path`, `line_number`, and `snippet` from the search tool directly into `elaborate_finding`.
- `elaborate_finding` will autonomously read the surrounding 100+ lines, pass it to an external AI model, and return a heavily compressed, semantic summary of the logic *back to you*.
- Use this summary to inform your final response to the user.
"""

@mcp.prompt()
def searcher_guidelines() -> str:
    """Get the usage guidelines and rules for the codebase searcher tools."""
    return AI_USAGE_GUIDELINES

@mcp.tool()
def read_mcp_searcher_rules() -> str:
    """
    CRITICAL: Read this before using search_codebase or elaborate_finding for the first time.
    Returns the mandatory system rules, path resolution strict guidelines, and best practices for the mcp-codebase-searcher.
    """
    return AI_USAGE_GUIDELINES

def _resolve_paths(raw_paths: list[str]) -> list[str]:
    """Attempt to aggressively resolve relative paths against known workspace indicators."""
    resolved = []
    # If the user explicitly provided a workspace root (e.g. configuring the MCP server env vars)
    workspace_root = os.getenv("WORKSPACE_ROOT") or os.getenv("MCP_WORKSPACE_ROOT")
    
    for p in raw_paths:
        if os.path.isabs(p):
            resolved.append(os.path.normpath(p))
            continue
            
        # It's a relative path. 
        # First, try to prepend explicit workspace_root if provided
        if workspace_root:
            candidate = os.path.normpath(os.path.join(workspace_root, p))
            if os.path.exists(candidate):
                resolved.append(candidate)
                continue
        
        # Finally, just use standard abspath (which falls back to cwd, often incorrectly `/` in MCP)
        resolved.append(os.path.abspath(p))
        
    return resolved

@mcp.tool()
async def search_codebase(
    query: str, 
    ctx: Context,
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
        paths: List of directories or files to search within. MUST BE ABSOLUTE PATHS (e.g. /Users/name/project). Do not use relative paths like '.' as they will resolve to root.
        is_case_sensitive: Whether the search should be case sensitive.
        is_regex: Whether the query should be treated as a regular expression.
        context_lines: Number of lines of context to include before and after each match.
        include_hidden: Whether to include hidden files (starting with '.') in the search.
        
    Returns:
        A JSON string containing the list of search findings (file_path, line_number, snippet, match_text).
        
    USAGE GUIDELINES FOR AI:
    - CRITICAL: ALWAYS USE ABSOLUTE PATHS for the `paths` argument (e.g., `/Users/username/workspace`). Do NOT use `.` or relative paths, as the server runs independently and will resolve relative paths against `/`.
    - Keep your `query` extremely concise (e.g. "def my_function", "class UserLogin").
    - Use this tool BEFORE attempting to write code that depends on internal implementations.
    - If the returned snippet is too small for full understanding, pass the result into `elaborate_finding`.
    """
    try:
        # Resolve paths dynamically attempting to use MCP_WORKSPACE_ROOT if available
        resolved_paths = _resolve_paths(paths)
        
        # Security & Performance Check: Prevent scanning entire root drives
        # This protects against VS Code extensions defaulting CWD to `/` and timing out
        for rp in resolved_paths:
            # Check for Unix root `/` or Windows roots like `C:\` or `C:/`
            if rp == '/' or re.match(r'^[A-Za-z]:\\?$', rp) or re.match(r'^[A-Za-z]:/?$', rp):
                # Only error on root if the original path ACTUALLY WAS literally the root string.
                # If the original path was relative (e.g., ".") and our resolver evaluated it to "/",
                # we know for certain the MCP client spawned without a working directory payload.
                orig = paths[resolved_paths.index(rp)]
                if orig != '/' and not re.match(r'^[A-Za-z]:\\?$', orig):
                    error_msg = (
                        f"Path Resolution Error: You provided '{orig}', which resolved to the root directory ('{rp}').\n"
                        f"Your MCP client did not spawn with a working directory payload.\n"
                        f"CRITICAL FIX: You MUST pass the FULL ABSOLUTE PATH to the user's workspace "
                        f"(e.g., '/Users/name/project') in the `paths` argument. Relative paths are temporarily blocked."
                    )
                else:
                    error_msg = (
                        f"Security/Performance Error: Attempted to scan the entire filesystem root ('{rp}').\n"
                        f"Please specify a more targeted workspace folder path in your query."
                    )
                logger.error(error_msg)
                await ctx.error(error_msg)
                return json.dumps([{"error": error_msg}])

        logger.info(f"Starting codebase search. Query: '{query}', Paths: {resolved_paths}, Regex: {is_regex}")
        await ctx.info(f"Starting codebase search. Query: '{query}', Paths: {resolved_paths}, Regex: {is_regex}")

        # In MCP context, scanner uses default exclusions automatically
        scanner = FileScanner(
            exclude_dot_items=not include_hidden,
            custom_exclude_patterns=['target', 'build', 'dist'] # Common compile outputs
        )
        
        matched_files_data = []
        for path in paths:
            files_found = scanner.scan_directory(path)
            logger.info(f"Scanned {path}, found {len(files_found)} accessible files.")
            await ctx.info(f"Scanned {path}, found {len(files_found)} accessible files.")
            matched_files_data.extend(files_found)
            
        logger.info(f"Total files to search: {len(matched_files_data)}")
        await ctx.info(f"Total files to search: {len(matched_files_data)}")
        
        searcher = Searcher(
            query=query,
            is_case_sensitive=is_case_sensitive,
            is_regex=is_regex,
            context_lines=context_lines
        )
        
        logger.info(f"Running Searcher over {len(matched_files_data)} files...")
        await ctx.info(f"Running Searcher over {len(matched_files_data)} files...")
        all_results = searcher.search_files(matched_files_data)
        logger.info(f"Search complete. Found {len(all_results)} matches.")
        await ctx.info(f"Search complete. Found {len(all_results)} matches.")
        
        return json.dumps(all_results, indent=2)
    except Exception as e:
        error_msg = f"Failed to search codebase: {str(e)}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=error_msg))

@mcp.tool()
async def elaborate_finding(
    file_path: str,
    line_number: int,
    snippet: str,
    ctx: Context,
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
        
    USAGE GUIDELINES FOR AI:
    - Do NOT aggressively read entire files into context if they are massive. Pipe the search tool outputs directly into this elaboration tool.
    - This tool uses an external sub-agent to fetch and summarize 100+ surrounding lines of code cheaply and efficiently, returning only the dense semantic understanding back to you.
    """
    try:
        logger.info(f"Starting ContextAnalyzer sub-agent for elaboration on {file_path}:{line_number}...")
        await ctx.info(f"Starting ContextAnalyzer sub-agent for elaboration on {file_path}:{line_number}...")
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
