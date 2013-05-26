from scrapy import log
from scrapy.utils.decorator import inthread
from scrapy.http import HtmlResponse
from scrapy.utils.misc import load_object
from selenium import webdriver
from scrapy.core.downloader.handlers.http import HttpDownloadHandler
from .http import WebdriverActionRequest, WebdriverRequest, WebdriverResponse
from .manager import WebdriverManager

from twisted.internet import defer
FALLBACK_HANDLER = 'scrapy.core.downloader.handlers.http.HttpDownloadHandler'


class WebdriverDownloadHandler(HttpDownloadHandler):
    """This download handler uses webdriver, deferred in a thread.

    Falls back to the stock scrapy download handler for non-webdriver requests.

    """
    def __init__(self, settings):
        super(WebdriverDownloadHandler, self).__init__(settings)
        self._enabled = settings.get('WEBDRIVER_BROWSER') is not None
        self.webdriver = webdriver.PhantomJS(service_args=['--load-images=false'])

    def download_request(self, request, spider):
        """Return the result of the right download method for the request."""
        if 'webdriver' in request.meta:
            dfd = defer.Deferred()
            dfd.addErrback(log.err, spider=spider)
            log.msg('Downloading %s with webdriver' % request.url, level=log.DEBUG)
            self.webdriver.get(request.url)

            res = HtmlResponse(request.url, body=self.webdriver.page_source, encoding='utf-8')
            dfd.callback(res)
            return dfd
        else:
            return super(WebdriverDownloadHandler, self).download_request(request, spider)

    def __del__(self):
        try:
            self.webdriver.quit()
        except:
            pass

