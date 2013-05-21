from collections import deque
from threading import Lock

from scrapy import log
from scrapy.signals import engine_stopped
from selenium import webdriver
from scrapy_webdriver.http import WebdriverRequest, WebdriverActionRequest


class WebdriverManager(object):
    """Manages the life cycle of a webdriver instance."""
    USER_AGENT_KEY = 'phantomjs.page.settings.userAgent'

    def __init__(self, crawler):
        self.crawler = crawler
        self._lock = Lock()
        self._wait_queue = deque()
        self._wait_inpage_queue = deque()
        self._browser = crawler.settings.get('WEBDRIVER_BROWSER', None)
        self._user_agent = crawler.settings.get('USER_AGENT', None)
        self._web_driver_options = crawler.settings.get('WEBDRIVER_OPTIONS',
                                                        dict())
        self.timeout = crawler.settings.get("WEBDRIVER_TIMEOUT", 0)
        self._webdriver = None
        if isinstance(self._browser, basestring):
            self._browser = getattr(webdriver, self._browser)
        elif self._browser is not None:
            self._webdriver = self._browser

    @property
    def _desired_capabilities(self):
        capabilities = dict()
        if self._user_agent is not None:
            capabilities[self.USER_AGENT_KEY] = self._user_agent
        return capabilities or None

    @classmethod
    def valid_settings(cls, settings):
        browser = settings.get('WEBDRIVER_BROWSER')
        if isinstance(browser, basestring):
            return getattr(webdriver, browser, None) is not None
        else:
            return browser is not None

    @property
    def webdriver(self):
        """Return the webdriver instance, instantiate it if necessary."""
        if self._webdriver is None:
            options = self._web_driver_options
            options['desired_capabilities'] = self._desired_capabilities
            self._webdriver = self._browser(**options)
            self.crawler.signals.connect(self._cleanup, signal=engine_stopped)
        return self._webdriver

    def acquire(self, request):
        """Acquire lock for the request, or enqueue request upon failure."""
        assert isinstance(request, WebdriverRequest), \
            'Only a WebdriverRequest can use the webdriver instance.'
        if self._lock.acquire(False):
            request.manager = self
            return request
        else:
            if isinstance(request, WebdriverActionRequest):
                queue = self._wait_inpage_queue
            else:
                queue = self._wait_queue
            queue.append(request)

    def get(self, url):
        if self.timeout:
            self.webdriver.set_page_load_timeout(self.timeout)
            self.webdriver.set_script_timeout(self.timeout)
            self.webdriver.implicitly_wait(self.timeout)
        try:
            self.webdriver.get(url)
        except Exception as e:
            message = "Unable to get url %s because of %s" % (url, e)
            log.msg(message, level=log.ERROR)

    def acquire_next(self):
        """Return the next waiting request, if any.

        In-page requests are returned first.

        """
        try:
            request = self._wait_inpage_queue.popleft()
        except IndexError:
            try:
                request = self._wait_queue.popleft()
            except IndexError:
                return
        return self.acquire(request)

    def release(self, msg):
        """Release the the webdriver instance's lock."""
        self._lock.release()

    def _cleanup(self):
        """Clean up when the scrapy engine stops."""
        if self._webdriver is not None:
            self._webdriver.quit()
            assert len(self._wait_queue) + len(self._wait_inpage_queue) == 0, \
                'Webdriver queue not empty at engine stop.'
