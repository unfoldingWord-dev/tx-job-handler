import json
import os
import tempfile
import traceback
from shutil import copy
from urllib.parse import urlparse, urlunparse, parse_qsl
from abc import ABCMeta, abstractmethod
from datetime import datetime
from typing import Dict, Optional, Any

from rq_settings import prefix, debug_mode_flag
from general_tools.url_utils import download_file
from general_tools.file_utils import unzip, add_contents_to_zip, remove_tree, remove_file
from app_settings.app_settings import AppSettings
from converters.convert_logger import ConvertLogger


class Converter(metaclass=ABCMeta):
    """
    """
    # RJH removed ReadMe so it can display for otherwise empty repos
    #   (but usually it's not copied across by the preprocessors anyway).
    EXCLUDED_FILES = ['license.md', 'package.json', 'project.json'] #, 'readme.md']


    def __init__(self, repo_subject:str, source_dir:str, cdn_file_key:Optional[str]=None, options:Optional[Dict[str,Any]]=None, identifier:Optional[str]=None) -> None:
        """
        :param string source:
        :param string repo_subject:
        :param string source_dir:
        :param string cdn_file_key: # NOTE: For S3 upload, not a complete URL
        :param dict options:
        :param string identifier:
        """
        AppSettings.logger.debug(f"Converter.__init__(rs={repo_subject}, source_dir={source_dir}, cdn_file_key={cdn_file_key}, options={options}, id={identifier})")
        # self.source_zip = source_zip
        self.repo_subject = repo_subject
        assert self.repo_subject # Programming error if not
        self.source_dir = source_dir
        assert self.repo_subject # Programming error if not
        self.cdn_file_key = cdn_file_key
        self.options = options if options else {}
        self.identifier = identifier

        self.log = ConvertLogger()
        if not os.path.isdir(self.source_dir):
            self.log.error(f"No such folder: {self.source_dir}")
            return

        self.converter_dir = tempfile.mkdtemp(prefix=f'tX_{repo_subject}_converter_' \
                                + datetime.utcnow().strftime('%Y-%m-%d_%H:%M:%S_'))
        self.download_dir = os.path.join(self.converter_dir, 'Download/')
        os.mkdir(self.download_dir)
        self.files_dir = os.path.join(self.converter_dir, 'UnZipped/')
        os.mkdir(self.files_dir)
        # self.input_zip_file = None  # If set, won't download the repo archive. Used for testing
        self.output_dir = os.path.join(self.converter_dir, 'Output/')
        os.mkdir(self.output_dir)
        if prefix and debug_mode_flag:
            self.debug_dir = os.path.join(self.converter_dir, 'DebugOutput/')
            os.mkdir(self.debug_dir)
        self.output_zip_file = tempfile.NamedTemporaryFile(prefix=f'{repo_subject}_', suffix='.zip', delete=False).name
        # self.callback = convert_callback
        # self.callback_status = 0
        # self.callback_results = None
        # if self.callback and not identifier:
        #     AppSettings.logger.error("Identity not given for callback")


    def close(self) -> None:
        """
        Delete temp files (except in debug mode)
        """
        # print("Converter close() was called!")
        if prefix and debug_mode_flag:
            AppSettings.logger.debug(f"Converter temp folder '{self.converter_dir}' has been left on disk for debugging!")
        else:
            try: remove_tree(self.converter_dir)
            except AttributeError: pass # no such variable
        try: remove_file(self.output_zip_file)
        except AttributeError: pass # no such variable

    # def __del__(self):
    #     print("Converter __del__() was called!")
    #     self.close()


    @abstractmethod
    def convert(self) -> None:
        """
        Dummy function for converters.

        Returns true if the resource could be converted
        :return bool:
        """
        raise NotImplementedError()


    def run(self) -> Dict[str,Any]:
        """
        Call the converters
        """
        success = False
        if os.path.isdir(self.source_dir):
            self.files_dir = self.source_dir # TODO: This can be cleaned up later
            try:
                # if not self.input_zip_file or not os.path.exists(self.input_zip_file):
                #     # No input zip file yet, so we need to download the archive
                #     self.download_archive()
                # # unzip the input archive
                # AppSettings.logger.debug(f"Converter unzipping {self.input_zip_file} to {self.files_dir}")
                # unzip(self.input_zip_file, self.files_dir)

                # convert method called
                AppSettings.logger.debug(f"Converting files from {self.files_dir}…")
                if self.convert():
                    #AppSettings.logger.debug(f"Was able to convert {self.resource}")
                    # Zip the output dir to the output archive
                    #AppSettings.logger.debug(f"Converter adding files in {self.output_dir} to {self.output_zip_file}")
                    add_contents_to_zip(self.output_zip_file, self.output_dir)
                    # remove_tree(self.output_dir) # Done in converter.close()
                    # Upload the output archive either to cdn_bucket or to a file (no cdn_bucket)
                    AppSettings.logger.info(f"Converter uploading output archive to {self.cdn_file_key} …")
                    if self.cdn_file_key:
                        self.upload_archive()
                        AppSettings.logger.debug(f"Uploaded converted files (using '{self.cdn_file_key}').")
                    else:
                        AppSettings.logger.debug("No converted file upload requested.")
                    remove_file(self.output_zip_file)
                    success = True
                else:
                    self.log.error(f"Resource type '{self.repo_subject}' currently not supported.")
            except Exception as e:
                self.log.error(f"Conversion process ended abnormally: {e}")
                AppSettings.logger.debug(f"Converter failure: {traceback.format_exc()}")

        results = {
            'identifier': self.identifier,
            'success': success and len(self.log.logs['error']) == 0,
            'info': self.log.logs['info'],
            'warnings': self.log.logs['warning'],
            'errors': self.log.logs['error']
        }

        # if self.callback is not None:
        #     self.callback_results = results
        #     self.do_callback(self.callback, self.callback_results)

        # AppSettings.logger.debug(results)
        return results


    def upload_archive(self) -> None:
        """
        Uploads self.output_zip_file
        """
        #AppSettings.logger.debug("converter.upload_archive()")
        if self.cdn_file_key and os.path.isdir(os.path.dirname(self.cdn_file_key)):
            #AppSettings.logger.debug("converter.upload_archive() doing copy")
            copy(self.output_zip_file, self.cdn_file_key)
        elif AppSettings.cdn_s3_handler():
            #AppSettings.logger.debug("converter.upload_archive() using S3 handler")
            AppSettings.cdn_s3_handler().upload_file(self.output_zip_file, self.cdn_file_key, cache_time=0)
