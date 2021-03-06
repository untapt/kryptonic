import os
from subprocess import Popen, PIPE
import unittest
from selenium.webdriver import Firefox, FirefoxProfile, Remote, Chrome, ChromeOptions
from selenium.webdriver.firefox.options import Options
from .options import Config
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException,NoSuchElementException,ElementNotVisibleException,ElementNotInteractableException
from time import sleep

import logging as log
from pymongo import MongoClient
from collections import ChainMap

MONGO_URI = 'localhost:27017' # TODO: A centralized place for the mongouri, modifiable by config and options.py
MONGO_DB = 'untapt_krypton'

#TODO: Refactor method extentions to a new KryptonMethods class and use multiple inheritance to Krypton<driver> classes
class KrDriver(Firefox):

    config_options = Config().options

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def wait_for_element(self, id=None, css_selector=None, class_name=None, xpath=None, link_text=None, timeout=20, optional=True ):
        if id:
            by = By.ID
            selector = id
        elif css_selector:
            by = By.CSS_SELECTOR
            selector = css_selector
        elif class_name:
            by = By.CLASS_NAME
            selector = class_name
        elif xpath:
            by = By.XPATH
            selector = xpath
        elif link_text:
            by = By.LINK_TEXT
            selector = link_text
        else:
            raise ValueError("wait_for_element must use one kwarg of: id, css_selector, class_name, xpath, link_text")

        try:
            return KrWebElementWrapper(
                WebDriverWait(self, timeout).until(EC.presence_of_element_located((by, selector))))
        except TimeoutException as ex:
            if optional is True:
                log.info(f'wait_for_element: Timeout waiting for "{selector}" but doing nothing because "optional" is True')
                return KrMissingElement()
            else:
                log.error(f'wait_for_element: Timeout while waiting for element {selector}')
                raise TimeoutException(f'wait_for_element: Timeout while waiting for element {selector}', ex.screen, ex.stacktrace)


    def get_element(self, id=None, css_selector=None, class_name=None, xpath=None, link_text=None ):
        if id:
            by = By.ID
            selector = id
        elif css_selector:
            by = By.CSS_SELECTOR
            selector = css_selector
        elif class_name:
            by = By.CLASS_NAME
            selector = class_name
        elif xpath:
            by = By.XPATH
            selector = xpath
        elif link_text:
            by = By.LINK_TEXT
            selector = link_text
        else:
            raise ValueError("get_element must use one kwarg of: id, css_selector, class_name, xpath, link_text")

        try:
            timeout=self.config_options['timeout']
            WebDriverWait(self, timeout).until(EC.presence_of_element_located((by, selector)))
            elms = self.find_elements(by, selector)
            if not elms:
                raise NoSuchElementException(f'get_element: Element {selector} not found on page {self.url}')
            if elms[0].is_displayed() or elms[0].is_enabled():
                return elms[0]
            else:
                raise ElementNotVisibleException(f'get_element: Element {selector} not displayed or not enabled on page {self.url}')


        except TimeoutException as ex:
            log.error(f'get_element: Timeout while waiting for element {selector}')
            raise TimeoutException(f'get_element: Timeout while waiting for element {selector} on page {self.url}', ex.screen, ex.stacktrace)

    def f_send_keys(self, text, id=None, css_selector=None, class_name=None, xpath=None, link_text=None):
        return self.get_element(id,css_selector,class_name,xpath,link_text).send_keys(text)

    def f_click(self, id=None, css_selector=None, class_name=None, xpath=None, link_text=None):
        return self.get_element(id,css_selector,class_name,xpath,link_text).click()

    def f_get_text(self, id=None, css_selector=None, class_name=None, xpath=None, link_text=None):
        return self.get_element(id,css_selector,class_name,xpath,link_text).Text

    def f_get_attr(self, attribute_name, id=None, css_selector=None, class_name=None, xpath=None, link_text=None):
        return self.get_element(id,css_selector,class_name,xpath,link_text).get_attribute(attribute_name)

    @property
    def url(self):
        return self.current_url

    def get_path(self, path):
        self.get(self.config_options['url'] + path)


class KrWebElementWrapper:

    def __init__(self, webelement):
        self.webelement = webelement

    def __getattr__(self, item):
        return getattr(self.unwrap(), item)

    def click(self):
        self.unwrap().click()
        return self

    def send_keys(self, *value):
        try:
            self.unwrap().send_keys(*value)
            return self
        except TypeError as e:
            raise TypeError("Don't know how to send this type to web element\n", e)

    def wait(self, seconds):
        sleep(seconds)
        return self

    def unwrap(self):
        return self.webelement

class KrMissingElement:

    def noop(self, *args, **kwargs):
        return None

    def __getattr__(self, item):
        return self.noop


class KrTestCase(unittest.TestCase):
    # config_options = Config().options

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance_config = getattr(self.__class__, 'config', {})
        self.config_options = ChainMap(instance_config, Config().options)


    @classmethod
    def setUpClass(cls):
        print(cls.__module__)

        for path, dirs, files in os.walk(f'./scenarios/{cls.__module__}'):
            if path[-8:] == '__data__':
                cls._runNodeWithDbAccess(path, 'preTest.js')

            print(path, dirs, files)

    @classmethod
    def _runNodeWithDbAccess(cls, path, file):
        pass

    def _buildFirefoxDriver(self, headless=False):
        profile = FirefoxProfile()
        profile.accept_untrusted_certs = True
        profile.headless = headless
        profile.set_preference('security.fileuri.strict_origin_policy', False)
        profile.set_preference("http.response.timeout", self.config_options['timeout'])
        profile.set_preference("dom.max_script_run_time", self.config_options['timeout'])
        o = Options()
        o.set_headless(self.config_options['headless'])
        return KrDriver(firefox_profile=profile, options=o)

    def _buildChromeDriver(self, headless=False):
        profile = FirefoxProfile()
        profile.accept_untrusted_certs = True
        profile.headless = headless
        profile.set_preference('security.fileuri.strict_origin_policy', False)
        o = Options()
        o.set_headless(self.config_options['headless'])
        return KrDriver(firefox_profile=profile, options=o)

    def _cleanupDbWrites(self):
        client = MongoClient(MONGO_URI)
        db = getattr(client, MONGO_DB)
        log.debug('Removing all documents with _kryptonData')
        for collection_name in db.collection_names():
            db[collection_name].remove({'_kryptonData': {'$exists': True}}, multi=True)

    def setUp(self):
        if os.path.exists(f'./scenarios/{self.__module__}/__data__/setUp.js'):
            log.debug('setUp.js hook detected')
            js = Popen(['node', f'./scenarios/{self.__module__}/__data__/setUp.js'])
            stdout, stderr = js.communicate()
            log.debug(f'{self.__module__}/__data__/setUp.js:{stdout}')

        log.debug(f'config_options for {self}:\n{self.config_options}')

        self.browser = self.config_options['browser']
        self.url = self.config_options['url']
        self.cleanup = self.config_options['cleanup']
        if 'browser' not in self.config_options:
            self.driver = self._buildFirefoxDriver(headless=self.config_options['headless'])

        if self.browser == 'Firefox':
            self.driver = self._buildFirefoxDriver(headless=self.config_options['headless'])
        self.driver.set_page_load_timeout(self.config_options['timeout'])
        self.driver.implicitly_wait(self.config_options['timeout'])
        self.driver.set_script_timeout(self.config_options['timeout'])
        if 'url' in self.config_options:
            self.driver.get(self.config_options['url'])
        # print(self.__module__) TODO: this is the name that should be used with errors

    def tearDown(self):
        # if self.config_options.get('cleanup_db_writes', 'always') == 'always':
        #     self._cleanupDbWrites()

        if self.config_options['cleanup'] == 'onfailure':
            # logic for test case
            pass
        elif self.config_options['cleanup'] == 'always':
            self.driver.quit()


