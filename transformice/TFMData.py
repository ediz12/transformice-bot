import urllib2
import json
import logging as log

class TFMData(object):
    def __init__(self, data_url, data_url2=None):
        self.data_url = data_url
        self.data_url2 = data_url2
        self.data = self._get_data()

    @staticmethod
    def _fetch_data(data):
        try:
            udata = urllib2.urlopen(data, timeout=5)
            data = udata.read()
            udata.close()
            data = json.loads(data)
            log.info("[TFMDATA] Got TFM Data successfully")
            return data
        except urllib2.URLError, e:
            raise urllib2.URLError(e)

    def _get_data(self):
        try:
            return self._fetch_data(self.data_url)
        except urllib2.URLError, e:
            try:
                log.error("Failed to get TFM data (%s). Trying alternative" % e)
                return self._fetch_data(self.data_url2)
            except urllib2.URLError, e:
                log.error("Alternative data failed. (%s)." % e)
                return False

    def reload_data(self):
        self.data = self._get_data()
        return self.data
