import os
import tempfile
import shutil
import mock

from general_tools.file_utils import read_file, write_file, unzip, add_contents_to_zip
from tests.linter_tests.linter_unittest import LinterTestCase
from linters.tw_linter import TwLinter


class TestTwLinter(LinterTestCase):

    resources_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'resources')

    def setUp(self):
        """Runs before each test."""
        self.temp_dir = tempfile.mkdtemp(prefix='tX_test_tw_')
        self.commit_data = {
            'repository': {
                'name': 'en_tw',
                'owner': {
                    'username': 'Door43'
                }
            }
        }

    def tearDown(self):
        """Runs after each test."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # Removed coz of extra parameters Nov 2019 RJH
    # @mock.patch('linters.markdown_linter.MarkdownLinter.invoke_markdown_linter')
    # def test_lint(self, mock_invoke_markdown_linter):
    #     # given
    #     mock_invoke_markdown_linter.return_value = {}  # Don't care about markdown linting here, just specific tw linting
    #     expected_warnings_count = 18 + 25
    #     zip_file = os.path.join(self.resources_dir, 'tw_linter', 'en_tw.zip')
    #     linter = TwLinter(repo_subject='Translation_Words', source_file=zip_file, commit_data=self.commit_data)

    #     # when
    #     linter.run()

    #     # then
    #     self.verify_results_warnings_count(expected_warnings_count, linter)

    # Removed coz of extra parameters Nov 2019 RJH
    # @mock.patch('linters.markdown_linter.MarkdownLinter.invoke_markdown_linter')
    # def test_lint_broken_links(self, mock_invoke_markdown_linter):
    #     # given
    #     mock_invoke_markdown_linter.return_value = {}  # Don't care about markdown linting here, just specific tw linting
    #     expected_warnings_count = 18 + 4 + 25
    #     zip_file = os.path.join(self.resources_dir, 'tw_linter', 'en_tw.zip')
    #     out_dir = self.unzip_resource(zip_file)
    #     self.replace_text(out_dir, 'en_tw/bible/names/aaron.md', '(../names/moses.md)', '(../moses.md)')
    #     self.replace_text(out_dir, 'en_tw/bible/names/aaron.md', '(../kt/israel.md)', '(./kt/israel.md)')
    #     self.replace_text(out_dir, 'en_tw/bible/other/alarm.md', '(../names/jehoshaphat.md)', '(../kt/jehoshaphat.md)')
    #     self.replace_text(out_dir, 'en_tw/bible/kt/anoint.md', '(../kt/consecrate.md)', '(..//consecrate.md)')
    #     new_zip = self.create_new_zip(out_dir)
    #     linter = TwLinter(repo_subject='Translation_Words', source_file=new_zip, commit_data=self.commit_data)

    #     # when
    #     linter.run()

    #     # then
    #     self.verify_results_warnings_count(expected_warnings_count, linter)

    #
    # helpers
    #

    # def verify_results(self, expected_warnings, linter):
    #     self.assertEqual(len(linter.log.warnings) > 0, expected_warnings)

    def verify_results_warnings_count(self, expected_warnings_count, linter):
        # print( "warnings3,", len(linter.log.warnings), linter.log.warnings)
        self.assertEqual(len(linter.log.warnings), expected_warnings_count)

    def replace_text(self, out_dir, file_name, match, replace):
        file_path = os.path.join(out_dir, file_name)
        text = read_file(file_path)
        new_text = text.replace(match, replace)
        self.assertNotEqual(text, new_text)
        write_file(file_path, new_text)

    def create_new_zip(self, out_dir):
        new_zip = tempfile.NamedTemporaryFile(prefix='linter', suffix='.zip', dir=self.temp_dir, delete=False).name
        add_contents_to_zip(new_zip, out_dir)
        return new_zip

    def prepend_text(self, out_dir, file_name, prefix):
        file_path = os.path.join(out_dir, file_name)
        text = read_file(file_path)
        new_text = prefix + text
        write_file(file_path, new_text)

    def unzip_resource(self, zip_name):
        zip_file = os.path.join(self.resources_dir, zip_name)
        out_dir = tempfile.mkdtemp(dir=self.temp_dir, prefix='linter_test_')
        unzip(zip_file, out_dir)
        return out_dir
