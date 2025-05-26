import json
import sys

class OutputGenerator:
    """Generates formatted output for search results and elaborations."""

    def __init__(self, output_format='console'):
        """
        Initializes the OutputGenerator.

        Args:
            output_format (str): The desired output format ('console', 'json', 'md').
                                 Defaults to 'console'.
        """
        self.output_format = output_format.lower()

    def generate_output(self, processed_results):
        """
        Generates output string based on the specified format.

        Args:
            processed_results (list): A list of dictionaries, where each dictionary 
                                      represents a match and its optional elaboration.
                                      Example item: {
                                          'file_path': 'path/to/file.py',
                                          'line_number': 10,
                                          'snippet': '...',
                                          'match_text': '...',
                                          'elaboration': 'LLM elaboration..._optional'
                                      }

        Returns:
            str: The formatted output string.
        """
        if self.output_format == 'json':
            return self._format_json(processed_results)
        elif self.output_format == 'md' or self.output_format == 'markdown':
            return self._format_markdown(processed_results)
        elif self.output_format == 'console':
            return self._format_console(processed_results)
        else:
            print(f"Warning: Unknown output format '{self.output_format}'. Defaulting to console.", file=sys.stderr)
            return self._format_console(processed_results)

    def _format_console(self, processed_results):
        """
        Formats results for console output.
        """
        output_lines = []
        if not processed_results:
            output_lines.append("No matches found.")
            return "\n".join(output_lines)

        for result in processed_results:
            output_lines.append(f"\nMatch in: {result['file_path']}")
            output_lines.append(f"Line {result['line_number']}:")
            output_lines.append(result['snippet'])

            if result.get('elaboration'):
                output_lines.append("\n    ✨ Elaborating...\n")
                elaboration_text = result['elaboration']
                for el_line in elaboration_text.split('\n'):
                    output_lines.append(f"    💡 {el_line}")
                output_lines.append("    --------------------")
        
        output_lines.append(f"\nFound {len(processed_results)} match(es) in total.")
        return "\n".join(output_lines)

    def _format_json(self, processed_results):
        """
        Formats results as a JSON string.
        """
        return json.dumps(processed_results, indent=4)

    def _format_markdown(self, processed_results):
        """
        Formats results as a Markdown string.
        """
        output_lines = []
        if not processed_results:
            output_lines.append("No matches found.")
            return "\n".join(output_lines)
        
        output_lines.append("# Code Search Results")
        output_lines.append(f"\nFound {len(processed_results)} match(es) in total.")

        current_file = None
        for result in processed_results:
            if result['file_path'] != current_file:
                if current_file is not None:
                    output_lines.append("\n---")
                current_file = result['file_path']
                output_lines.append(f"\n## File: `{current_file}`")
            
            output_lines.append(f"\n### Match at Line {result['line_number']}")
            output_lines.append("```text")
            output_lines.append(result['snippet'])
            output_lines.append("```")

            if result.get('elaboration'):
                output_lines.append("\n**Elaboration:**")
                output_lines.append("> " + result['elaboration'].replace('\n', '\n> '))
        
        return "\n".join(output_lines)

if __name__ == '__main__':
    print("OutputGenerator module direct execution (for testing during dev)")

    sample_results_no_elab = [
        {
            'file_path': 'project/module_a/file1.py',
            'line_number': 42,
            'match_text': 'important_function',
            'snippet': '  41: def another_func():\n  42:     call_ >>> important_function <<< (param1)\n  43:     return True'
        },
        {
            'file_path': 'project/module_a/file1.py',
            'line_number': 101,
            'match_text': 'important_function',
            'snippet': ' 100: class TestImportant:\n 101:     self.check = >>> important_function <<< _setup()\n 102:         pass'
        },
        {
            'file_path': 'project/module_b/file2.py',
            'line_number': 15,
            'match_text': 'important_function',
            'snippet': '  14: # TODO: Refactor important_function call\n  15:     result = old_ >>> important_function <<< (data)\n  16:     # Process result'
        }
    ]

    sample_results_with_elab = [
        {
            'file_path': 'project/module_c/file3.py',
            'line_number': 88,
            'match_text': 'critical_logic',
            'snippet': '  87: if status is True:\n  88:     >>> critical_logic <<< (payload)\n  89:     logger.info("Critical logic executed")',
            'elaboration': 'This line executes critical_logic with the payload if status is true.\nConsider adding robust error handling around this call.'
        },
        {
            'file_path': 'project/module_c/file3.py',
            'line_number': 95,
            'match_text': 'critical_logic',
            'snippet': '  94: # Fallback critical_logic path\n  95:     fallback_ >>> critical_logic <<< (payload)\n  96:     logger.warn("Fallback logic executed")',
            'elaboration': 'This is a fallback execution of critical_logic.\nEnsure monitoring is in place for frequent fallback scenarios.'
        }
    ]

    print("\n--- Testing Console Output (No Elaboration) ---")
    gen_console_no_elab = OutputGenerator(output_format='console')
    console_output_no_elab = gen_console_no_elab.generate_output(sample_results_no_elab)
    print(console_output_no_elab)

    print("\n--- Testing Console Output (With Elaboration) ---")
    gen_console_with_elab = OutputGenerator(output_format='console')
    console_output_with_elab = gen_console_with_elab.generate_output(sample_results_with_elab)
    print(console_output_with_elab)

    print("\n--- Testing JSON Output (With Elaboration) ---")
    gen_json = OutputGenerator(output_format='json')
    json_output = gen_json.generate_output(sample_results_with_elab)
    print(json_output)

    print("\n--- Testing Markdown Output (With Elaboration) ---")
    gen_md = OutputGenerator(output_format='md')
    md_output = gen_md.generate_output(sample_results_with_elab)
    print(md_output)
    
    print("\n--- Testing Console Output (Empty Results) ---")
    console_output_empty = gen_console_no_elab.generate_output([])
    print(console_output_empty)

    print("\n--- Testing JSON Output (Empty Results) ---")
    json_output_empty = gen_json.generate_output([])
    print(json_output_empty)

    print("\n--- Testing Markdown Output (Empty Results) ---")
    md_output_empty = gen_md.generate_output([])
    print(md_output_empty) 