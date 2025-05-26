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

**1. Install from PyPI (Recommended):**

The easiest way to install `mcp-codebase-searcher` is from PyPI using pip:

```bash
pip install mcp-codebase-searcher
```
This will download and install the latest stable version and its dependencies. Ensure your pip is up to date (`pip install --upgrade pip`).

**2. API Key (for Elaboration):**

To use the elaboration feature, you need a Google API key for Gemini. You can provide it via:
*   The `--api-key` argument when using the `elaborate` command.
*   A JSON configuration file specified with `--config-file` (containing `{\\"GOOGLE_API_KEY\\": \\"YOUR_KEY\\"}`).
*   An environment variable `GOOGLE_API_KEY`.

The API key is sourced with the following precedence: `--api-key` argument > `--config-file` > `GOOGLE_API_KEY` environment variable.

If using environment variables, you might set it in your shell profile or create a `.env` file in your project directory *when you are using the tool* (not for installation of the tool itself):
```
GOOGLE_API_KEY="YOUR_API_KEY_HERE"
```
The tool uses `python-dotenv` to load this if available in the working directory.

**3. Development / Manual Installation (from source):**

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
    mcp-searcher search "^\\s*def\\s+\\w+\\s*\\(.*\\):" . --regex --exclude-files "!*.py" # Assumes FileScanner handles includes or user pre-filters paths if !*.py is not directly supported for exclusion.
    # A better way if FileScanner doesn't support include patterns in exclude-files:
    # Find .py files first, then pass to mcp-searcher, or rely on mcp-searcher scanning all and then filtering if it did.
    # For this tool, it scans all non-excluded, so to search only .py, you'd typically not exclude others unless they are binaries etc.
    # Corrected Example for just regex:
    mcp-searcher search "^\\s*def\\s+\\w+\\s*\\(.*\\):" . --regex
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

3.  Elaborate on a finding from `project_report.json`, using an API key stored in a custom configuration file named `my_gemini_config.json` located in the user\'s home directory:
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
        \"file_path\": \"/path/to/your/file.py\",
        \"line_number\": 42,
        \"match_text\": \"matched text\",
        \"snippet\": \"  Context line 1 before match\\n  >>>The line with the matched text<<<\\n  Context line 1 after match\",
        \"char_start_in_line\": 25, 
        \"char_end_in_line\": 37
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

## Troubleshooting

Here are some common issues and how to resolve them:

*   **Command Not Found after `pip install` (`mcp-searcher: command not found`):**

    If you install `mcp-codebase-searcher` using `pip install mcp-codebase-searcher` (especially with `pip install --user mcp-codebase-searcher` or if your global site-packages isn't writable), `pip` might install the script `mcp-searcher` to a directory that is not in your system's `PATH`.

    You will see a warning during installation similar to:
    ```
    WARNING: The script mcp-searcher is installed in '/Users/your_username/Library/Python/X.Y/bin' which is not on PATH.
    Consider adding this directory to PATH or, if you prefer to suppress this warning, use --no-warn-script-location.
    ```
    (The exact path will vary based on your operating system and Python version.)

    If the `mcp-searcher` command is not found after installation:

    1.  **Identify the script location:** Note the directory mentioned in the `pip` warning (e.g., `/Users/your_username/Library/Python/X.Y/bin` on macOS, or `~/.local/bin` on Linux).

    2.  **Add the directory to your PATH:**
        *   **For Bash users (common on Linux and older macOS):**
            Edit your `~/.bashrc` or `~/.bash_profile` file:
            ```bash
            nano ~/.bashrc  # or ~/.bash_profile
            ```
            Add the following line at the end, replacing `/path/to/your/python/scripts` with the actual directory from the warning:
            ```bash
            export PATH="/path/to/your/python/scripts:$PATH"
            ```
            Save the file, then apply the changes by running `source ~/.bashrc` (or `source ~/.bash_profile`) or by opening a new terminal.

        *   **For Zsh users (common on newer macOS):**
            Edit your `~/.zshrc` file:
            ```bash
            nano ~/.zshrc
            ```
            Add the following line at the end, replacing `/path/to/your/python/scripts` with the actual directory from the warning:
            ```bash
            export PATH="/path/to/your/python/scripts:$PATH"
            ```
            Save the file, then apply the changes by running `source ~/.zshrc` or by opening a new terminal.

        *   **For Fish shell users:**
            ```fish
            set -U fish_user_paths /path/to/your/python/scripts $fish_user_paths
            ```
            This command updates your user paths persistently. Open a new terminal for the changes to take effect.

        *   **For Windows users:**
            You can add the directory to your PATH environment variable through the System Properties:
            1.  Search for "environment variables" in the Start Menu and select "Edit the system environment variables".
            2.  In the System Properties window, click the "Environment Variables..." button.
            3.  Under "User variables" (or "System variables" if you want it for all users), find the variable named `Path` and select it.
            4.  Click "Edit...".
            5.  Click "New" and paste the directory path (e.g., `C:\\\\Users\\\\YourUser\\\\AppData\\\\Roaming\\\\Python\\\\PythonXY\\\\Scripts`).
            6.  Click "OK" on all open dialogs. You may need to open a new Command Prompt or PowerShell window for the changes to take effect.

    After updating your `PATH`, the `mcp-searcher` command should be accessible from any directory in your terminal.

*   **ModuleNotFoundError (e.g., `No module named 'google_generativeai'`):**
    *   This usually indicates an issue with the installation or virtual environment.
    *   If installed via `pip install mcp-codebase-searcher`, dependencies should be handled automatically. Ensure you are in the correct virtual environment. Try `pip install --force-reinstall mcp-codebase-searcher`.
    *   Ensure you are using the Python interpreter from your activated virtual environment.

*   **API Key Errors (for `elaborate` command):**
    *   **"Could not initialize GenerativeModel... API key not found."**: This means the Google API key was not found through any of the supported methods (argument, config file, environment variable). Double-check the [API Key section under Installation](#2-api-key-for-elaboration).
    *   **"Could not initialize GenerativeModel... Invalid API key."**: The key was found but is incorrect or unauthorized for the Gemini API.
    *   Verify that the environment variable `GOOGLE_API_KEY` is set and exported in your current shell session. If using a `.env` file, ensure it is in the directory where you are running the `mcp-searcher` command.

*   **File/Directory Not Found (for `search` or `elaborate --report-file`):**
    *   Double-check that the paths provided to the `search` command or the `--report-file` argument are correct and accessible.
    *   Relative paths are resolved from the current working directory where you run the command.

*   **Permission Denied Errors:**
    *   Ensure you have read permissions for the files/directories you are trying to search, and write permissions if using `--output-file` to a restricted location.

*   **Invalid Regular Expression (for `search --regex`):**
    *   The tool will output an error if the regex pattern is invalid. Test your regex pattern with online tools or Python\'s `re` module separately.
    *   Remember to quote your regex pattern properly in the shell, especially if it contains special characters like `*`, `(`, `)`, `|`, etc. Single quotes (`\'pattern\'`) are often safer than double quotes in bash/zsh for complex patterns.

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
    *   If your search query contains spaces or special shell characters (e.g., `!`, `*`, `$`, `&`), ensure it\'s properly quoted. Single quotes (`\'your query\'`) are generally safest to prevent shell expansion.
    ```bash
    mcp-searcher search \'my exact phrase with spaces!\' . 
    mcp-searcher search \'pattern_with_$(dollar_sign_and_parens)\' . --regex
    ``` 