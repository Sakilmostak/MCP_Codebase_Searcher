import unittest
from unittest.mock import patch, mock_open, MagicMock
import os
import sys
import json
import io

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.output_generator import OutputGenerator

class TestOutputGenerator(unittest.TestCase):

    def setUp(self):
        self.sample_results_no_elab = [
            {
                'file_path': 'file1.txt',
                'line_number': 10,
                'match_text': 'hello world',
                'snippet': 'L9: ...\nL10: some >>>hello world<<< context\nL11: ...'
            },
            {
                'file_path': 'file2.py',
                'line_number': 5,
                'match_text': 'print("Hello")',
                'snippet': 'L4: def greet():\nL5:     >>>print("Hello")<<<\nL6: greet()'
            }
        ]
        self.sample_results_with_elab = [
            {
                'file_path': 'file1.txt',
                'line_number': 10,
                'match_text': 'hello world',
                'snippet': 'L9: ...\nL10: some >>>hello world<<< context\nL11: ...',
                'elaboration': 'This is a common greeting.'
            },
            {
                'file_path': 'file2.py',
                'line_number': 5,
                'match_text': 'print("Hello")',
                'snippet': 'L4: def greet():\nL5:     >>>print("Hello")<<<\nL6: greet()',
                'elaboration': 'This function prints a greeting.'
            }
        ]
        self.empty_results = []

    def test_init_known_formats(self):
        gen_console = OutputGenerator('console')
        self.assertEqual(gen_console.output_format, 'console')
        gen_json = OutputGenerator('json')
        self.assertEqual(gen_json.output_format, 'json')
        gen_md = OutputGenerator('md')
        self.assertEqual(gen_md.output_format, 'md')
        gen_markdown = OutputGenerator('markdown') # Alias for md
        self.assertEqual(gen_markdown.output_format, 'markdown')

    def test_init_unknown_format_is_stored_but_warns_on_generate(self):
        # Test that an unknown format is stored, but generate_output defaults to console and prints a warning
        unknown_format = "xml"
        generator = OutputGenerator(output_format=unknown_format)
        self.assertEqual(generator.output_format, unknown_format) # __init__ stores what it's given

        with patch('sys.stderr', new_callable=io.StringIO) as mock_stderr:
            # Calling generate_output should trigger the default to console and the warning
            output = generator.generate_output(self.empty_results) 
            self.assertEqual(output, "No matches found.") # Should be console output for empty
            self.assertIn(f"warning: unknown output format '{unknown_format}'. defaulting to console.", mock_stderr.getvalue().lower())

    def test_format_console_empty(self):
        generator = OutputGenerator('console')
        output = generator._format_console(self.empty_results)
        self.assertEqual(output, "No matches found.")

    def test_format_console_no_elaboration(self):
        generator = OutputGenerator('console')
        output = generator._format_console(self.sample_results_no_elab)
        self.assertIn("Match in: file1.txt", output)
        self.assertIn("Line 10", output)
        self.assertIn("L9: ...\nL10: some >>>hello world<<< context\nL11: ...", output)
        self.assertIn("Match in: file2.py", output)
        self.assertNotIn("Elaboration:", output)
        self.assertIn("Found 2 match(es) in total.", output)

    def test_format_console_with_elaboration(self):
        generator = OutputGenerator('console')
        output = generator._format_console(self.sample_results_with_elab)
        self.assertIn("Match in: file1.txt", output)
        self.assertIn("💡 This is a common greeting.", output)
        self.assertIn("Match in: file2.py", output)
        self.assertIn("💡 This function prints a greeting.", output)
        self.assertIn("Found 2 match(es) in total.", output)

    def test_format_json_empty(self):
        generator = OutputGenerator('json')
        output_str = generator._format_json(self.empty_results)
        output_json = json.loads(output_str)
        self.assertEqual(output_json, [])

    def test_format_json_no_elaboration(self):
        generator = OutputGenerator('json')
        output_str = generator._format_json(self.sample_results_no_elab)
        output_json = json.loads(output_str)
        self.assertEqual(len(output_json), 2)
        self.assertEqual(output_json[0]['file_path'], 'file1.txt')
        self.assertNotIn('elaboration', output_json[0])

    def test_format_json_with_elaboration(self):
        generator = OutputGenerator('json')
        output_str = generator._format_json(self.sample_results_with_elab)
        output_json = json.loads(output_str)
        self.assertEqual(len(output_json), 2)
        self.assertEqual(output_json[0]['elaboration'], 'This is a common greeting.')
        self.assertEqual(output_json[1]['elaboration'], 'This function prints a greeting.')

    def test_format_markdown_empty(self):
        generator = OutputGenerator('markdown')
        output = generator._format_markdown(self.empty_results)
        self.assertEqual(output, "No matches found.")

    def test_format_markdown_no_elaboration(self):
        generator = OutputGenerator('markdown')
        output = generator._format_markdown(self.sample_results_no_elab)
        self.assertIn("## File: `file1.txt`", output)
        self.assertIn("### Match at Line 10", output)
        self.assertIn("```text\nL9: ...\nL10: some >>>hello world<<< context\nL11: ...\n```", output)
        self.assertIn("## File: `file2.py`", output)
        self.assertNotIn("**Elaboration:**", output)
        self.assertIn("Found 2 match(es) in total.", output)

    def test_format_markdown_with_elaboration(self):
        generator = OutputGenerator('markdown')
        output = generator._format_markdown(self.sample_results_with_elab)
        self.assertIn("## File: `file1.txt`", output)
        self.assertIn("> This is a common greeting.", output)
        self.assertIn("## File: `file2.py`", output)
        self.assertIn("> This function prints a greeting.", output)
        self.assertIn("Found 2 match(es) in total.", output)

    def test_generate_output_dispatches_correctly(self):
        results = self.sample_results_no_elab
        
        with patch('sys.stderr', new_callable=io.StringIO):
            # Console (default for unknown)
            generator_console = OutputGenerator("unknown_format")
            with patch.object(generator_console, '_format_console') as mock_format_console:
                generator_console.generate_output(results)
                mock_format_console.assert_called_once_with(results)

            # JSON
            generator_json = OutputGenerator("json")
            with patch.object(generator_json, '_format_json') as mock_format_json:
                generator_json.generate_output(results)
                mock_format_json.assert_called_once_with(results)

            # Markdown
            generator_md = OutputGenerator("md")
            with patch.object(generator_md, '_format_markdown') as mock_format_markdown:
                generator_md.generate_output(results)
                mock_format_markdown.assert_called_once_with(results)

if __name__ == '__main__':
    unittest.main() 