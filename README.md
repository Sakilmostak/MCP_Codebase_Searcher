# MCP Codebase Searcher

**An ultra-fast, context-optimized Model Context Protocol (MCP) Server for LLM code navigation.**

MCP Codebase Searcher is a Python-based server that exposes powerful, token-efficient codebase semantic search and elaboration tools directly to your AI assistants (Claude Desktop, Cursor, etc.). By using our optimized `search_codebase` and `elaborate_finding` MCP endpoints, you can bypass the native constraints of massive context windows, eliminating token bloat and OOMs on large repositories.

## Why Use This Over Standard RAG?

When an AI attempts to read an entire codebase (Brute-force RAG), it wastes massive amounts of API compute on irrelevant files and runs into strict context window limits. 

By injecting this MCP Server into your AI's toolkit, the LLM intelligently calls our native search tool to find exactly what it needs, and then pipes that snippet into our LiteLLM-powered `elaborate_finding` sub-agent to summarize local file logic.

**Benchmark Simulation (15-File Repo):**
*   **Prompt Compute Reduction:** **-85.21%** (4,436 tokens → 656 tokens)
*   **Inference Latency:** **-41.13% Faster** (24.5s → 14.4s)
*   **Scalability:** O(1) context scaling. Safe for 100k+ line mono-repos where standard context dumps fail.

## Core Capabilities

*   **Native MCP Integration**: Exposes `@mcp.tool()` endpoints directly over STDIO for seamless AI consumption.
*   **Intelligent Self-Documentation**: The MCP server automatically feeds its own usage constraints (`@mcp.prompt()`) to the connecting AI, teaching it how to optimize its queries.
*   **Lightning Fast Regex/Text Scanner**: Case-insensitive and regex-capable tree walking with robust glob exclusions (`.git`, `node_modules`, etc).
*   **Universal LLM Support (LiteLLM)**: The elaboration sub-agent supports 100+ AI models (OpenAI, Anthropic, Google Vertex AI, Local Ollama) using the same universal structure.
*   **Disk Caching**: Built-in SQLite caching via `diskcache` to save redundant LLM elaboration compute.

## Quick Install

This project requires Python 3.8+.

```bash
pip install mcp-codebase-searcher
```
This will download and install the latest stable version and its dependencies. Ensure your pip is up to date (`pip install --upgrade pip`).

**2. Development / Manual Installation (from source):**

If you want to develop the tool or install it manually from the source code:

*   **Clone the repository:**
    ```bash
    git clone https://github.com/Sakilmostak/mcp_codebase_searcher.git # Replace with actual URL
    cd mcp_codebase_searcher
    ```

*   **Create and activate a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows use `venv\\\\Scripts\\\\activate`
    ```

*   **Install in editable mode:**
    For development, install the package in editable mode from the project root. This allows your changes to be reflected immediately.
    ```bash
    pip install -e .
    ```
    Alternatively, to install from a built wheel (after building it yourself, see [Building](#building) section):
    ```bash
    pip install dist/mcp_codebase_searcher-*.whl
    ```
## Using as an MCP Server
The `mcp-codebase-searcher` can be used dynamically as a Model Context Protocol (MCP) server. This allows AI clients (like Claude Desktop, Cursor, Xyne) to invoke the search and elaborate tools natively.

### Available MCP Tools
When running as an MCP server, the following tools are exposed to the AI client:
*   **`search_codebase`**: A lightning-fast regex and text scanner mapped to the underlying filesystem. Returns file paths, line numbers, and snippets.
*   **`elaborate_finding`**: An out-of-band LLM context-analyzer that reads 100+ surrounding lines of a finding and returns a semantic summary, saving the primary AI's context window.
*   **`read_mcp_searcher_rules`**: A configuration and guidelines tool that instructs the AI on how to properly resolve absolute paths and use the above tools effectively. AI agents are encouraged to read this before executing their first search.


### ⚠️ CRITICAL RULES FOR MCP SETUP ⚠️
Because MCP servers often spawn independently from your project's command line, they can accidentally start with their working directory pointing to the root of your filesystem (`/` or `C:\`). This completely breaks relative paths and tools.

**Rule 1: Always use FULL absolute paths for your executable command.**  
Find where `uv` is installed (`which uv`) and use that exact path.

**Rule 2: The LLM should be instructed to use absolute paths.**  
When using the tool through an AI, assure the system prompt or your questions specify the absolute path to your workspace.

### Xyne Configuration Best Practices
Modify your VS Code user settings (`Cmd + ,` -> search for "xyne.mcpServers") to securely mount the tool and write robust fallback logs:

```json
{
 "xyne.mcpServers": {
   "codebase-searcher": {
     "type": "stdio",
     "command": "/Users/YOUR_USERNAME/.local/bin/uv",
     "args": [
       "tool",
       "run",
       "--from",
       "mcp-codebase-searcher",
       "mcp-searcher-server"
     ],
     "env": {
       "MCP_WORKSPACE_ROOT": "/Users/YOUR_USERNAME/path/to/project"
     }
   }
 }
}
```

*Tip: Providing `MCP_WORKSPACE_ROOT` in the `env` tells the server exactly where your codebase lives, completely bypassing relative path failures where AI prompts otherwise search the filesystem root (`/`).*

> **Note on Tool Discovery:** You do **not** need to explicitly declare `search_codebase`, `elaborate_finding`, or the new `read_mcp_searcher_rules` tools in your JSON configurations. The MCP protocol handles tool discovery automatically—once the server connects, the AI inherently knows how to use them.

### Claude Desktop Configuration
Add the server to your `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):
```json
{
  "mcpServers": {
    "codebase-searcher": {
      "command": "/full/path/to/uv",
      "args": ["tool", "run", "--from", "mcp-codebase-searcher", "mcp-searcher-server"]
    }
  }
}
```

> **Note on Tool Discovery:** Just like with Xyne, Claude automatically syncs `search_codebase`, `elaborate_finding`, and `read_mcp_searcher_rules` upon connection without needing them hardcoded into `claude_desktop_config.json`.

### Enforcing MCP Tool Usage (Optional)

AI assistants (like Claude, Cursor, or Windsurf) often try to use their "native" search tools before realizing they have a faster MCP tool available. To permanently force your AI to use the MCP codebase searcher instead of native tools, you can create a project rules file.

Create a `.cursorrules`, `.windsurfrules`, or `.github/copilot-instructions.md` file in the root of your project and paste this exact snippet:

```markdown
When you need to explore or search this repository, you MUST strictly follow these rules:
1. ALWAYS prioritize using the `search_codebase` MCP tool for exploration and searching.
2. ONLY use your native search tools (like your built-in editor search or bash grep commands) as a fallback IF the MCP tool fails or cannot complete the request.
3. If the search results are too small to understand, immediately pipe the finding into the `elaborate_finding` MCP tool to get the full semantic context.
4. Before issuing your first search, trigger the `read_mcp_searcher_rules` tool to ensure your pathing parameters are correct.
```

### Troubleshooting

If your `search_codebase` tool is returning `[]` or throwing `Security/Performance Error` messages, this is usually caused by your AI client spawning the background server at the filesystem root. 
Please refer to the comprehensive [**Troubleshooting Guide**](./TROUBLESHOOTING.md) for solutions covering Xyne, Claude Desktop, and logging.

## Configuration

### API Key and Model Selection for Elaboration

To use the elaboration feature, you need an AI model. `mcp-codebase-searcher` uses **LiteLLM** under the hood, meaning you can configure it to use almost any API provider (OpenAI, Anthropic, Google) or even a local AI via Ollama.

You can configure the model using the `--model-name` argument. Provide any LiteLLM-compliant model string (e.g. `gpt-4o`, `ollama/llama3`, `bedrock/anthropic.claude-3-sonnet`). The default is `gemini/gemini-1.5-flash-latest`.

If your model requires an API key, you can provide it via:
*   The **`--api-key`** argument when using the `elaborate` command.
*   A JSON configuration file specified with **`--config-file`** (e.g., `{"OPENAI_API_KEY": "YOUR_KEY"}`).
*   An environment variable matching your provider (e.g., **`OPENAI_API_KEY`**, **`ANTHROPIC_API_KEY`**).

**Authentication via Cloud Identity:**
Cloud providers that use Identity Authentication (e.g., **Google Vertex AI** via `gcloud auth login` or **AWS Bedrock** via AWS credentials) do not strictly need hardcoded API keys. Just run your standard CLI sign-in beforehand.

The API key is sourced with the following precedence: **`--api-key`** argument > **`--config-file`** > **Environment variables**.

If using environment variables, you might set it in your shell profile or create a `.env` file in your project directory *when you are using the tool* (not for installation of the tool itself):
```env
# Required for your specific provider
OPENAI_API_KEY="YOUR_API_KEY_HERE"

# Optional overrides (useful if using local models or proxies)
LITELLM_MODEL_NAME="ollama/llama3"
LITELLM_API_BASE="http://localhost:11434"
```
The tool uses `python-dotenv` to load this if available in the working directory.

## Caching

`mcp-codebase-searcher` implements a caching mechanism to improve performance for repeated search and elaboration operations. This feature is particularly useful when working on the same codebase or re-visiting previous findings.

The cache stores results of search queries and elaboration outputs. When a similar operation is performed, the tool can retrieve the result from the cache instead of re-processing, saving time and, in the case of elaboration, API calls.

This functionality is powered by the `diskcache` library.

**Default Cache Location:**
By default, cache files are stored in `~/.cache/mcp_codebase_searcher` (i.e., in a directory named `mcp_codebase_searcher` within your user's standard cache directory).

**Caching CLI Arguments:**

The following command-line arguments allow you to control the caching behavior:

*   **`--no-cache`**:
    *   Disables caching entirely for the current run. Neither reading from nor writing to the cache will occur.

*   **`--clear-cache`**:
    *   Clears all data from the cache directory before the current operation proceeds. This is useful if you suspect the cache is stale or want to free up disk space.

*   **`--cache-dir`** `DIRECTORY`:
    *   Specifies a custom directory to store cache files. If the directory does not exist, the tool will attempt to create it.
    *   Example: `--cache-dir /tmp/my_search_cache`

*   **`--cache-expiry`** `DAYS`:
    *   Sets the default expiry time for new cache entries in days. Cached items older than this will be considered stale and re-fetched on the next request.
    *   Default: `7` days.
    *   Example: `--cache-expiry 3` (sets expiry to 3 days)

*   **`--cache-size-limit`** `MB`:
    *   Sets an approximate size limit for the cache directory in Megabytes (MB). When the cache approaches this limit, older or less frequently used items may be evicted to make space.
    *   Default: `100` MB.
    *   Example: `--cache-size-limit 250` (sets limit to 250 MB)

These caching options provide flexibility in managing how search and elaboration results are stored and reused, allowing you to balance performance benefits with disk space usage and data freshness.

## Project Structure

The project follows a standard Python packaging layout:

*   `src/`: Contains the main application source code for the `mcp_codebase_searcher` package.
    *   `mcp_searcher.py`: Main CLI entry point and argument parsing.
    *   `file_scanner.py`: Module for scanning directories and finding files.
    *   `mcp_search.py`: Core search logic.
    *   `mcp_elaborate.py`: Handles LLM interaction for context analysis.
    *   `report_elaborator.py`: Logic for elaborating on findings from a report.
    *   `output_generator.py`: Formats and generates output.
    *   `config.py`: Handles API key loading (though primarily used when running from source before full packaging, now mostly superseded by environment variables or direct CLI args for the installed package).
*   `tests/`: Contains all unit and integration tests.
*   `pyproject.toml`: Build system configuration and package metadata.
*   `README.md`: This file.
*   `LICENSE`: Project license.

## Usage

The tool provides two main commands: `search` and `elaborate`.

### Search

```bash
mcp-searcher search "your_query" path/to/search [--regex] [--case-sensitive] [--context LINES] [--exclude-dirs .git,node_modules] [--exclude-files *.log] [--include-hidden] [--output-format json] [--output-file results.json]
```

**Arguments:**

*   `query`: The search term or regex pattern.
*   `paths`: One or more file or directory paths to search within.
*   **`--regex`**, **`-r`**: Treat the `query` as a Python regular expression pattern.
*   **`--case-sensitive`**, **`-c`**: Perform a case-sensitive search. By default, search is case-insensitive.
*   **`--context`** `LINES`, **`-C`** `LINES`: Number of context lines to show around each match (default: 3). Set to 0 for no context.
*   **`--exclude-dirs`** `PATTERNS`: Comma-separated list of directory name patterns (using `fnmatch` wildcards like `*`, `?`) to exclude (e.g., `.git,node_modules,build,*cache*`).
*   **`--exclude-files`** `PATTERNS`: Comma-separated list of file name patterns (using `fnmatch` wildcards) to exclude (e.g., `*.log,*.tmp,temp_*`).
*   **`--include-hidden`**: Include hidden files and directories (those starting with a period `.`) in the scan. By default, they are excluded unless they are explicitly provided in `paths`.
*   **`--output-format`** `FORMAT`: Format for the output. Choices: `console` (default), `json`, `md` (or `markdown`).
*   **`--output-file`** `FILE`: Path to save the output. If not provided, prints to the console.

**Examples:**

1.  Search for "TODO" (case-insensitive) in the `src` directory and its subdirectories, excluding `__pycache__` directories and any `.tmp` or `.log` files, and save the results as JSON:
    ```bash
    mcp-searcher search "TODO" src --exclude-dirs __pycache__ --exclude-files "*.tmp,*.log" --output-format json --output-file todos.json
    ```

2.  Search for Python function definitions (e.g., `def my_function():`) using a regular expression within the current directory (`.`):
    ```bash
    mcp-searcher search "^\s*def\s+\w+\s*\(.*\):" . --regex
    ```
    *Note: Ensure your regex is quoted correctly for your shell, especially if it contains special characters. To search only within specific file types (e.g., only `.py` files), you can either provide paths directly to those files/directories containing mostly those files, or use shell commands to pipe a list of files to `mcp-searcher` if it supports reading file lists from stdin (currently, it expects paths as arguments).*

3.  Perform a case-sensitive search for the exact string "ErrorLog" in all files in `/var/log`, include hidden files, and output to a Markdown file:
    ```bash
    mcp-searcher search "ErrorLog" /var/log --case-sensitive --include-hidden --output-format md --output-file errors_report.md
    ```

### Elaborate

```bash
mcp-searcher elaborate --report-file path/to/report.json --finding-id INDEX [--model-name MODEL] [--api-key YOUR_KEY] [--api-base CUSTOM_URL] [--config-file path/to/config.json] [--context-lines LINES] [--output-format FORMAT] [--output-file FILE]
```

**Arguments:**

*   **`--report-file`** `FILE`: (Required) Path to the JSON search report file generated by the `search` command.
*   **`--finding-id`** `INDEX`: (Required) The 0-based index (ID) of the specific finding within the report file that you want to elaborate on.
*   **`--model-name`** `MODEL`: The LiteLLM model identifier to use (e.g., `gpt-4o`, `ollama/llama3`, `gemini/gemini-1.5-flash-latest`). Default is `gemini/gemini-1.5-flash-latest`.
*   **`--api-key`** `KEY`: Your provider's API key. If provided, this is prioritized.
*   **`--api-base`** `URL`: Optional custom API base URL (useful for local Ollama endpoints or proxies).
*   **`--config-file`** `FILE`: Path to an optional JSON configuration file containing API keys.
*   **`--context-lines`** `LINES`: Number of lines of broader context from the source file (surrounding the original snippet) to provide to the LLM for better understanding (default: 10).
*   **`--output-format`** `FORMAT`: Format for the elaboration output. Choices: `console` (default), `json`, `md` (or `markdown`).
*   **`--output-file`** `FILE`: Path to save the elaboration output. If not provided, prints to the console. If an error occurs during elaboration, the error message itself will be printed/saved.

**Examples:**

1.  Elaborate on the first finding (index 0) from `todos.json`, assuming the API key is set as an environment variable (e.g., `OPENAI_API_KEY`) using OpenAI's `gpt-4o` model:
    ```bash
    mcp-searcher elaborate --report-file todos.json --finding-id 0 --model-name gpt-4o
    ```

2.  Elaborate on a finding from `search_results.json` natively using your local machine by specifying the Ollama model:
    ```bash
    mcp-searcher elaborate --report-file search_results.json --finding-id 2 --model-name "ollama/llama3" --context-lines 15
    ```

3.  Elaborate on a finding using an authenticated cloud identity platform (Google Cloud Vertex AI). First login via `gcloud auth application-default login`, then:
    ```bash
    mcp-searcher elaborate --report-file project_report.json --finding-id 5 --model-name "vertex_ai/gemini-1.5-flash"
    ```

4.  Elaborate on the first finding from `todos.json` and save the output as a JSON file named `elaboration_0.json`:
    ```bash
    mcp-searcher elaborate --report-file todos.json --finding-id 0 --output-format json --output-file elaboration_0.json
    ```

## Output Formats

The `search` command can output results in several formats using the `--output-format` option:

*   **`console` (default):** Prints results directly to the terminal in a human-readable format. Each match includes the file path, line number, and the line containing the match with the matched text highlighted (e.g., `>>>matched text<<<`). Context lines, if requested, are shown above and below the match line.

    *Example Console Output (simplified):*
    ```text
    path/to/your/file.py:42
      Context line 1 before match
      >>>The line with the matched text<<<
      Context line 1 after match
    ---
    another/file.txt:101
      Just the >>>matched line<<< if no context
    ---
    ```

*   **`json`:** Outputs results as a JSON array. Each object in the array represents a single match and contains the following fields:
    *   `file_path`: Absolute path to the file containing the match.
    *   `line_number`: The 1-based line number where the match occurred.
    *   `match_text`: The actual text that was matched.
    *   `snippet`: A string containing the line with the match and any surrounding context lines requested. The matched text within the snippet is highlighted with `>>> <<<`.
    *   `char_start_in_line`: The 0-based starting character offset of the match within its line.
    *   `char_end_in_line`: The 0-based ending character offset of the match within its line.

    *Example JSON Output (for one match):*
    ```json
    [
      {
        "file_path": "/path/to/your/file.py",
        "line_number": 42,
        "match_text": "matched text",
        "snippet": "  Context line 1 before match\n  >>>The line with the matched text<<<\n  Context line 1 after match",
        "char_start_in_line": 25,
        "char_end_in_line": 37
      }
      // ... more matches ...
    ]
    ```
    This format is ideal for programmatic processing and is required as input for the `elaborate` command.

*   **`md` or `markdown`:** Outputs results in Markdown format. Each match is typically presented with the file path as a heading or bolded, followed by the line number and the snippet (often as a preformatted text block).

    *Example Markdown Output (simplified):*
    ```markdown
    ### Match in `path/to/your/file.py` (Line 42)

    ```text
      Context line 1 before match
      >>>The line with the matched text<<<
      Context line 1 after match
    ```

    ---

    ### Match in `another/file.txt` (Line 101)

    ```text
      Just the >>>matched line<<< if no context
    ```
    ```
    This format is suitable for generating reports or for easy pasting into documents that support Markdown.

## Building

This section is primarily for developers contributing to the project or those who wish to build the package from source manually. If you just want to use the tool, please use the [PyPI installation method](#installation) above.

To build the package (wheel and source distribution):

1.  Ensure you have the necessary build tools:
    ```bash
    pip install build
    ```
2.  Run the build command from the project root:
    ```bash
    python -m build
    ```
    This will create `sdist` and `wheel` files in a `dist/` directory.

## Running Tests

1.  Ensure test dependencies are installed (if any beyond main dependencies).
2.  Run tests using unittest discovery from the project root:
    ```bash
    python -m unittest discover -s tests
    ```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

