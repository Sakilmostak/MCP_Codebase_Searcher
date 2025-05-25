import unittest
import json
from unittest.mock import patch

# Add project root to sys.path to allow direct import of output_generator
import os
import sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '.'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from output_generator import OutputGenerator

class TestOutputGenerator(unittest.TestCase):

    def setUp(self):
        """Set up sample data for tests."""
        self.sample_results_no_elab = [
            {
                'file_path': 'project/file1.py',
                'line_number': 10,
                'match_text': 'some_match',
                'snippet': 'Line 9\nLine >>> 10 <<<: some_match\nLine 11',
                'elaboration': None
            },
            {
                'file_path': 'project/file2.py',
                'line_number': 25,
                'match_text': 'another_match',
                'snippet': 'Context before\nLine >>> 25 <<<: another_match here\nContext after',
                'elaboration': None
            }
        ]

        self.sample_results_with_elab = [
            {
                'file_path': 'project/file1.py',
                'line_number': 10,
                'match_text': 'some_match',
                'snippet': 'Line 9\nLine >>> 10 <<<: some_match\nLine 11',
                'elaboration': 'This is a detailed elaboration for the first match.\nIt can span multiple lines.'
            },
            {
                'file_path': 'project/file2.py',
                'line_number': 25,
                'match_text': 'another_match',
                'snippet': 'Context before\nLine >>> 25 <<<: another_match here\nContext after',
                'elaboration': 'Elaboration for the second match.'
            }
        ]
        self.empty_results = []

    def test_initialization(self):
        """Test OutputGenerator initialization with different formats."""
        gen_console = OutputGenerator('console')
        self.assertEqual(gen_console.output_format, 'console')
        gen_json = OutputGenerator('json')
        self.assertEqual(gen_json.output_format, 'json')
        gen_md = OutputGenerator('md')
        self.assertEqual(gen_md.output_format, 'md')
        gen_default = OutputGenerator()
        self.assertEqual(gen_default.output_format, 'console')
        gen_upper = OutputGenerator('JSON')
        self.assertEqual(gen_upper.output_format, 'json')
        gen_unknown = OutputGenerator('xml')
        self.assertEqual(gen_unknown.output_format, 'xml')

    # Test Console Output
    def test_format_console_empty(self):
        gen = OutputGenerator('console')
        output = gen.generate_output(self.empty_results)
        self.assertIn("No matches found.", output)

    def test_format_console_no_elab(self):
        gen = OutputGenerator('console')
        output = gen.generate_output(self.sample_results_no_elab)
        self.assertIn("Match in: project/file1.py", output)
        self.assertIn("Line 10:", output)
        self.assertIn("Line >>> 10 <<<: some_match", output)
        self.assertIn("Match in: project/file2.py", output)
        self.assertIn("Line 25:", output)
        self.assertNotIn("✨ Elaborating", output)
        self.assertIn(f"Found {len(self.sample_results_no_elab)} match(es) in total.", output)

    def test_format_console_with_elab(self):
        gen = OutputGenerator('console')
        output = gen.generate_output(self.sample_results_with_elab)
        self.assertIn("Match in: project/file1.py", output)
        self.assertIn("✨ Elaborating...", output)
        self.assertIn("💡 This is a detailed elaboration", output)
        self.assertIn("💡 It can span multiple lines.", output)
        self.assertIn("💡 Elaboration for the second match.", output)
        self.assertIn(f"Found {len(self.sample_results_with_elab)} match(es) in total.", output)

    # Test JSON Output
    def test_format_json_empty(self):
        gen = OutputGenerator('json')
        output = gen.generate_output(self.empty_results)
        self.assertEqual(json.loads(output), [])

    def test_format_json_no_elab(self):
        gen = OutputGenerator('json')
        output = gen.generate_output(self.sample_results_no_elab)
        data = json.loads(output)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['file_path'], 'project/file1.py')
        self.assertIsNone(data[0]['elaboration'])
        self.assertEqual(data[1]['match_text'], 'another_match')

    def test_format_json_with_elab(self):
        gen = OutputGenerator('json')
        output = gen.generate_output(self.sample_results_with_elab)
        data = json.loads(output)
        self.assertEqual(len(data), 2)
        self.assertIn("detailed elaboration", data[0]['elaboration'])
        self.assertEqual(data[1]['elaboration'], 'Elaboration for the second match.')

    # Test Markdown Output
    def test_format_markdown_empty(self):
        gen = OutputGenerator('md')
        output = gen.generate_output(self.empty_results)
        self.assertIn("No matches found.", output)

    def test_format_markdown_no_elab(self):
        gen = OutputGenerator('md')
        output = gen.generate_output(self.sample_results_no_elab)
        self.assertIn("# Code Search Results", output)
        self.assertIn(f"Found {len(self.sample_results_no_elab)} match(es) in total.", output)
        self.assertIn("## File: `project/file1.py`", output)
        self.assertIn("### Match at Line 10", output)
        self.assertIn("```text\nLine 9\nLine >>> 10 <<<: some_match\nLine 11\n```", output)
        self.assertNotIn("**Elaboration:**", output)

    def test_format_markdown_with_elab(self):
        gen = OutputGenerator('md')
        output = gen.generate_output(self.sample_results_with_elab)
        self.assertIn("## File: `project/file1.py`", output)
        self.assertIn("**Elaboration:**", output)
        self.assertIn("> This is a detailed elaboration for the first match.", output)
        self.assertIn("> It can span multiple lines.", output)
        self.assertIn("> Elaboration for the second match.", output)

    def test_generate_output_dispatch(self):
        """Test that generate_output calls the correct internal method."""
        with patch.object(OutputGenerator, '_format_console', return_value="console_out") as mock_console,\
             patch.object(OutputGenerator, '_format_json', return_value="json_out") as mock_json, \
             patch.object(OutputGenerator, '_format_markdown', return_value="md_out") as mock_md:
            
            gen_c = OutputGenerator('console')
            self.assertEqual(gen_c.generate_output([]), "console_out")
            mock_console.assert_called_once_with([])

            gen_j = OutputGenerator('json')
            self.assertEqual(gen_j.generate_output([]), "json_out")
            mock_json.assert_called_once_with([])

            gen_m = OutputGenerator('md')
            self.assertEqual(gen_m.generate_output([]), "md_out")
            mock_md.assert_called_once_with([])
            
            # Test default to console for unknown
            gen_u = OutputGenerator('unknown')
            # Reset mock_console as it's called by gen_c and gen_u
            mock_console.reset_mock() 
            self.assertEqual(gen_u.generate_output([]), "console_out")
            mock_console.assert_called_once_with([])

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False) 