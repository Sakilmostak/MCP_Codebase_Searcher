# Module for mcp_elaborate command logic

import google.generativeai as genai
import os
import sys
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from google.generativeai.types import BlockedPromptException # Explicit import for clarity
import google.api_core.exceptions # For more specific API error handling

# Assuming config.py is in the same directory or PYTHONPATH
try:
    import config
except ImportError:
    # This might happen if running mcp_elaborate.py directly without the project root in PYTHONPATH
    # For direct execution or testing, ensure .env is locatable or API key is otherwise available.
    print("Warning: Could not import config.py. API key loading might rely on direct environment variables.", file=sys.stderr)
    config = None # Allow script to continue if API key is passed directly or via env

class ContextAnalyzer:
    """
    Uses a Generative AI model to elaborate on code snippets and provide context.
    """
    def __init__(self, api_key=None, model_name='gemini-1.5-flash-latest'):
        """
        Initializes the ContextAnalyzer.

        Args:
            api_key (str, optional): The Google API key. If None, attempts to load from config.
            model_name (str, optional): The name of the Gemini model to use. Defaults to 'gemini-1.5-flash-latest'.
        """
        self.model_name = model_name
        self.api_key = api_key
        self.generation_config = genai.types.GenerationConfig(
            # temperature=0.7, # Example: Adjust creativity
            # top_p=0.9,       # Example: Adjust token sampling
            # top_k=40,        # Example: Adjust token sampling
            # max_output_tokens=1024 # Example: Limit response length
        )
        self.safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            }
        ]

        if not self.api_key: # If api_key was not directly passed to __init__
            loaded_from_config = False
            if config: # Check if the config module was successfully imported
                try:
                    self.api_key = config.load_api_key()
                    if self.api_key:
                        loaded_from_config = True
                        # print("Info: API key loaded from config.", file=sys.stderr) # Optional: for debugging
                    else:
                        # This means load_api_key() was called but returned None/empty
                        print("Warning: API key loaded from config is empty.", file=sys.stderr)
                except Exception as e:
                    print(f"Warning: Could not load API key from config: {e}", file=sys.stderr)
            
            # If not loaded from config (either config module missing, load_api_key failed, or returned empty)
            # then try to load from environment variable.
            if not loaded_from_config and not self.api_key:
                 self.api_key = os.getenv('GOOGLE_API_KEY')
                 if self.api_key:
                    # print("Info: API key loaded from GOOGLE_API_KEY environment variable.", file=sys.stderr) # Optional
                    pass
                 else:
                    print("Warning: API key not provided via config and could not be loaded from GOOGLE_API_KEY environment variable.", file=sys.stderr)
        
        if not self.api_key:
            self.model = None
            print("Error: ContextAnalyzer initialized without an API key. Elaboration will not function.", file=sys.stderr)
            return

        try:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config=self.generation_config,
                safety_settings=self.safety_settings
            )
            # Test with a simple generation to catch auth/permission issues early if GOOGLE_API_KEY is present
            # but invalid, or if the model name is incorrect.
            # self.model.generate_content("test") # This can be verbose during normal init
            print(f"ContextAnalyzer initialized successfully with model: {self.model_name}")
        except Exception as e:
            self.model = None
            print(f"Error initializing Google Generative AI model ({self.model_name}): {e}", file=sys.stderr)

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
                        # Highlight the original match line or use the provided snippet's line
                        # For simplicity, we'll just mark it clearly.
                        # The snippet already contains the >>> <<< markers for the exact match.
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
                # Fallback to just using the snippet if broader context processing fails
                context_for_prompt = snippet 

        # Corrected multiline f-string for prompt
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
            # print(f"DEBUG: Prompt sent to Gemini: --------\n{{prompt}}\n----------") # DEBUG
            response = self.model.generate_content(
                prompt,
                # stream=True # Consider if streaming makes sense here for long elaborations
            )
            # print(f"DEBUG: Gemini Raw Response: {response}") # DEBUG

            # Check for blocked prompt via prompt_feedback
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                reason = response.prompt_feedback.block_reason.name
                # print(f"Warning: Elaboration for {file_path}:{line_number} blocked by API. Reason: {reason}", file=sys.stderr)
                return f"[Elaboration blocked by API. Reason: {reason}]"
            
            # Accessing parts and text
            if response.parts:
                elaboration_text = "".join(part.text for part in response.parts if hasattr(part, 'text'))
                # print(f"DEBUG: Extracted elaboration text: {{elaboration_text}}") # DEBUG
                if not elaboration_text.strip():
                    # print(f"Warning: Received empty elaboration from API for {{file_path}}:{{line_number}}.")
                    return "[Elaboration from API was empty or unparsable]"
                return elaboration_text
            else:
                # This case might occur if the response structure is unexpected or truly empty
                # print(f"Warning: No parts found in API response for {{file_path}}:{{line_number}}. Response: {{response}}")
                return "[No content returned from API for elaboration]"

        except BlockedPromptException as e:
            # print(f"Warning: Elaboration for {{file_path}}:{{line_number}} was explicitly blocked. {{e}}", file=sys.stderr)
            return f"[Elaboration blocked by API: {e}]"
        except google.api_core.exceptions.GoogleAPIError as e:
            error_message = f"API error during elaboration for {file_path}:{line_number}: {type(e).__name__} - {e}"
            # print(f"Warning: {{error_message}}", file=sys.stderr)
            return f"[{error_message}]"
        except Exception as e:
            # Catch any other unexpected errors during generation
            error_message = f"Unexpected error during elaboration for {file_path}:{line_number}: {type(e).__name__} - {e}"
            # print(f"Warning: {{error_message}}", file=sys.stderr)
            return f"[{error_message}]"

if __name__ == '__main__':
    print("MCP Elaborate module direct execution (for testing during dev)")
    
    loaded_api_key = None
    if config:
        try:
            loaded_api_key = config.load_api_key()
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
            # Simulate a larger file content for context extraction
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
                "# Line 16\n"
                "def main():\n"
                "    pass # Line 18\n"
                "# Line 19\n"
                "# Line 20\n"
                "# Line 21\n"
                "# Line 22\n"
                "# Line 23\n"
                "# Line 24\n"
                "# Line 25\n"
            )
            # The snippet for this match would be generated by Searcher. For testing, let's assume:
            test_snippet_for_full_context = (
                "   5: # Line 5\n"
                "   6: from file_scanner import >>> FileScanner <<< # Line 6 - The actual match\n"
                "   7: from mcp_search import Searcher # Line 7"
            )
            # The match is on line 6 of simulated_full_content (1-based)
            elaboration2 = analyzer.elaborate_on_match(
                "dummy_module.py", 
                6, 
                test_snippet_for_full_context, 
                full_file_content=simulated_full_content,
                context_window_lines=3 # Show 3 lines before/after in broader context
            )
            print("Elaboration Result 2:")
            print(elaboration2)

        else:
            print("\nTest: ContextAnalyzer model could not be initialized, even with an API key attempt.")
    else:
        print("\nTest: Skipping ContextAnalyzer instantiation as no API key was available.")
        print("\nTest: Attempting to instantiate ContextAnalyzer without API key...")
        analyzer_no_key = ContextAnalyzer()
        print(f"Test: analyzer_no_key.model is {analyzer_no_key.model}")

def elaborate_finding():
    pass 