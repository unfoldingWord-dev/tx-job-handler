import os
import re
import tempfile

from rq_settings import prefix, debug_mode_flag
from app_settings.app_settings import AppSettings
from door43_tools.bible_books import BOOK_NUMBERS
from general_tools import file_utils, url_utils
from tx_usfm_tools.usfm_verses import verses
from linters.markdown_linter import MarkdownLinter
from linters.linter import Linter


class TnLinter(MarkdownLinter):

    # match links of form '](link)'
    link_marker_re = re.compile(r'\]\(([^\n()]+)\)')

    def __init__(self, single_file=None, *args, **kwargs):
        super(TnLinter, self).__init__(*args, **kwargs)

        self.single_file = single_file
        AppSettings.logger.debug(f"Convert single '{self.single_file}'")
        self.single_dir = None
        if self.single_file:
            parts = os.path.splitext(self.single_file)
            self.single_dir = self.get_dir_for_book(parts[0])
            AppSettings.logger.debug(f"Single source dir '{self.single_dir}'")


    def lint(self):
        """
        Checks for issues with translationNotes

        Use self.log.warning("message") to log any issues.
        self.source_dir is the directory of source files (.md)
        :return boolean:
        """
        self.source_dir = os.path.abspath(self.source_dir)
        source_dir = self.source_dir if not self.single_dir else os.path.join(self.source_dir, self.single_dir)
        for root, _dirs, files in os.walk(source_dir):
            for f in files:
                file_path = os.path.join(root, f)
                parts = os.path.splitext(f)
                if parts[1] == '.md':
                    contents = file_utils.read_file(file_path)
                    self.find_invalid_links(root, f, contents)

        for dir in BOOK_NUMBERS:
            found_files = False
            if self.single_dir and (dir != self.single_dir):
                continue
            AppSettings.logger.debug(f"Processing folder {dir}")
            file_path = os.path.join(self.source_dir, dir)
            for root, _dirs, files in os.walk(file_path):
                if root == file_path:
                    continue  # skip book folder

                if files:
                    found_files = True
                    break

            if not found_files \
            and 'OBS' not in self.repo_subject \
            and len(self.rc.projects) != 1: # Many repos are intentionally just one book
                msg = f"Missing tN book: '{dir}'"
                AppSettings.logger.debug(msg)
                self.log.warnings.append(msg)

        results = super(TnLinter, self).lint()  # Runs checks on Markdown, using the markdown linter
        if not results:
            AppSettings.logger.debug(f"Error running MD linter on {self.repo_subject}")
        return results


    def find_invalid_links(self, folder:str, f:str, contents:str) -> None:
        for link_match in TnLinter.link_marker_re.finditer(contents):
            link = link_match.group(1)
            if link:
                if link[:4] == 'http':
                    continue
                if link.find('.md') < 0:
                    continue

                file_path = os.path.join(folder, link)
                file_path_abs = os.path.abspath(file_path)
                exists = os.path.exists(file_path_abs)
                if not exists:
                    a = self.get_file_link(f, folder)
                    msg = f"{a}: contains invalid link: ({link})"
                    self.log.warnings.append(msg)
                    AppSettings.logger.debug(msg)

    def get_file_link(self, f:str, folder:str):
        parts = folder.split(self.source_dir)
        sub_path = self.source_dir  # default
        if len(parts) == 2:
            sub_path = parts[1][1:]
        self.repo_owner = self.repo_name = '' # WE DON'T KNOW THIS STUFF
        url = f"https://git.door43.org/{self.repo_owner}/{self.repo_name}/src/master/{sub_path}/{f}"
        a = f'<a href="{url}">{sub_path}/{f}</a>'
        return a
# end of TnLinter class



class TnTsvLinter(Linter):

    # match links of form '](link)'
    link_marker_re = re.compile(r'\]\(([^\n()]+)\)')
    EXPECTED_TAB_COUNT = 4 # So there's one more column than this
        # NOTE: The preprocessor removes unneeded columns while fixing links


    def __init__(self, *args, **kwargs) -> None:
        self.loaded_file_path = None
        self.loaded_file_contents = None
        self.preload_dir = tempfile.mkdtemp(prefix='tX_tN_linter_preload_')
        super(TnTsvLinter, self).__init__(*args, **kwargs)


    def lint(self) -> bool:
        """
        Checks for issues with translationNotes

        Use self.log.warning("message") to log any issues.
        self.source_dir is the directory of source files (.tsv)
        :return boolean:
        """
        self.source_dir = os.path.abspath(self.source_dir)
        source_dir = self.source_dir
        for root, _dirs, files in os.walk(source_dir):
            for f in files:
                file_path = os.path.join(root, f)
                if os.path.splitext(f)[1] == '.tsv':
                    contents = file_utils.read_file(file_path)
                    self.find_invalid_links(root, f, contents)

        file_list = os.listdir(source_dir)
        if  len(self.rc.projects) != 1: # Many repos are intentionally just one book
            for dir in BOOK_NUMBERS:
                found_file = False
                for file_name in file_list:
                    if file_name.endswith('.tsv') and dir.upper() in file_name:
                        found_file = True
                        break
                if not found_file:
                    msg = f"Missing tN tsv book: '{dir}'"
                    self.log.warnings.append(msg)
                    AppSettings.logger.debug(msg)

        # See if manifest has relationships back to original language versions
        # Compares with the unfoldingWord version if possible
        #   otherwise falls back to the Door43Catalog version
        # NOTE: This is the only place that Door43.org is hard-coded into the tX side of the system
        # TODO: Should this be moved back to the Door43 preprocessor like most other similar checks?
        need_to_check_quotes = False
        rels = self.rc.resource.relation
        if isinstance(rels, list):
            for rel in rels:
                if 'hbo/uhb' in rel:
                    if '?v=' not in rel:
                        self.log.warnings.append(f"No Hebrew version number specified in manifest: '{rel}'")
                    version = rel[rel.find('?v=')+3:]
                    url = f"https://git.door43.org/unfoldingWord/UHB/archive/v{version}.zip"
                    successFlag = self.preload_original_text_archive('uhb', url)
                    if not successFlag: # Try the Door43 Catalog version
                        url = f"https://cdn.door43.org/{rel.replace('?v=', '/v')}/uhb.zip"
                        successFlag = self.preload_original_text_archive('uhb', url)
                    if successFlag:
                        # self.log.warnings.append(f"Note: Using {url} for checking Hebrew quotes against.")
                        need_to_check_quotes = True
                if 'el-x-koine/ugnt' in rel:
                    if '?v=' not in rel:
                        self.log.warnings.append(f"No Greek version number specified in manifest: '{rel}'")
                    version = rel[rel.find('?v=')+3:]
                    url = f"https://git.door43.org/unfoldingWord/UGNT/archive/v{version}.zip"
                    successFlag = self.preload_original_text_archive('ugnt', url)
                    if not successFlag: # Try the Door43 Catalog version
                        url = f"https://cdn.door43.org/{rel.replace('?v=', '/v')}/ugnt.zip"
                        successFlag = self.preload_original_text_archive('ugnt', url)
                    if successFlag:
                        # self.log.warnings.append(f"Note: Using {url} for checking Greek quotes against.")
                        need_to_check_quotes = True
        if not need_to_check_quotes:
            self.log.warnings.append("Unable to find/load original language (Heb/Grk) sources for comparing snippets against.")

        # Now check tabs and C:V numbers
        MAX_ERROR_COUNT = 20
        for filename in sorted(file_list):
            if not filename.endswith('.tsv'): continue # Skip other files
            error_count = 0
            AppSettings.logger.info(f"Linting {filename}…")
            tsv_filepath = os.path.join(source_dir, filename)
            started = False
            expectedB = filename[-7:-4]
            lastC = lastV = C = V = '0'
            with open(tsv_filepath, 'rt') as tsv_file:
                for tsv_line in tsv_file:
                    tsv_line = tsv_line.rstrip('\n')
                    tab_count = tsv_line.count('\t')
                    if not started:
                        # AppSettings.logger.debug(f"TSV header line is '{tsv_line}'")
                        if tsv_line != 'Book	Chapter	Verse	OrigQuote	OccurrenceNote':
                            self.log.warnings.append(f"Unexpected TSV header line: '{tsv_line}' in {filename}")
                            error_count += 1
                        started = True
                    elif tab_count != TnTsvLinter.EXPECTED_TAB_COUNT:
                        self.log.warnings.append(f"Bad {expectedB} line near {C}:{V} with {tab_count} tabs (expected {TnTsvLinter.EXPECTED_TAB_COUNT})")
                        B = C = V = OrigQuote = OccurrenceNote = None
                        error_count += 1
                    else:
                        B, C, V, OrigQuote, OccurrenceNote = tsv_line.split('\t')
                        if B != expectedB:
                            self.log.warnings.append(f"Unexpected '{tsv_line}' line in {filename}")
                        if not C:
                            self.log.warnings.append(f"Missing chapter number after {lastC}:{lastV} in {filename}")
                        elif not C.isdigit() and C not in ('front','back'):
                            self.log.warnings.append(f"Bad '{C}' chapter number near verse {V} in {filename}")
                        elif C.isdigit() and lastC.isdigit():
                            lastCint, Cint = int(lastC), int(C)
                            if Cint < lastCint:
                                self.log.warnings.append(f"Decrementing '{C}' chapter number after {lastC} in {filename}")
                            elif Cint > lastCint+1:
                                self.log.warnings.append(f"Missing chapter number {lastCint+1} after {lastC} in {filename}")
                        if C == lastC: # still in the same chapter
                            if not V.isdigit():
                                self.log.warnings.append(f"Bad '{V}' verse number in chapter {C} in {filename}")
                            elif lastV.isdigit():
                                lastVint, Vint = int(lastV), int(V)
                                if Vint < lastVint:
                                    self.log.warnings.append(f"Decrementing '{V}' verse number after {lastV} in chapter {C} in {filename}")
                                # NOTE: Disabled because missing verse notes are expected
                                # elif Vint > lastVint+1:
                                    # self.log.warnings.append(f"Missing verse number {lastVint+1} after {lastV} in chapter {C} in {filename}")
                        else: # just started a new chapter
                            if not V.isdigit() and V != 'intro':
                                self.log.warnings.append(f"Bad '{V}' verse number in start of chapter {C} in {filename}")
                        if OrigQuote and need_to_check_quotes:
                            try: self.check_original_language_quotes(B,C,V,OrigQuote)
                            except Exception as e:
                                self.log.warnings.append(f"{B} {C}:{V} Unable to check original language quotes: {e}")
                        if OccurrenceNote:
                            left_count, right_count = OccurrenceNote.count('['), OccurrenceNote.count(']')
                            if left_count != right_count:
                                self.log.warnings.append(f"Unmatched square brackets at {B} {C}:{V} in '{OccurrenceNote}'")
                            self.check_markdown(OccurrenceNote, f"{B} {C}:{V}")
                        lastC, lastV = C, V
                        if lastC == 'front': lastC = '0'
                        elif lastC == 'back': lastC = '999'
                    if error_count > MAX_ERROR_COUNT:
                        AppSettings.logger.critical("TnTsvLinter: Too many TSV count errors -- aborting!")
                        break

        if prefix and debug_mode_flag:
            AppSettings.logger.debug(f"Temp folder '{self.preload_dir}' has been left on disk for debugging!")
        else:
            file_utils.remove_tree(self.preload_dir)
        return True
    # end of TnTsvLinter.lint()


    def check_markdown(self, markdown_string, reference):
        """
        Checks the header progressions in the markdown string
        """
        # TODO: Why can't we convert <br> to nl and run the normal MD linter???
        header_level = 0
        for bit in markdown_string.split('<br>'):
            if bit.startswith('# '):
                header_level = 1
            elif bit.startswith('## '):
                if header_level < 1:
                    self.log.warnings.append(f"Markdown header jumped directly to level 2 at {reference}")
                header_level = 2
            elif bit.startswith('### '):
                if header_level < 2:
                    self.log.warnings.append(f"Markdown header jumped directly to level 3 at {reference}")
                header_level = 3
            elif bit.startswith('#### '):
                if header_level < 3:
                    self.log.warnings.append(f"Markdown header jumped directly to level 4 at {reference}")
                header_level = 4
            elif bit.startswith('##### '):
                if header_level < 4:
                    self.log.warnings.append(f"Markdown header jumped directly to level 5 at {reference}")
                header_level = 5
            elif bit.startswith('#'):
                self.log.warning(f"Badly formatted markdown header at {reference}")
    # end of TnTsvLinter.check_markdown function


    def preload_original_text_archive(self, name:str, zip_url:str) -> bool:
        """
        Fetch and unpack the Hebrew/Greek zip file.

        Returns a True/False success flag
        """
        AppSettings.logger.info(f"preload_original_text_archive({name}, {zip_url})…")
        zip_path = os.path.join(self.preload_dir, f'{name}.zip')
        try:
            url_utils.download_file(zip_url, zip_path)
            file_utils.unzip(zip_path, self.preload_dir)
            file_utils.remove_file(zip_path)
        except Exception as e:
            AppSettings.logger.error(f"Unable to download {zip_url}: {e}")
            self.log.warnings.append(f"Unable to download '{name}' from {zip_url}")
            return False
        # AppSettings.logger.debug(f"Got {name} files:", os.listdir(self.preload_dir))
        return True
    # end of TnTsvLinter.preload_original_text_archive function


    def check_original_language_quotes(self, B:str,C:str,V:str, quoteField:str) -> None:
        """
        Check that the quoted portions can indeed be found in the original language versions.
        """
        # AppSettings.logger.debug(f"check_original_language_quotes({B},{C},{V}, {quoteField})…")

        verse_text = self.get_passage(B,C,V)
        if not verse_text:
            return # nothing else we can do here

        if '...' in quoteField:
            AppSettings.logger.debug(f"Bad ellipse characters in {B} {C}:{V} '{quoteField}'")
            self.log.warnings.append(f"Should use proper ellipse character in {B} {C}:{V} '{quoteField}'")

        if '…' in quoteField:
            quoteBits = quoteField.split('…')
            if ' …' in quoteField or '… ' in quoteField:
                AppSettings.logger.debug(f"Unexpected space(s) beside ellipse in {B} {C}:{V} '{quoteField}'")
                self.log.warnings.append(f"Unexpected space(s) beside ellipse character in {B} {C}:{V} '{quoteField}'")
        elif '...' in quoteField: # Yes, we still actually allow this
            quoteBits = quoteField.split('...')
            if ' ...' in quoteField or '... ' in quoteField:
                AppSettings.logger.debug(f"Unexpected space(s) beside ellipse characters in {B} {C}:{V} '{quoteField}'")
                self.log.warnings.append(f"Unexpected space(s) beside ellipse characters in {B} {C}:{V} '{quoteField}'")
        else:
            quoteBits = None

        if quoteBits:
            numQuoteBits = len(quoteBits)
            if numQuoteBits >= 2:
                for index in range(numQuoteBits):
                    if quoteBits[index] not in verse_text: # this is what we really want to catch
                        # If the quote has multiple parts, create a description of the current part
                        if index == 0: description = 'beginning'
                        elif index == numQuoteBits-1: description = 'end'
                        else: description = f"middle{index if numQuoteBits>3 else ''}"
                        AppSettings.logger.debug(f"Unable to find {B} {C}:{V} '{quoteBits[index]}' ({description}) in '{verse_text}'")
                        self.log.warnings.append(f"Unable to find {B} {C}:{V} {description} of '{quoteField}' in '{verse_text}'")
            else: # < 2
                self.log.warnings.append(f"Ellipsis without surrounding snippet in {B} {C}:{V} '{quoteField}'")
        elif quoteField not in verse_text:
            AppSettings.logger.debug(f"Unable to find {B} {C}:{V} '{quoteField}' in '{verse_text}'")
            # if B=='TIT':
            #     import unicodedata
            #     print(f"quoteField='{quoteField}'")
            #     for char in quoteField:
            #         print(unicodedata.name(char), end='  ')
            #     print(f"\nverse_text='{verse_text}'")
            #     for char in verse_text:
            #         print(unicodedata.name(char), end='  ')
            #     print()
            extra_text = " (contains No-Break Space shown as '~')" if '\u00A0' in quoteField else ""
            if extra_text: quoteField = quoteField.replace('\u00A0', '~')
            self.log.warnings.append(f"Unable to find {B} {C}:{V} '{quoteField}'{extra_text} in '{verse_text}'")
    # end of TnTsvLinter.check_original_language_quotes function


    def get_passage(self, B:str, C:str,V:str) -> str:
        """
        Get the information for the given verse out of the appropriate book file.

        Also removes milestones and extra word (\\w) information
        """
        # AppSettings.logger.debug(f"get_passage({B}, {C},{V})…")
        try: book_number = verses[B]['usfm_number']
        except KeyError: # how can this happen?
            AppSettings.logger.error(f"Unable to find book number for '{B} {C}:{V}' in get_passage()")
            book_number = 0

        # Look for OT book first -- if not found, look for NT book
        #   NOTE: Lazy way to determine which testament/folder the book is in
        book_path = os.path.join(self.preload_dir, f'{book_number}-{B}.usfm')
        if not os.path.isfile(book_path):
            # NOTE: uW UHB and UGNT repos didn't use to have language code in repo name
            book_path = os.path.join(self.preload_dir, 'hbo_uhb/', f'{book_number}-{B}.usfm')
            if not os.path.isfile(book_path):
                book_path = os.path.join(self.preload_dir, 'uhb/', f'{book_number}-{B}.usfm')
            if not os.path.isfile(book_path):
                book_path = os.path.join(self.preload_dir, 'el-x-koine_ugnt/', f'{book_number}-{B}.usfm')
            if not os.path.isfile(book_path):
                book_path = os.path.join(self.preload_dir, 'ugnt/', f'{book_number}-{B}.usfm')
        if not os.path.isfile(book_path):
            return None
        if self.loaded_file_path != book_path:
            # It's not cached already
            AppSettings.logger.info(f"Reading {book_path}…")
            with open(book_path, 'rt') as book_file:
                self.loaded_file_contents = book_file.read()
            self.loaded_file_path = book_path
            # Do some initial cleaning and convert to lines
            self.loaded_file_contents = self.loaded_file_contents \
                                            .replace('\\zaln-e\\*','') \
                                            .replace('\\k-e\\*', '') \
                                            .split('\n')
        # print("loaded_book_contents", self.loaded_file_contents)
        found_chapter = found_verse = False
        verseText = ''
        for book_line in self.loaded_file_contents:
            if not found_chapter and book_line == f'\\c {C}':
                found_chapter = True
                continue
            if found_chapter and not found_verse and book_line.startswith(f'\\v {V}'):
                found_verse = True
                continue
            if found_verse:
                if book_line.startswith('\\v ') or book_line.startswith('\\c '):
                    break # Don't go into the next verse or chapter
                ix = book_line.find('\\k-s ')
                if ix != -1:
                    book_line = book_line[:ix] # Remove k-s field right up to end of line
                verseText += ('' if book_line.startswith('\\f ') else ' ') + book_line
        verseText = verseText.replace('\\p ', '').strip().replace('  ', ' ')
        # print(f"Got verse text1: '{verseText}'")

        # Remove \w fields (just leaving the actual Bible text words)
        ixW = verseText.find('\\w ')
        while ixW != -1:
            ixEnd = verseText.find('\\w*', ixW)
            if ixEnd != -1:
                field = verseText[ixW+3:ixEnd]
                bits = field.split('|')
                adjusted_field = bits[0]
                verseText = verseText[:ixW] + adjusted_field + verseText[ixEnd+3:]
            else:
                AppSettings.logger.error(f"Missing \\w* in {B} {C}:{V} verseText: '{verseText}'")
                verseText = verseText.replace('\\w ', '', 1) # Attempt to limp on
            ixW = verseText.find('\\w ', ixW+1) # Might be another one
        # print(f"Got verse text2: '{verseText}'")

        # Remove footnotes
        verseText = re.sub(r'\\f (.+?)\\f\*', '', verseText)
        # Remove alternative versifications
        verseText = re.sub(r'\\va (.+?)\\va\*', '', verseText)
        # print(f"Got verse text3: '{verseText}'")

        # Final clean-up (shouldn't be necessary, but just in case)
        return verseText.replace('  ', ' ')
    # end of TnTsvLinter.get_passage function


    def find_invalid_links(self, folder:str, filename:str, contents:str) -> None:
        # AppSettings.logger.debug(f"TnTsvLinter.find_invalid_links( {folder}, {f}, {contents} ) …")
        for link_match in TnLinter.link_marker_re.finditer(contents):
            link = link_match.group(1)
            if link:
                if link[:4] == 'http':
                    continue
                if link.find('.tsv') < 0:
                    continue

                file_path = os.path.join(folder, link)
                file_path_abs = os.path.abspath(file_path)
                exists = os.path.exists(file_path_abs)
                if not exists:
                    a = self.get_file_link(filename, folder)
                    msg = f"{a}: contains invalid link: ({link})"
                    self.log.warnings.append(msg)
                    AppSettings.logger.debug(msg)
    # end of TnTsvLinter.find_invalid_links function

    def get_file_link(self, filename:str, folder:str) -> str:
        parts = folder.split(self.source_dir)
        sub_path = self.source_dir  # default
        if len(parts) == 2:
            sub_path = parts[1][1:]
        self.repo_owner = self.repo_name = '' # WE DON'T KNOW THIS STUFF
        url = f'https://git.door43.org/{self.repo_owner}/{self.repo_name}/src/master/{sub_path}/{filename}'
        a = f'<a href="{url}">{sub_path}/{filename}</a>'
        return a
    # end of TnTsvLinter.get_file_link function
# end of TnTsvLinter class
