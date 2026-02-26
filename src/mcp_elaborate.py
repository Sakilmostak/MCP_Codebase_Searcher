# Module for mcp_elaborate command logic

import litellm
from litellm.exceptions import ContextWindowExceededError # Example explicit import, LiteLLM has many
import os
import sys

# Direct import, as config.py is installed as a top-level module
try:
    import config
except ImportError as e:
    print(f"Warning: Could not import 'config' module. API key loading might rely on direct environment variables. Error: {e}", file=sys.stderr)
    config = None # Allow script to continue if API key is passed directly or via env
    # raise # Re-raise the ImportError to make it visible during tests

class ContextAnalyzer:
    """
    Uses a Generative AI model to elaborate on code snippets and provide context.
    """
    def __init__(self, api_key=None, model_name='gemini/gemini-1.5-flash-latest', api_base=None):
        """
        Initializes the ContextAnalyzer.

        Args:
            api_key (str, optional): The API key (if needed by the provider). If None, relies on environment variables.
            model_name (str, optional): The name of the model to use (LiteLLM format, e.g. 'gpt-4o', 'ollama/llama3'). Defaults to 'gemini/gemini-1.5-flash-latest'.
            api_base (str, optional): A custom API base URL (e.g., for local models or proxy endpoints).
        """
        self.model_name = model_name
        self.api_key = api_key  # Prioritize direct parameter
        self.api_base = api_base

        if not self.api_key:
            # We assume LiteLLM can find the key in the environment (e.g. OPENAI_API_KEY, GEMINI_API_KEY, etc.)
            # or the user is using a provider that doesn't need an explicit key (e.g. local Ollama, vertex_ai, bedrock).
            self.api_key = os.getenv('GOOGLE_API_KEY') # Fallback if previously used

        if not self.api_key:
            # Try config file last
            if config: # Check if the config module was successfully imported
                try:
                    self.api_key = config.load_api_key()
                except Exception as e:
                    print(f"Warning: Could not load API key from config: {e}", file=sys.stderr)

        # LiteLLM handles initialization dynamically at call-time, so we don't need distinct model setup here.
        # However, we can track if initialization "succeeded" by validating if model_name is set.
        if not self.model_name:
            self.model = None
            print("Error: ContextAnalyzer initialized without a model name. Elaboration will not function.", file=sys.stderr)
            return

        self.model = True # Simple flag indicating readiness
        print(f"ContextAnalyzer initialized successfully for model: {self.model_name}")

    def elaborate_on_match(self, file_path, line_number, snippet, full_file_content=None, context_window_lines=10):
        """
        Elaborates on a search match using the generative model.

        Args:
            file_path (str): The path of the file where the match was found.
            line_number (int): The 1-based line number of the match.
            snippet (str): The code snippet containing the match and some surrounding context.
            full_file_content (str, optional): The full content of the file. Defaults to None.
            context_window_lines (int, optional): Number of lines before and after the match line
                                                 from full_file_content to include if provided.
                                                 Defaults to 10.

        Returns:
            str: The elaboration text from the model, or an error message.
        """
        if not self.model:
            return "Error: Elaboration model not initialized. Cannot elaborate."

        context_for_prompt = snippet
        if full_file_content:
            try:
                lines = full_file_content.splitlines()
                match_line_idx = line_number - 1 # 0-indexed
                
                start_idx = max(0, match_line_idx - context_window_lines)
                end_idx = min(len(lines), match_line_idx + context_window_lines + 1)
                
                broader_context_lines = []
                for i in range(start_idx, end_idx):
                    prefix = "  " # Indent context lines slightly
                    if i == match_line_idx:
                        prefix = ">> " # Mark the matched line
                    broader_context_lines.append(f"{prefix}{i+1: >4}: {lines[i]}")
                
                broader_context_string = '\n'.join(broader_context_lines)
                context_for_prompt = (
                    f"The following snippet was found:\n"
                    f"------------------SNIPPET------------------\n{snippet}\n"
                    f"----------------END SNIPPET------------------\n\n"
                    f"Here is a broader context from the file (matched line marked with '>>'):\n"
                    f"----------------FILE CONTEXT-----------------\n"
                    f"{broader_context_string}\n"
                    f"--------------END FILE CONTEXT---------------"
                )
            except Exception as e:
                print(f"Warning: Error processing full_file_content for prompt: {e}", file=sys.stderr)
                context_for_prompt = snippet 

        prompt = (
            f"You are an expert AI programming assistant. A code search found a match.\n"
            f"File: {file_path}\nLine: {line_number}\n\n"
            f"Context/Code:\n{context_for_prompt}\n\n"
            f"Please elaborate on this code. Your analysis should be concise (2-4 sentences ideally, max 150 words) and focus on:\n"
            f"1. What is this code snippet primarily doing or responsible for?\n"
            f"2. Based on the surrounding code (if available) and the snippet itself, what are potential implications, common use cases, or important considerations related to this code?\n"
            f"3. If applicable, suggest any potential improvements or best practices ONLY IF they are obvious and highly relevant. Avoid speculation.\n"
            f"Present your analysis clearly. Do not repeat the code itself in your answer unless quoting a very small, specific part for clarification."
        )

        try:
            # Prepare kwargs for the completion call
            kwargs = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt}],
            }
            if self.api_key:
                kwargs["api_key"] = self.api_key
            if self.api_base:
                kwargs["api_base"] = self.api_base

            response = litellm.completion(**kwargs)

            # litellm standardizes the response to an OpenAI-like format
            if response.choices and len(response.choices) > 0:
                elaboration_text = response.choices[0].message.content
                if not elaboration_text or not elaboration_text.strip():
                     print(f"Warning: Received empty elaboration from API for {file_path}:{line_number}.", file=sys.stderr)
                     return "Error: Elaboration from API was empty or unparsable"
                return elaboration_text
            else:
                print(f"Warning: No choices found in API response for {file_path}:{line_number}. Response: {response}", file=sys.stderr)
                return "Error: No content returned from API for elaboration"

        except Exception as e:
            error_message = f"API error during elaboration for {file_path}:{line_number} (litellm): {type(e).__name__} - {e}"
            print(f"Warning: {error_message}", file=sys.stderr)
            return f"Error: {error_message}"

if __name__ == '__main__':
    print("MCP Elaborate module direct execution (for testing during dev)")
    
    # Adjust import for when running this file directly from src/
    # This assumes config.py is in the same directory (src/)
    # And that the Python interpreter is run from the project root (e.g., python -m src.mcp_elaborate)
    # or that src/ is in PYTHONPATH.
    try:
        from . import config as main_config # If run as part of src package
    except ImportError:
        try:
            import config as main_config # If src/ is in path and running directly
        except ImportError:
            print("Test Main: Failed to import config for direct execution test.", file=sys.stderr)
            main_config = None

    loaded_api_key = None
    if main_config:
        try:
            loaded_api_key = main_config.load_api_key()
            if not loaded_api_key:
                 print("Test: API key from config.py is empty or not found.")
        except Exception as e:
            print(f"Test: Could not load API key via config.py: {e}")
    
    if not loaded_api_key:
        loaded_api_key = os.getenv('GOOGLE_API_KEY')
        if loaded_api_key:
            print("Test: Loaded API key from GOOGLE_API_KEY environment variable.")
        else:
            print("Test: API key not found in config or environment variable GOOGLE_API_KEY.")

    if loaded_api_key:
        analyzer = ContextAnalyzer(api_key=loaded_api_key)
        if analyzer.model:
            print("\n--- Test 1: Elaboration with basic snippet ---")
            dummy_snippet = (
                "   7:  # Assuming file_scanner.py and mcp_search.py are in the same directory or PYTHONPATH\n"
                "   8: from file_scanner import >>> FileScanner <<< #, DEFAULT_EXCLUDED_DIRS, DEFAULT_EXCLUDED_FILES # Might need these if modifying defaults\n"
                "   9:  from mcp_search import Searcher"
            )
            elaboration1 = analyzer.elaborate_on_match("mcp_searcher.py", 8, dummy_snippet)
            print("Elaboration Result 1:")
            print(elaboration1)

            print("\n--- Test 2: Elaboration with snippet and full_file_content (simulated) ---")
            simulated_full_content = (
                "#!/usr/bin/env python3\n"
                "import argparse\n"
                "import os\n"
                "import sys\n"
                "# Line 5\n"
                "from file_scanner import FileScanner # Line 6 - The actual match\n"
                "from mcp_search import Searcher # Line 7\n"
                "# Line 8\n"
                "# Line 9\n"
                "# Line 10\n"
                "# Line 11\n"
                "# Line 12\n"
                "# Line 13\n"
                "# Line 14\n"
                "# Line 15\n"
                "def main_function_example():\n"
                "    pass\n"
                "# ... many more lines ...\n"
                "# Line 25\n"
                "# Line 26\n"
                "# Line 27\n"
                "# Line 28\n"
                "# Line 29\n"
                "# Line 30\n"
            )
            elaboration2 = analyzer.elaborate_on_match(
                "test_file.py", 
                6, # Match is on Line 6 of simulated_full_content
                "from file_scanner import >>> FileScanner <<<", 
                full_file_content=simulated_full_content,
                context_window_lines=3 # Keep context small for this test
            )
            print("Elaboration Result 2:")
            print(elaboration2)

            print("\n--- Test 3: Model not initialized (no API key) ---")
            analyzer_no_key = ContextAnalyzer(api_key=None) # Force no key
            # Temporarily clear env var if it exists to ensure test condition
            original_env_key = os.environ.pop('GOOGLE_API_KEY', None)
            if config: # And prevent loading from config for this specific test instance
                original_config_load = config.load_api_key
                config.load_api_key = lambda: None
            
            analyzer_no_key_actually = ContextAnalyzer(api_key=None)
            elaboration3 = analyzer_no_key_actually.elaborate_on_match("test.py", 1, "snippet")
            print(f"Elaboration Result 3 (no API key): {elaboration3}")

            # Restore environment and config for other tests or subsequent runs
            if original_env_key:
                os.environ['GOOGLE_API_KEY'] = original_env_key
            if config:
                config.load_api_key = original_config_load
        else:
            print("Test: ContextAnalyzer model not initialized, skipping elaboration tests.")
    else:
        print("Test: API key not available, skipping direct execution tests for ContextAnalyzer.") 