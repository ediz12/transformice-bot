from twisted.internet.protocol import ClientFactory
from twisted.internet import reactor
import logging as log


class FactoryHandler(object):
    def __init__(self):
        self.factories = {}

    def add_factory(self, name, factory):
        self.factories[name] = factory

    def get_factory_protocol(self, factoryname):
        return self.factories[factoryname].current_protocol

    def start_factories(self):
        for name, factory in self.factories.iteritems():
            self.factories[name].connector = reactor.connectTCP(factory.host, factory.port, factory)

    def start_factory(self, name):
        factory = self.factories[name]
        self.factories[name].connector = reactor.connectTCP(factory.host, factory.port, factory)


class Factory(ClientFactory):
    """
    Sample factory class to use for protocols
    """
    def __init__(self, protocol, host, port, *args, **kwargs):
        self.protocol = protocol
        self.host = host
        self.port = port
        self.args = args
        self.kwargs = kwargs
        self.stop = False

    def buildProtocol(self, addr):
        p = self.protocol(*self.args, **self.kwargs)
        p.factory = self
        return p

    def clientConnectionFailed(self, connector, reason):
        if not self.stop:
            log.error("Connection failed: %s" % reason.value)
            log.info("I will reconnect in 60 seconds.")
            reactor.callLater(60, connector.connect)
        else:
            log.info("Failed: Connection successfully closed.")

    def clientConnectionLost(self, connector, reason):
        if not self.stop:
            log.error("Connection lost: %s" % reason.value)
            log.info("I will reconnect in 60 seconds.")
            reactor.callLater(60, connector.connect)
        else:
            log.info("Lost: Connection successfully closed.")

    def stop_connection(self):
        self.stop = True
