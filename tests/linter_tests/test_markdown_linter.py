import os
import tempfile
import shutil
import mock
from tests.linter_tests.linter_unittest import LinterTestCase
from linters.markdown_linter import MarkdownLinter


class TestMarkdownLinter(LinterTestCase):

    resources_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'resources')

    def setUp(self):
        """Runs before each test."""
        self.temp_dir = tempfile.mkdtemp(prefix='tX_test_markdown_linter_')

    def tearDown(self):
        """Runs after each test."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # Removed coz of extra parameters Nov 2019 RJH
    # @mock.patch('linters.markdown_linter.MarkdownLinter.invoke_markdown_linter')
    # def test_lint(self, mock_invoke):
    #     mock_invoke.return_value = {
    #         "intro\\gl-strategy\\01.md": [],
    #         "intro\\finding-answers\\01.md": [
    #             {"lineNumber": 1,
    #              "ruleName": "MD041",
    #              "ruleAlias": "first-line-h1",
    #              "ruleDescription": "First line in file should be a top level header",
    #              "errorDetail": None,
    #              "errorContext": "Text on first line",
    #              "errorRange": None
    #              }
    #         ],
    #         "intro\\uw-intro\\01.md": [
    #             {"lineNumber": 1,
    #              "ruleName": "MD041",
    #              "ruleAlias": "first-line-h1",
    #              "ruleDescription": "First line in file should be a top level header",
    #              "errorDetail": None,
    #              "errorContext": "Text on first line",
    #              "errorRange": None
    #              },
    #             {
    #                 "lineNumber": 29,
    #                 "errorContext": None,
    #                 "ruleName": "MD007",
    #                 "ruleDescription": "Unordered list indentation",
    #                 "errorDetail": "Expected: 2; Actual: 4",
    #                 "ruleAlias": "ul-indent",
    #                 "errorRange": [
    #                     1,
    #                     6
    #                 ]
    #             }
    #         ],
    #     }

    #     commit_data = {
    #         "repository": {
    #             "owner": {
    #                 "username": "unfoldingWord"
    #             },
    #             "name": "en_ta"
    #         }
    #     }
    #     zip_file = os.path.join(self.resources_dir, 'ta_linter', 'en_ta.zip')
    #     identifier = 'test'
    #     linter = MarkdownLinter(repo_subject='Translation_Academy', source_file=zip_file, commit_data=commit_data, identifier=identifier)
    #     results = linter.run()
    #     expected = {
    #         'identifier': identifier,
    #         'success': True,
    #         'warnings': [
    #             "intro/translation-guidelines/01: Possible missing closing ')' -- found 21 '(' but 20 ')'",
    #             "intro/translation-guidelines/01: Seem to have the following unclosed field(s): '('",
    #             '<a href="https://git.door43.org/unfoldingWord/en_ta/src/master/intro\\finding-answers\\01.md" target="_blank">intro\\finding-answers\\01.md</a> - Line 1: First line in file should be a top level header. See "Text on first line"',
    #             '<a href="https://git.door43.org/unfoldingWord/en_ta/src/master/intro\\uw-intro\\01.md" target="_blank">intro\\uw-intro\\01.md</a> - Line 1: First line in file should be a top level header. See "Text on first line"',
    #             '<a href="https://git.door43.org/unfoldingWord/en_ta/src/master/intro\\uw-intro\\01.md" target="_blank">intro\\uw-intro\\01.md</a> - Line 29: Unordered list indentation. ',
    #         ],
    #         #'s3_results_key': None
    #     }
    #     # print( "results1", len(results), len(results['warnings']), results)
    #     self.assertEqual(len(results['warnings']), len(expected['warnings']))
    #     self.assertDictEqual(results, expected)

    def test_strip_tags(self):
        ml = MarkdownLinter(repo_subject='Unknown', source_dir=None)
        text = ml.strip_tags('<a href="test"><u>remove my tags')
        self.assertEqual(text, 'remove my tags')
