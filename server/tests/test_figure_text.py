import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from utils.config import Config
from utils.figure_text import figure_text_command, install_figure_protection

try:
    from babeldoc.format.pdf.document_il import il_version_1 as il
    from babeldoc.format.pdf.document_il.midend import paragraph_finder
    from babeldoc.format.pdf.document_il.utils.layout_helper import build_layout_index
except ImportError:
    il = None


class FigureOptionTest(unittest.TestCase):
    def test_request_boolean_and_legacy_default(self):
        for value, expected in [(None, False), (False, False), ('false', False), ('true', True), (True, True)]:
            request = {'engine': 'pdf2zh_next'}
            if value is not None:
                request['skipFigureText'] = value
            with redirect_stdout(StringIO()):
                config = Config(request)
            self.assertIs(config.skip_figure_text, expected)

    def test_module_invocation_keeps_engine_python_and_arguments(self):
        command = [sys.executable, '-u', '-m', 'pdf2zh_next', 'space name.pdf', '--no-dual']
        wrapped = figure_text_command(command)
        self.assertEqual(wrapped[0], sys.executable)
        self.assertEqual(wrapped[3:], command[4:])
        self.assertTrue(Path(wrapped[2]).is_file())

    def test_executor_wraps_only_enabled_requests_after_environment_resolution(self):
        from utils import execute

        resolved = [sys.executable, '-u', '-m', 'pdf2zh_next', 'input.pdf']
        manager = SimpleNamespace(get_command_and_env=lambda cmd: (resolved, {}))
        for enabled in (False, True):
            with (
                patch.object(execute, 'prepare_deepseek_runtime_command', side_effect=lambda cmd, env: cmd),
                patch.object(execute, '_execute_with_pty') as posix,
                patch.object(execute, '_execute_with_inherit') as windows,
                redirect_stdout(StringIO()),
            ):
                execute.execute_with_progress(
                    ['pdf2zh_next', 'input.pdf'], None,
                    SimpleNamespace(enable_venv=True), manager,
                    skip_figure_text=enabled,
                )
                command = (posix if posix.called else windows).call_args.args[0]
            if enabled:
                self.assertEqual(command[0], sys.executable)
                self.assertTrue(command[2].endswith('figure_text.py'))
                self.assertEqual(command[3:], ['input.pdf'])
            else:
                self.assertEqual(command, resolved)

    def test_unresolvable_interpreter_fails_instead_of_ignoring_option(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                figure_text_command([str(Path(folder) / 'missing'), 'input.pdf'])


@unittest.skipIf(il is None, 'Install BabelDOC to run paragraph integration tests')
class FigureParagraphTest(unittest.TestCase):
    def page(self, label='figure', text_label='plain text', overlap=True):
        box = il.Box(x=10, y=10, x2=20, y2=20)
        char = il.PdfCharacter(
            box=box, visual_bbox=il.VisualBbox(box=box), char_unicode='A',
            pdf_style=il.PdfStyle(font_id='f1', font_size=10),
        )
        region = il.Box(x=0, y=0, x2=30, y2=30) if overlap else il.Box(x=50, y=50, x2=60, y2=60)
        return il.Page(pdf_character=[char], page_layout=[
            il.PageLayout(id=1, box=region, class_name=label),
            il.PageLayout(id=2, box=box, class_name=text_label),
        ])

    def group(self, page, enabled):
        finder = object.__new__(paragraph_finder.ParagraphFinder)
        finder.update_paragraph_data = lambda paragraph: None
        finder.is_isolated_formula = lambda char: False
        with patch.object(paragraph_finder, 'get_character_layout', paragraph_finder.get_character_layout):
            if enabled:
                install_figure_protection()
            index, mapping = build_layout_index(page)
            return finder._group_characters_into_paragraphs(page, index, mapping)

    def test_figure_characters_stay_verbatim_outside_translation_paragraphs(self):
        for label in ['figure', 'image', 'figure_text', 'figure_text_hybrid']:
            with self.subTest(label=label):
                page = self.page(label)
                char = page.pdf_character[0]
                self.assertEqual(self.group(page, True), [])
                self.assertIs(page.pdf_character[0], char)
                self.assertEqual(char.char_unicode, 'A')

    def test_disabled_preserves_original_translation_behavior(self):
        page = self.page()
        self.assertEqual(len(self.group(page, False)), 1)
        self.assertEqual(page.pdf_character, [])

    def test_captions_tables_and_body_remain_translatable(self):
        for page in [self.page(text_label='figure_caption'), self.page(label='table'), self.page(overlap=False)]:
            self.assertEqual(len(self.group(page, True)), 1)
            self.assertEqual(page.pdf_character, [])

    def test_grazing_figure_boundary_does_not_suppress_body(self):
        page = self.page()
        page.page_layout[0].box.x2 = 11
        self.assertEqual(len(self.group(page, True)), 1)


if __name__ == '__main__':
    unittest.main()
