import json
import sys
import os # For API key loading, and reading full file content
from mcp_elaborate import ContextAnalyzer

def elaborate_finding(report_path, finding_id, api_key=None, context_window_lines=10):
    """
    Loads a JSON search report, locates a specific finding by its index (finding_id),
    reads the source file for broader context, and uses ContextAnalyzer to elaborate.

    Args:
        report_path (str): Path to the JSON search report file.
        finding_id (int or str): The 0-based index of the finding or a string to be converted to int.
        api_key (str, optional): Google API key for ContextAnalyzer. Defaults to None (analyzer will try other methods).
        context_window_lines (int, optional): Number of lines for broader context. Defaults to 10.

    Returns:
        str: The elaboration text or an error message string.
    """
    try:
        with open(report_path, 'r', encoding='utf-8') as f:
            report_data = json.load(f)
    except FileNotFoundError:
        return f"Error: Report file not found at '{report_path}'."
    except json.JSONDecodeError:
        return f"Error: Could not decode JSON from report file '{report_path}'."
    except Exception as e:
        return f"Error: Could not read report file '{report_path}': {e}"

    if not isinstance(report_data, list):
        return "Error: Report data is not in the expected list format."

    try:
        finding_index = int(finding_id)
    except ValueError:
        return f"Error: Finding ID '{finding_id}' must be an integer index."

    if not (0 <= finding_index < len(report_data)):
        return f"Error: Finding ID {finding_index} is out of range for the report (0 to {len(report_data) - 1})."

    found_finding = report_data[finding_index]
    required_keys = ['file_path', 'line_number', 'snippet', 'match_text']
    if not all(key in found_finding for key in required_keys):
        return f"Error: Finding at index {finding_index} has an invalid structure. Missing one of {required_keys}."

    # Subtask 9.2: Read Source File Context
    source_file_path = found_finding['file_path']
    full_file_content = None
    try:
        # Attempt to make source_file_path absolute if it's relative to the report's dir
        if not os.path.isabs(source_file_path) and os.path.exists(os.path.dirname(report_path)):
            possible_abs_path = os.path.join(os.path.dirname(report_path), source_file_path)
            if os.path.exists(possible_abs_path):
                source_file_path = possible_abs_path
            # If still not found, it might be relative to CWD, or an absolute path that's incorrect

        with open(source_file_path, 'r', encoding='utf-8') as sf:
            full_file_content = sf.read()
    except FileNotFoundError:
        print(f"Warning: Source file '{source_file_path}' for finding {finding_index} not found. Proceeding with snippet only.", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Could not read source file '{source_file_path}': {e}. Proceeding with snippet only.", file=sys.stderr)

    # Subtasks 9.3, 9.4, 9.5: Use ContextAnalyzer
    try:
        analyzer = ContextAnalyzer(api_key=api_key)
        if not analyzer.model: # Check if model initialization failed (e.g. no API key at all)
            # The ContextAnalyzer __init__ already prints a detailed error to stderr
            return "Error: ContextAnalyzer model could not be initialized. Cannot elaborate."

        elaboration = analyzer.elaborate_on_match(
            file_path=found_finding['file_path'],
            line_number=found_finding['line_number'],
            snippet=found_finding['snippet'],
            full_file_content=full_file_content,
            context_window_lines=context_window_lines
        )
        return elaboration
    except Exception as e:
        # This catches unexpected errors during ContextAnalyzer instantiation or its elaborate_on_match call
        return f"Error during elaboration process: {e}"


if __name__ == '__main__':
    print("Report Elaborator module direct execution (for testing during dev)")

    # Create a dummy sample_report.json for testing
    # Assume this script is run from the project root for pathing to work easily
    # For file_path in report, use paths that might exist relative to project root if possible
    # For this dummy test, we'll create dummy files too.

    test_dir = "temp_report_elaborator_test_files"
    os.makedirs(test_dir, exist_ok=True)

    dummy_file1_path_rel = os.path.join(test_dir, "dummy_module_a", "dummy_file1.py")
    dummy_file2_path_rel = os.path.join(test_dir, "dummy_module_b", "dummy_file2.py")
    
    os.makedirs(os.path.dirname(dummy_file1_path_rel), exist_ok=True)
    os.makedirs(os.path.dirname(dummy_file2_path_rel), exist_ok=True)

    with open(dummy_file1_path_rel, 'w', encoding='utf-8') as f:
        f.write("line1 in dummy_file1\n" \
                  "def another_func():\n" \
                  "    call_ important_function (param1)\n" \
                  "    return True\n" \
                  "line5 in dummy_file1")

    with open(dummy_file2_path_rel, 'w', encoding='utf-8') as f:
        f.write("line1 in dummy_file2\n" \
                  "# TODO: Refactor important_function call\n" \
                  "    result = old_ important_function (data)\n" \
                  "    # Process result\n" \
                  "line5 in dummy_file2")

    sample_results_for_report = [
        {
            'file_path': dummy_file1_path_rel, # Relative path
            'line_number': 3, # Corresponds to "    call_ important_function (param1)"
            'match_text': 'important_function',
            'snippet': '  2: def another_func():\n  3:     call_ >>> important_function <<< (param1)\n  4:     return True',
        },
        {
            'file_path': dummy_file2_path_rel, # Relative path
            'line_number': 3, # Corresponds to "    result = old_ important_function (data)"
            'match_text': 'important_function',
            'snippet': '  2: # TODO: Refactor important_function call\n  3:     result = old_ >>> important_function <<< (data)\n  4:     # Process result'
        }
    ]
    sample_report_path = os.path.join(test_dir, "sample_report_for_elab.json")
    with open(sample_report_path, 'w', encoding='utf-8') as f_report:
        json.dump(sample_results_for_report, f_report, indent=4)
    
    print(f"Created '{sample_report_path}' and dummy source files in '{test_dir}' for testing.")

    # IMPORTANT: For these tests to call the actual Gemini API, 
    # you need a valid GOOGLE_API_KEY in your environment or .env file that config.py can read.
    # Otherwise, ContextAnalyzer will fail to initialize its model.
    print("\nNOTE: Ensure GOOGLE_API_KEY is available for ContextAnalyzer to work.")
    retrieved_api_key = os.getenv('GOOGLE_API_KEY') # Simple check for this test script
    if not retrieved_api_key:
        try:
            import config as app_config
            retrieved_api_key = app_config.load_api_key()
        except ImportError:
            pass # config might not be importable if script is moved
        except AttributeError: 
            pass # config.load_api_key might not exist if config is a mock

    if not retrieved_api_key:
        print("Warning: GOOGLE_API_KEY not found. Elaboration will likely fail or return error messages.")

    print("\n--- Test 1: Elaborate finding 0 (valid) ---")
    # Pass the API key if found, otherwise analyzer will try to find it
    result1 = elaborate_finding(sample_report_path, 0, api_key=retrieved_api_key)
    print(f"Elaboration Result 1:\n{result1}")

    print("\n--- Test 2: Elaborate finding 1 (valid, different file) ---")
    result2 = elaborate_finding(sample_report_path, "1", api_key=retrieved_api_key) # Test string ID
    print(f"Elaboration Result 2:\n{result2}")

    print("\n--- Test 3: Elaborate finding 2 (out of range) ---")
    result3 = elaborate_finding(sample_report_path, 2, api_key=retrieved_api_key)
    print(f"Result 3: {result3}")
    
    print("\n--- Test 4: Elaborate finding 'abc' (invalid ID type) ---")
    result4 = elaborate_finding(sample_report_path, "abc", api_key=retrieved_api_key)
    print(f"Result 4: {result4}")

    print("\n--- Test 5: Report file not found ---")
    result5 = elaborate_finding("non_existent_report.json", 0, api_key=retrieved_api_key)
    print(f"Result 5: {result5}")

    print("\n--- Test 6: Finding with invalid structure (missing 'snippet') ---")
    faulty_report_data = [
        {
            'file_path': dummy_file1_path_rel,
            'line_number': 1,
            'match_text': 'line1',
            # 'snippet': 'missing snippet' # Intentionally missing
        }
    ]
    faulty_report_path = os.path.join(test_dir, "faulty_report.json")
    with open(faulty_report_path, 'w', encoding='utf-8') as fr:
        json.dump(faulty_report_data, fr)
    result6 = elaborate_finding(faulty_report_path, 0, api_key=retrieved_api_key)
    print(f"Result 6: {result6}")

    print("\n--- Test 7: Source file for finding not found ---")
    report_with_bad_source_path = [
        {
            'file_path': os.path.join(test_dir, "non_existent_source.py"),
            'line_number': 1,
            'match_text': 'test',
            'snippet': '>>>test<<<'
        }
    ]
    bad_source_report_path = os.path.join(test_dir, "bad_source_report.json")
    with open(bad_source_report_path, 'w', encoding='utf-8') as bsr:
        json.dump(report_with_bad_source_path, bsr)
    result7 = elaborate_finding(bad_source_report_path, 0, api_key=retrieved_api_key)
    print(f"Elaboration Result 7 (expect warning in console, then elaboration based on snippet only):\n{result7}")

    # Clean up the dummy files and directory
    import shutil
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
        print(f"\nCleaned up test directory '{test_dir}'.") 