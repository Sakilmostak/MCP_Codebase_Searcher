# Troubleshooting

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
            5.  Click "New" and paste the directory path (e.g., `C:\\Users\\YourUser\\AppData\\Roaming\\Python\\PythonXY\\Scripts`).
            6.  Click "OK" on all open dialogs. You may need to open a new Command Prompt or PowerShell window for the changes to take effect.

    After updating your `PATH`, the `mcp-searcher` command should be accessible from any directory in your terminal.

*   **ModuleNotFoundError (e.g., `No module named 'google_generativeai'`):**
    *   This usually indicates an issue with the installation or virtual environment.
    *   If installed via `pip install mcp-codebase-searcher`, dependencies should be handled automatically. Ensure you are in the correct virtual environment. Try `pip install --force-reinstall mcp-codebase-searcher`.
    *   Ensure you are using the Python interpreter from your activated virtual environment.

    *   **"Error: Elaboration model not initialized"** or API key missing notes: This means the API key was not found through any of the supported methods for your configured model provider. 
    *   **Invalid Default Key:** If you're using default arguments, ensure you have correctly configured the provider specified. Remember to supply `--model-name` along with `OPENAI_API_KEY`, etc.
    *   Verify that the environment variable used by LiteLLM (e.g., `OPENAI_API_KEY`) is set and exported in your current shell session. If using a `.env` file, ensure it is in the directory where you are running the `mcp-searcher` command.

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
