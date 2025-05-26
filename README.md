# MCP Codebase Searcher

MCP Codebase Searcher is a Python tool designed to scan codebases, search for text or regular expression patterns, and optionally elaborate on the findings using Google Gemini.

## Features

*   Search for exact strings or regular expression patterns.
*   Case-sensitive or case-insensitive searching.
*   Specify context lines to display around matches.
*   Exclude specific directories and file patterns.
*   Option to include/exclude hidden files and directories.
*   Output results in console, JSON, or Markdown format.
*   Save search results to a file.
*   Elaborate on individual findings from a JSON report using Google Gemini.

## Installation

This project uses Python 3.8+.

1.  **Clone the repository (if applicable):**
    ```bash
    git clone <repository_url>
    cd mcp_codebase_searcher
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install the package:**
    Once the package is built (see Building section below), you can install it using pip:
    ```bash
    pip install dist/mcp_codebase_searcher-*.whl 
    ```
    Alternatively, for development, install in editable mode from the project root:
    ```bash
    pip install -e .
    ```

4.  **API Key (for Elaboration):**
    To use the elaboration feature, you need a Google API key for Gemini. You can provide it via:
    *   The `--api-key` argument when using the `elaborate` command.
    *   A JSON configuration file specified with `--config-file` (containing `{"GOOGLE_API_KEY": "YOUR_KEY"}`).
    *   An environment variable `GOOGLE_API_KEY`.
    *   A `config.py` file in the project root (if running from source) that has a `load_api_key()` function returning the key.

    The API key is sourced with the following precedence: `--api-key` argument > `--config-file` > `GOOGLE_API_KEY` environment variable > `config.py` module.

    Create a `.env` file in the project root for local development if using environment variables:
    ```
    GOOGLE_API_KEY="YOUR_API_KEY_HERE"
    ```

## Usage

The tool provides two main commands: `search` and `elaborate`.

### Search

```bash
mcp-searcher search "your_query" path/to/search [--regex] [--case-sensitive] [--context LINES] [--exclude-dirs .git,node_modules] [--exclude-files *.log] [--include-hidden] [--output-format json] [--output-file results.json]
```

**Arguments:**

*   `query`: The search term or regex pattern.
*   `paths`: One or more file or directory paths to search within.
*   `--regex`, `-r`: Treat the `query` as a Python regular expression pattern.
*   `--case-sensitive`, `-c`: Perform a case-sensitive search. By default, search is case-insensitive.
*   `--context LINES`, `-C LINES`: Number of context lines to show around each match (default: 3). Set to 0 for no context.
*   `--exclude-dirs PATTERNS`: Comma-separated list of directory name patterns (using `fnmatch` wildcards like `*`, `?`) to exclude (e.g., `.git,node_modules,build,*cache*`).
*   `--exclude-files PATTERNS`: Comma-separated list of file name patterns (using `fnmatch` wildcards) to exclude (e.g., `*.log,*.tmp,temp_*`).
*   `--include-hidden`: Include hidden files and directories (those starting with a period `.`) in the scan. By default, they are excluded unless they are explicitly provided in `paths`.
*   `--output-format FORMAT`: Format for the output. Choices: `console` (default), `json`, `md` (or `markdown`).
*   `--output-file FILE`: Path to save the output. If not provided, prints to the console.

**Examples:**

1.  Search for "TODO" (case-insensitive) in the `src` directory and its subdirectories, excluding `__pycache__` directories and any `.tmp` or `.log` files, and save the results as JSON:
    ```bash
    mcp-searcher search "TODO" src --exclude-dirs __pycache__ --exclude-files "*.tmp,*.log" --output-format json --output-file todos.json
    ```

2.  Search for Python function definitions (e.g., `def my_function(`) using a regular expression in all `.py` files within the current directory (`.`) and its subdirectories:
    ```bash
    mcp-searcher search "^\s*def\s+\w+\s*\(.*\):" . --regex --exclude-files "!*.py" # Assumes FileScanner handles includes or user pre-filters paths if !*.py is not directly supported for exclusion.
    # A better way if FileScanner doesn't support include patterns in exclude-files:
    # Find .py files first, then pass to mcp-searcher, or rely on mcp-searcher scanning all and then filtering if it did.
    # For this tool, it scans all non-excluded, so to search only .py, you'd typically not exclude others unless they are binaries etc.
    # Corrected Example for just regex:
    mcp-searcher search "^\s*def\s+\w+\s*\(.*\):" . --regex
    ```
    *Note: Ensure your regex is quoted correctly for your shell, especially if it contains special characters.*

3.  Perform a case-sensitive search for the exact string "ErrorLog" in all files in `/var/log`, include hidden files, and output to a Markdown file:
    ```bash
    mcp-searcher search "ErrorLog" /var/log --case-sensitive --include-hidden --output-format md --output-file errors_report.md
    ```

### Elaborate

```bash
mcp-searcher elaborate --report-file path/to/report.json --finding-id INDEX [--api-key YOUR_KEY] [--config-file path/to/config.json] [--context-lines LINES]
```

**Arguments:**

*   `--report-file FILE`: (Required) Path to the JSON search report file generated by the `search` command.
*   `--finding-id INDEX`: (Required) The 0-based index (ID) of the specific finding within the report file that you want to elaborate on.
*   `--api-key KEY`: Your Google API key for Gemini. If provided, this takes precedence over other key sources.
*   `--config-file FILE`: Path to an optional JSON configuration file containing your `GOOGLE_API_KEY` (e.g., `{"GOOGLE_API_KEY": "YOUR_KEY"}`).
*   `--context-lines LINES`: Number of lines of broader context from the source file (surrounding the original snippet) to provide to the LLM for better understanding (default: 10).

**Examples:**

1.  Elaborate on the first finding (index 0) from `todos.json`, assuming the API key is set as an environment variable (`GOOGLE_API_KEY`) or in a `config.py` / `.env` file:
    ```bash
    mcp-searcher elaborate --report-file todos.json --finding-id 0
    ```

2.  Elaborate on the third finding (index 2) from `search_results.json`, providing the API key directly and specifying 15 lines of context for the LLM:
    ```bash
    mcp-searcher elaborate --report-file search_results.json --finding-id 2 --api-key "AIzaSyXXXXXXXXXXXXXXXXXXX" --context-lines 15
    ```

3.  Elaborate on a finding from `project_report.json`, using an API key stored in a custom configuration file named `my_gemini_config.json` located in the user's home directory:
    ```bash
    mcp-searcher elaborate --report-file project_report.json --finding-id 5 --config-file ~/.my_gemini_config.json
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
    **path/to/your/file.py:42**
    ```text
      Context line 1 before match
      >>>The line with the matched text<<<
      Context line 1 after match
    ```
    ---
    **another/file.txt:101**
    ```text
      Just the >>>matched line<<< if no context
    ```
    ```
    This format is suitable for generating reports or for easy pasting into documents that support Markdown.

## Building

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

## Troubleshooting

Here are some common issues and how to resolve them:

*   **Command not found (`mcp-searcher: command not found`):**
    *   Ensure you have activated the virtual environment where the package was installed: `source venv/bin/activate` (or `venv\Scripts\activate` on Windows).
    *   If installed in editable mode (`pip install -e .`), ensure you are in the project root or that the project root is in your `PYTHONPATH`.
    *   If installed via wheel, ensure the virtual environment's `bin` (or `Scripts`) directory is in your system's `PATH`.

*   **ModuleNotFoundError (e.g., `No module named 'google_generativeai'`):**
    *   Make sure all dependencies are installed correctly within your active virtual environment. Try reinstalling: `pip install --force-reinstall -r requirements.txt` (if you have one from source) or `pip install --force-reinstall mcp-codebase-searcher` (if from wheel, though direct wheel reinstallation might be `pip install --force-reinstall dist/mcp_codebase_searcher-*.whl`). For an installed package, dependencies should be handled automatically.
    *   Ensure you are using the Python interpreter from your activated virtual environment.

*   **API Key Errors (for `elaborate` command):**
    *   **"Could not initialize GenerativeModel... API key not found."**: This means the Google API key was not found through any of the supported methods (argument, config file, environment variable, `config.py`). Double-check the [API Key section under Installation](#api-key-for-elaboration).
    *   **"Could not initialize GenerativeModel... Invalid API key."**: The key was found but is incorrect or unauthorized for the Gemini API.
    *   Ensure your `.env` file (if used) is in the correct location (project root if running from source) and correctly formatted (`GOOGLE_API_KEY="YOUR_KEY"`).
    *   Verify that the environment variable `GOOGLE_API_KEY` is set and exported in your current shell session if not using an `.env` file with `python-dotenv` support.

*   **File/Directory Not Found (for `search` or `elaborate --report-file`):**
    *   Double-check that the paths provided to the `search` command or the `--report-file` argument are correct and accessible.
    *   Relative paths are resolved from the current working directory where you run the command.

*   **Permission Denied Errors:**
    *   Ensure you have read permissions for the files/directories you are trying to search, and write permissions if using `--output-file` to a restricted location.

*   **Invalid Regular Expression (for `search --regex`):**
    *   The tool will output an error if the regex pattern is invalid. Test your regex pattern with online tools or Python's `re` module separately.
    *   Remember to quote your regex pattern properly in the shell, especially if it contains special characters like `*`, `(`, `)`, `|`, etc. Single quotes (`'pattern'`) are often safer than double quotes in bash/zsh for complex patterns.

*   **No Matches Found:**
    *   Verify your query term or regex pattern. Try a simpler, broader query first.
    *   Check your `--case-sensitive` flag. Search is case-insensitive by default.
    *   Review your exclusion patterns (`--exclude-dirs`, `--exclude-files`). You might be unintentionally excluding the files containing matches.
    *   Ensure the target files are not binary or are of a type the tool can read (primarily text-based).
    *   If searching hidden files, ensure `--include-hidden` is used.

*   **Incorrect JSON in Report File (for `elaborate` command):**
    *   The `elaborate` command expects a JSON file in the format produced by `mcp-searcher search --output-format json`. If the file is malformed or not a valid JSON array of search results, elaboration will fail.
    *   Error messages like "Could not decode JSON from report file" or "Finding ID ... is out of range" point to issues with the report file or the provided ID.

*   **Shell Quoting Issues for Query:**
    *   If your search query contains spaces or special shell characters (e.g., `!`, `*`, `$`, `&`), ensure it's properly quoted. Single quotes (`'your query'`) are generally safest to prevent shell expansion.
    ```bash
    mcp-searcher search 'my exact phrase with spaces!' . 
    mcp-searcher search 'pattern_with_$(dollar_sign_and_parens)' . --regex
    ``` 