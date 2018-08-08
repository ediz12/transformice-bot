from twisted.internet.protocol import Protocol


class BridgeProtocol(Protocol):
    def __init__(self, **kwargs):
        self.factorylist = kwargs["factorylist"]
        self.sep = chr(12)

    def connectionMade(self):
        self.authenticate()
        self.factory.current_protocol = self

    def connectionLost(self, reason="Lost"):
        self.factory.current_protocol = None

    def dataReceived(self, data):
        data = data.split(self.sep)[1:-1]
        while len(data) > 0:
            req = data[0]
            if req == "chat_message":
                name, message, chat = data[1:4]
                data = data[5:]
                if hasattr(self, "on_bridge_chat_message"):
                    getattr(self, "on_bridge_chat_message")(name, message, chat)

            elif req == "chat_message_failed":
                err, chat = data[1:3]
                data = data[4:]
                if hasattr(self, "on_bridge_chat_failed"):
                    getattr(self, "on_bridge_chat_failed")(err, chat)

            elif req == "chat_message_success":
                data = data[2:]

            elif req == "tribe_online_people":
                result = data[1]
                data = data[3:]
                if hasattr(self, "on_tribe_online_request"):
                    getattr(self, "on_tribe_online_request")(result)

            elif req == "stafflist":
                result = data[1]
                data = data[3:]
                if hasattr(self, "on_stafflist_request"):
                    getattr(self, "on_stafflist_request")(result)
            else:
                data = []

    def send(self, *data):
        data = self.sep + ("%s" % self.sep).join(data) + self.sep
        self.transport.write(data)

    def handler(self):
        pass

    def authenticate(self):
        self.send("auth", "tfm_bot")

    def send_message(self, to, user, message, chat):
        self.send("chat_message", to, user, message, chat)

    def send_chat_message_failed(self, to, chat):
        self.send("chat_message_failed", to, chat)

    def send_get_online_tribe(self, to, result):
        self.send("tribe_online_people", to, result)

    def send_stafflist_request(self, result):
        self.send("stafflist", "bot_discord", result)
