import json
import os
import tempfile
import traceback
import requests
from shutil import copy
from urllib.parse import urlparse, urlunparse, parse_qsl
from abc import ABCMeta, abstractmethod
from datetime import datetime

from rq_settings import prefix, debug_mode_flag
from general_tools.url_utils import download_file
from general_tools.file_utils import unzip, add_contents_to_zip, remove_tree, remove
from global_settings.global_settings import GlobalSettings
from converters.convert_logger import ConvertLogger


class Converter(metaclass=ABCMeta):
    """
    """
    EXCLUDED_FILES = ['license.md', 'package.json', 'project.json', 'readme.md']


    def __init__(self, source, resource, cdn_file=None, options=None, convert_callback=None, identifier=None):
        """
        :param string source:
        :param string resource:
        :param string cdn_file: # NOTE: Should be cdn_file_KEY for S3, not a complete URL
        :param dict options:
        :param string convert_callback:
        :param string identifier:
        """
        GlobalSettings.logger.debug(f"Converter.__init__(s={source}, r={resource}, cdn_file={cdn_file}, options={options}, callback={convert_callback}, id={identifier})")
        self.source = source
        self.resource = resource
        self.cdn_file = cdn_file
        self.options = {} if not options else options

        self.log = ConvertLogger()
        self.converter_dir = tempfile.mkdtemp(prefix='tX_JH_converter_' \
                                + datetime.utcnow().strftime('%Y-%m-%d_%H:%M:%S_'))
        self.download_dir = os.path.join(self.converter_dir, 'Download/')
        os.mkdir(self.download_dir)
        self.files_dir = os.path.join(self.converter_dir, 'UnZipped/')
        os.mkdir(self.files_dir)
        self.input_zip_file = None  # If set, won't download the repo archive. Used for testing
        self.output_dir = os.path.join(self.converter_dir, 'Output/')
        os.mkdir(self.output_dir)
        if prefix and debug_mode_flag:
            self.debug_dir = os.path.join(self.converter_dir, 'DebugOutput/')
            os.mkdir(self.debug_dir)
        self.output_zip_file = tempfile.NamedTemporaryFile(prefix=f'{resource}_', suffix='.zip', delete=False).name
        self.callback = convert_callback
        self.callback_status = 0
        self.callback_results = None
        self.identifier = identifier
        if self.callback and not identifier:
            GlobalSettings.logger.error("Identity not given for callback")


    def close(self):
        """
        Delete temp files (except in debug mode)
        """
        # print("Converter close() was called!")
        if prefix and debug_mode_flag:
            GlobalSettings.logger.debug(f"Converter temp folder '{self.converter_dir}' has been left on disk for debugging!")
        else:
            remove_tree(self.converter_dir)
        remove(self.output_zip_file)

    # def __del__(self):
    #     print("Converter __del__() was called!")
    #     self.close()


    @abstractmethod
    def convert(self):
        """
        Dummy function for converters.

        Returns true if the resource could be converted
        :return bool:
        """
        raise NotImplementedError()


    def run(self):
        """
        Call the converters
        """
        success = False
        try:
            if not self.input_zip_file or not os.path.exists(self.input_zip_file):
                # No input zip file yet, so we need to download the archive
                self.download_archive()
            # unzip the input archive
            GlobalSettings.logger.debug(f"Converter unzipping {self.input_zip_file} to {self.files_dir}")
            unzip(self.input_zip_file, self.files_dir)
            # convert method called
            GlobalSettings.logger.debug("Converting files…")
            if self.convert():
                #GlobalSettings.logger.debug(f"Was able to convert {self.resource}")
                # Zip the output dir to the output archive
                #GlobalSettings.logger.debug(f"Converter adding files in {self.output_dir} to {self.output_zip_file}")
                add_contents_to_zip(self.output_zip_file, self.output_dir)
                # remove_tree(self.output_dir) # Done in converter.close()
                # Upload the output archive either to cdn_bucket or to a file (no cdn_bucket)
                GlobalSettings.logger.debug(f"Converter uploading output archive to {self.cdn_file} …")
                self.upload_archive()
                remove(self.output_zip_file)
                GlobalSettings.logger.debug("Uploaded.")
                success = True
            else:
                self.log.error(f"Resource {self.resource} currently not supported.")
        except Exception as e:
            self.log.error(f"Conversion process ended abnormally: {e}")
            GlobalSettings.logger.debug(f"Converter failure: {traceback.format_exc()}")

        results = {
            'identifier': self.identifier,
            'success': success and len(self.log.logs['error']) == 0,
            'info': self.log.logs['info'],
            'warnings': self.log.logs['warning'],
            'errors': self.log.logs['error']
        }

        if self.callback is not None:
            self.callback_results = results
            self.do_callback(self.callback, self.callback_results)

        GlobalSettings.logger.debug(results)
        return results


    def download_archive(self):
        archive_url = self.source
        filename = self.source.rpartition('/')[2]
        self.input_zip_file = os.path.join(self.download_dir, filename)
        if not os.path.isfile(self.input_zip_file):
            try:
                download_file(archive_url, self.input_zip_file)
            finally:
                if not os.path.isfile(self.input_zip_file):
                    raise Exception(f"Failed to download {archive_url}")


    def upload_archive(self):
        """
        Uploads self.output_zip_file
        """
        #GlobalSettings.logger.debug("converter.upload_archive()")
        if self.cdn_file and os.path.isdir(os.path.dirname(self.cdn_file)):
            #GlobalSettings.logger.debug("converter.upload_archive() doing copy")
            copy(self.output_zip_file, self.cdn_file)
        elif GlobalSettings.cdn_s3_handler():
            #GlobalSettings.logger.debug("converter.upload_archive() using S3 handler")
            GlobalSettings.cdn_s3_handler().upload_file(self.output_zip_file, self.cdn_file, cache_time=0)


    def do_callback(self, url, payload):
        if url.startswith('http'):
            headers = {"content-type": "application/json"}
            GlobalSettings.logger.debug(f"Making callback to {url} with payload:")
            GlobalSettings.logger.debug(json.dumps(payload)[:256])
            response = requests.post(url, json=payload, headers=headers)
            self.callback_status = response.status_code
            if (self.callback_status >= 200) and (self.callback_status < 299):
                GlobalSettings.logger.debug("Callback finished.")
            else:
                GlobalSettings.logger.error(f"Error calling callback code {self.callback_status}: {response.reason}")
        else:
            GlobalSettings.logger.error(f"Invalid callback url: {url}")


    def check_for_exclusive_convert(self):
        """
        Not sure what this is used for???

        Returns either:
            an empty list (normally), or
            a list of the files which should be converted
        """
        convert_only_list = []
        if self.source and len(self.source) > 0:
            parsed = urlparse(self.source)
            params = parse_qsl(parsed.query)
            if params and len(params) > 0:
                for i in range(0, len(params)):
                    item = params[i]
                    if item[0] == 'convert_only':
                        convert_only_list = item[1].split(',')
                        GlobalSettings.logger.debug(f"Converting only: {convert_only_list}")
                        self.source = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
                        break
        if convert_only_list:
            GlobalSettings.logger.debug(f"converter:check_for_exclusive_convert() returned a list of {len(convert_only_list)} files: {convert_only_list}")
        return convert_only_list
