# coding=utf-8
import base64
import hashlib
import logging as log
import struct
import urllib2
import re
from twisted.internet.protocol import Protocol
from twisted.internet.task import LoopingCall
import errors


class TFMProtocol(Protocol):
    def __init__(self, *args, **kwargs):
        try:
            if kwargs["data"] is False:
                raise errors.TFMDataUnacquired("No TFM data found, closing connection")
        except KeyError:
            raise KeyError("TFM Data is not initialized")

        self.player_bot = False
        self.args = args
        self.kwargs = kwargs
        self.name = "Unknown"
        self.factorylist = kwargs["factorylist"]
        self.tfm_data = kwargs["data"]
        self.data = self.tfm_data.data
        self.tribulle = self.data["tribulle"]

        self.tfm_connection_data = {"fingerprint": "\x00", "b_fingerprint": "\x00", "tribulleIncrement": 0}
        self.loops = {}
        self.incoming_data = ""
        self.fp = None

    def connectionMade(self):
        for name, factory in self.factorylist.factories.iteritems():
            if factory == self.factory:
                if name == "transformice":
                    # self.data = self.tfm_data.reload_data()
                    self.fp = "fingerprint"
                    self.connect()
                elif name == "bulle":
                    self.fp = "b_fingerprint"
                    self.connect_bulle(self.args[0])
                self.name = name
                if hasattr(self, "on_connection_made"):
                    getattr(self, "on_connection_made")(name)
                break
        self.factory.current_protocol = self

    def connectionLost(self, reason="Lost"):
        self.factory.current_protocol = None
        if hasattr(self, "on_connection_lost"):
            getattr(self, "on_connection_lost")(self.name)

    def dataReceived(self, data):
        # Read 1 byte, interpret that as an integer n, then read another n bytes,
        # Interpret those n bytes as integer x, read x bytes for whole packet
        # Read size: 1 byte
        # Read packet_length, 1, 2 or 3 bytes
        # data[:packet_length] is the whole packet
        # Iterate over data[packet_length:]
        self.incoming_data += data

        while len(self.incoming_data) > 0:
            data_length = len(self.incoming_data)
            size, temp_data = self.unpack_data("b", self.incoming_data)
            packet_length = 2 ** 128
            if size == 1:
                packet_length, temp_data = self.unpack_data("B", temp_data)
            elif size == 2:
                packet_length, temp_data = self.unpack_data("H", temp_data)
            elif size == 3:
                packet_length, temp_data = self.unpack_data("I", "\x00" + temp_data)

            # print "BEFORE: DL: %s | PL: %s | S: %s | P: %s" % (data_length, packet_length, size, repr(self.incoming_data))
            if data_length >= packet_length:
                c, temp_data = self.unpack_data("b", temp_data)
                cc, temp_data = self.unpack_data("b", temp_data)
                packet_length -= 2
                packet, self.incoming_data = temp_data[:packet_length], temp_data[packet_length:]

                # print "AFTER: DL: %s | PL: %s | S: %s | CCC: %s %s | P: %s | ID: %s" % (data_length, packet_length, size, c, cc, repr(packet), repr(self.incoming_data))
                self.handle(c, cc, packet)
            else:
                break

    @staticmethod
    def pack_data(types, *data):
        """
        Encrypting TFM protocol to send data to TFM servers.
        """
        result = ""
        for t, d in zip(types, data):
            if t == "s":
                result = result + struct.pack("!h", len(d)) + d
            elif t == ".":
                result = result + d
            else:
                result += struct.pack("!" + t, d)
        return result

    @staticmethod
    def unpack_data(t, data):
        """
        Decrypting TFM protocol to make it readable.
        """
        if t == "s":
            string_length = struct.unpack("!h", data[:2])[0]  # tuple
            result = data[2:2 + string_length]
            data = data[2 + string_length:]  # shifted data
        else:
            result = struct.unpack("!" + t, data[:struct.calcsize(t)])[0]
            data = data[struct.calcsize(t):]
        return result, data

    @staticmethod
    def get_packet_size(packet):
        if len(packet) < 256:
            return struct.pack("!BB", 1, len(packet) - 1)
        elif 256 <= len(packet) < 65536:
            return struct.pack("!BH", 2, len(packet) - 1)
        else:
            return struct.pack("!B", 3) + struct.pack("!I", len(packet) - 1)[1:]

    def build_packet(self, fp, c, cc, data="", old=False):
        """
        Building the full packet to be sent to server.

        :param fp: Fingerprint
        :param c: First byte of packet identifier
        :param cc: Second byte of packet identifier
        :param data: The rest of the packet
        :param old: Whether the packet must be old protocol
        :return: The full packet
        """
        if old:
            packet = fp + chr(1) + chr(1) + struct.pack("!h", len(c + cc + data)) + c + cc + data
            packet_len = self.get_packet_size(packet)
        else:
            packet = fp + c + cc + data
            # Some code here are omitted for security.
            packet_len = self.get_packet_size(packet)
        packet = packet_len + packet

        self.tfm_connection_data[self.fp] = chr((ord(fp) + 1) % 100)
        return packet

    def send(self, c, cc, what, data="", old=False):
        """
        Sending the packet to the TFM servers.

        :param c: First byte of packet identifier
        :param cc: Second byte of packet identifier
        :param what: What is this packet about
        :param data: The rest of the packet
        :param old: Whether the packet must be old protocol
        """
        packet = self.build_packet(self.tfm_connection_data[self.fp], c, cc, data, old)

        log.debug("[OUT] %s: %s" % (what, repr(packet)))
        self.transport.write(packet)

    def handle(self, c, cc, packet):
        """
        Turns packet into human-friendly text.

        :param c: First byte of packet identifier
        :param cc: Second byte of packet identifier
        :param packet: The packet data
        """

        # VALUES ARE CHANGED FOR SECURITY

        c_cc = (c, cc)

        if c_cc not in [(0, 0), (0, 0), (0, 0)]:
            # MOVEMENT, SYNC, WTF PACKETS
            log.debug("[IN] %s: %s" % (c_cc, repr(packet)))

        if c_cc == (0, 0):
            # OLD PROTOCOL
            packet_len, old_pro = self.unpack_data("h", packet)
            raw_oldc, raw_oldcc, packet = old_pro[0], old_pro[1], old_pro[2:]
            oldc_cc = (ord(raw_oldc), ord(raw_oldcc))

            if oldc_cc == (0, 0):
                # PLAYER JOINED ROOM / RESPAWN
                p_info = packet[1:].split("#")
                name, mouse_id, dead, joined_room, score, hascheese, title, avatar, clothes, forum_id, fur_color, shaman_color, idk, empty = p_info

                player = {"mouse_id": mouse_id, "name": name, "dead": dead, "score": score, "hascheese": hascheese,
                          "title": title, "avatar": avatar, "clothes": clothes,
                          "forum_id": forum_id, "fur_color": fur_color,
                          "shaman_color": shaman_color}

                if hasattr(self, "on_player_spawn"):
                    getattr(self, "on_player_spawn")(player)

            elif oldc_cc == (0, 0):
                # ROOM PLAYERS AFTER NEW MAP
                players = {}
                for p_info in packet[1:].split("\x01"):
                    p_info = p_info.split("#")
                    name, mouse_id, dead, score, hascheese, something, title, avatar, clothes, forum_id, fur_color, shaman_color, idk, empty = p_info
                    players[int(mouse_id)] = {"name": name, "dead": dead, "score": score, "hascheese": hascheese,
                                              "title": title, "avatar": avatar, "clothes": clothes,
                                              "forum_id": forum_id, "fur_color": fur_color,
                                              "shaman_color": shaman_color}

                    if hasattr(self, "on_room_player_list"):
                        getattr(self, "on_room_player_list")(players)

        if c_cc == (0, 0):
            # CHAT MESSAGE
            user_id, packet = self.unpack_data('i', packet)
            name, packet = self.unpack_data('s', packet)
            a_byte, packet = self.unpack_data('b', packet)
            message, packet = self.unpack_data('s', packet)
            if hasattr(self, "on_room_message"):
                getattr(self, "on_room_message")(user_id, name, message)

        elif c_cc == (0, 0):
            # ADMIN SERVER MESSAGE
            a_byte, packet = self.unpack_data('b', packet)
            name, packet = self.unpack_data('s', packet)
            message, packet = self.unpack_data('s', packet)
            if hasattr(self, "on_admin_message"):
                getattr(self, "on_admin_message")(name, message)

        elif c_cc == (0, 0):
            # SUCCESSFULLY LOGGED ON
            player_id, packet = self.unpack_data("i", packet)
            bot_name, packet = self.unpack_data("s", packet)
            time_played, packet = self.unpack_data("i", packet)
            community, packet = self.unpack_data("b", packet)
            temp_player_id, packet = self.unpack_data("i", packet)
            mod_level, packet = self.unpack_data("b", packet)
            public_staff, packet = self.unpack_data("b", packet)
            levels, packet = self.unpack_data("b", packet)  # Total amount of levels that exists in your account
            if hasattr(self, "on_login"):
                getattr(self, "on_login")(player_id, bot_name, time_played, community, temp_player_id, mod_level,
                                          public_staff, levels)

        elif c_cc == (0, 0):
            # FINGERPRINT
            online_mice, packet = self.unpack_data('i', packet)
            self.tfm_connection_data["fingerprint"], packet = packet[0], packet[1:]
            community, packet = self.unpack_data("s", packet)
            language, packet = self.unpack_data("s", packet)
            key, packet = self.unpack_data("i", packet)
            # logger.info("[FINGERPRINT] Currently %s mice online, I am in %s community and I use %s language" %
            #            (online_mice, community.upper(), language.upper()))
            self.loops["pingmain"] = LoopingCall(self.ping)
            self.loops["pingmain"].start(15)
            self.login(key)

        elif c_cc == (0, 0):
            # SERVER MESSAGE
            something, packet = self.unpack_data("h", packet)
            string, packet = self.unpack_data("s", packet)
            regex = re.compile("</?[A-Z]?[A-Z]?[A-Z]?[A-Z]?>")
            string = regex.sub("", string)
            if string.startswith("$ModoEnLigne"):
                string = string.replace("$ModoEnLigne", "")
                what = "mods"
            elif string.startswith("$ModoPasEnLigne"):
                string = string.replace("$ModoPasEnLigne", "There aren't any mods online.")
                what = "mods"
            elif string.startswith("$MapcrewEnLigne"):
                string = string.replace("$MapcrewEnLigne", "")
                what = "mapcrew"
            elif string.startswith("$MapcrewPasEnLigne"):
                string = string.replace("$MapcrewPasEnLigne", "There aren't any Map Crew online.")
                what = "mapcrew"
            else:
                what = "unknown"
            if hasattr(self, "on_server_message"):
                getattr(self, "on_server_message")(what, string)

        elif c_cc == (0, 0):
            # SERVER RESTART
            ms, packet = self.unpack_data('i', packet)
            if hasattr(self, "on_server_restart"):
                getattr(self, "on_server_restart")(ms)

        elif c_cc == (0, 0):
            # LUA PRINT
            text, packet = self.unpack_data("s", packet)
            text = text.split("<BL> ")[1]
            if hasattr(self, "on_lua_print"):
                getattr(self, "on_lua_print")(text)

        elif c_cc == (0, 0):
            # BULLE IP
            key, packet = self.unpack_data('i', packet)
            bulle_ip, packet = self.unpack_data("s", packet)
            if hasattr(self, "got_room_address"):
                getattr(self, "got_room_address")(bulle_ip, key)

                # logger.info("[BULLE IP] %s" % self.bulleIP)

        elif c_cc == (0, 0):
            # BULLE FP
            self.tfm_connection_data["b_fingerprint"] = packet[0]
            self.loops["pingbulle"] = LoopingCall(self.ping)
            self.loops["pingbulle"].start(15)

        elif c_cc == (0, 0):
            # TRIBULLE
            code, packet = self.unpack_data('h', packet)
            log.debug("[IN] Tribulle code: %s" % code)
            if code == self.tribulle["JoinPublicChatSignal"]:
                # OPENED CHAT TAB
                chat_id, packet = self.unpack_data('i', packet)
                chat_name, packet = self.unpack_data('s', packet)
                # logger.info("[OPENED CHAT TAB] I joined %s chatroom" % chat_name.capitalize())
                if hasattr(self, "on_join_chatroom"):
                    getattr(self, "on_join_chatroom")(chat_id, chat_name)

            elif code == self.tribulle['ChatMessageSignal']:
                # CHAT MESSAGE
                # 64 '\x00\x04ediz\x00\x00\x00\x07\x00\x11testchannelblabla\x00\x04test'
                name, packet = self.unpack_data("s", packet)
                community, packet = self.unpack_data("i", packet)
                channel, packet = self.unpack_data("s", packet)
                message, packet = self.unpack_data("s", packet)
                if hasattr(self, "on_chat_message"):
                    getattr(self, "on_chat_message")(name, community, channel, message)

            elif code == self.tribulle["TribeMessageSignal"]:
                chat_name, packet = self.unpack_data('s', packet)
                message, packet = self.unpack_data('s', packet)
                if hasattr(self, "on_tribe_message"):
                    getattr(self, "on_tribe_message")(chat_name, message)

            elif code == self.tribulle["PrivateMessageSignal"]:
                # PRIVATE MESSAGE
                # [IN] (60, 0): '\x00B\x00\tediz#0095\x00\x00\x00\x07\x00\x0bedizzy#0000\x00\x04test'
                # [6:38 PM] Pikashu: Its structure is : author, id of the author's community (int), recipient, message
                sender, packet = self.unpack_data('s', packet)
                community, packet = self.unpack_data('i', packet)
                receiver, packet = self.unpack_data('s', packet)
                message, packet = self.unpack_data('s', packet)
                if hasattr(self, "on_private_message"):
                    getattr(self, "on_private_message")(sender, receiver, community, message)

            elif code == self.tribulle["TribeMemberConnectionSignal"]:
                name, packet = self.unpack_data('s', packet)
                if hasattr(self, "on_tribe_connect"):
                    getattr(self, "on_tribe_connect")(name)

            elif code == self.tribulle["TribeMemberDisconnectionSignal"]:
                name, packet = self.unpack_data('s', packet)
                if hasattr(self, "on_tribe_disconnect"):
                    getattr(self, "on_tribe_disconnect")(name)

            elif code == self.tribulle["TribeMemberJoinedSignal"]:
                # TRIBE MEMBER JOINED
                name, packet = self.unpack_data('s', packet)
                if hasattr(self, "on_tribe_join"):
                    getattr(self, "on_tribe_join")(name)

            elif code == self.tribulle["TribeMemberLeftSignal"]:
                # TRIBE MEMBER QUIT
                name, packet = self.unpack_data('s', packet)
                if hasattr(self, "on_tribe_quit"):
                    getattr(self, "on_tribe_quit")(name)

            elif code == self.tribulle["TribeMemberExcludedSignal"]:
                # TRIBE MEMBER KICKED
                kicked_person, packet = self.unpack_data('s', packet)
                who_kicked, packet = self.unpack_data('s', packet)
                if hasattr(self, "on_tribe_kick"):
                    getattr(self, "on_tribe_kick")(kicked_person, who_kicked)

            elif code == self.tribulle["TribeParametersChangeSignal"]:
                # TRIBE INFO
                tribe_id, packet = self.unpack_data("i", packet)
                tribe_name, packet = self.unpack_data("s", packet)
                welcome_message, packet = self.unpack_data("s", packet)
                tribe_house_code, packet = self.unpack_data("i", packet)
                total_members, packet = self.unpack_data("h", packet)

                tribe = {
                    "id": tribe_id,
                    "name": tribe_name,
                    "welcome message": welcome_message,
                    "tribecode": tribe_house_code
                }
                members = {}
                ranks = {}

                for i in range(total_members):
                    player_id, packet = self.unpack_data("i", packet)
                    player_name, packet = self.unpack_data("s", packet)
                    gender_id, packet = self.unpack_data("b", packet)
                    avatar_id, packet = self.unpack_data("i", packet)
                    last_connection, packet = self.unpack_data("i", packet)
                    rank_id, packet = self.unpack_data("i", packet)
                    game, packet = self.unpack_data("b", packet)
                    room_name, packet = self.unpack_data("s", packet)
                    members[player_name] = {"player id": player_id,
                                            "gender_id": gender_id,
                                            "avatar": avatar_id,
                                            "rank id": rank_id,
                                            "last connection": last_connection,
                                            "game": game,
                                            "room": room_name}

                total_ranks, packet = self.unpack_data("h", packet)

                for i in range(total_ranks):
                    rank_name, packet = self.unpack_data("s", packet)
                    rank_ids, packet = self.unpack_data("i", packet)
                    ranks[rank_name] = rank_ids

                if hasattr(self, "on_tribe_list"):
                    getattr(self, "on_tribe_list")(tribe, members, ranks)

            elif code == self.tribulle["ChangeTribeWelcomeMessageSignal"]:
                # TRIBE GREETING CHANGE
                name, packet = self.unpack_data("s", packet)
                text, packet = self.unpack_data("s", packet)
                if hasattr(self, "on_tribe_greeting_change"):
                    getattr(self, "on_tribe_greeting_change")(name, text)

    @staticmethod
    def passwordhash(password):
        # Code emitted for security
        a = base64.b64encode(hashlib.sha256("1234"))
        return struct.pack("!h", len(a)) + a

    def connect(self):
        """
        The first packet you send to start communicating with TFM servers.
        """
        # Code emitted for security
        data = ""
        self.send(chr(0), chr(0), "Connection packet", data)

    def connect_bulle(self, key):
        """
        Connect to the room server you requested
        """
        self.send(chr(0), chr(0), "Bulle Connection packet", self.pack_data("i", key))

    def login(self, key):
        """
        The login packet - to actually log in with your user creditentials.
        """
        url = "http://www.transformice.com/Transformice.swf?n=1344518439676"
        try:
            # Code emitted for security
            data = ""
        except AttributeError:
            raise errors.UserCredentialMissing("Please enter username, password and a default room to connect.")
        self.send(chr(0), chr(0), "Login packet", data)

    def ping(self):
        """
        The ping packet - for telling the server to keep the connection open
        """
        self.send(chr(0), chr(0), "Ping packet")

    def send_channel_message(self, cid, message):
        """
        Sends a channel Message. This also is the function for sending tribe messages.

        :param cid: The channel ID of the channel
        :param message: The message you want to send
        """
        data = self.pack_data("hiis", self.tribulle["ST_EnvoitMessageCanal"],
                              self.tfm_connection_data["tribulleIncrement"], cid, message)
        self.tfm_connection_data["tribulleIncrement"] += 1
        self.send(chr(0), chr(0), "Channel message packet", data)

    def join_chat(self, chat_name):
        data = self.pack_data("hisb", self.tribulle["JoinPublicChat"], self.tfm_connection_data["tribulleIncrement"],
                              chat_name, 1)
        self.tfm_connection_data["tribulleIncrement"] += 1
        self.send(chr(0), chr(0), "Join chat packet", data)

    def send_chat_message(self, chat_name, message):
        data = self.pack_data("hiss", self.tribulle["SendChatMessage"], self.tfm_connection_data["tribulleIncrement"],
                              chat_name, message)
        self.tfm_connection_data["tribulleIncrement"] += 1
        self.send(chr(0), chr(0), "Chatroom message packet", data)

    def send_tribe_message(self, message):
        data = self.pack_data("his", self.tribulle["SendTribeMessage"],
                              self.tfm_connection_data["tribulleIncrement"], message)
        self.tfm_connection_data["tribulleIncrement"] += 1
        self.send(chr(0), chr(0), "Channel message packet", data)

    def send_private_message(self, name, message):
        """
        Sends a private message to an user.
        :param name: The recipient of the message
        :param message:  The message itself
        """
        data = self.pack_data("hiss", self.tribulle["SendPrivateMessage"], self.tribulle["SendPrivateMessage"], name,
                              message)
        self.send(chr(0), chr(0), "Private message packet", data)

    def send_room_message(self, message):
        """
        Sends a room message to room chat.
        :param message: The message you want to send
        """
        data = self.pack_data("sb", message, 32)
        self.send(chr(0), chr(0), "Room message packet", data)

    def send_command(self, cmd):
        data = self.pack_data("s", cmd)
        self.send(chr(0), chr(0), "Command packet", data)

    def join_tribehouse(self):
        """
        Joins the bot's tribe house.
        """
        self.send(chr(0), chr(0), "Join TH packet")

    def request_tribe_members_list(self):
        """
        Request the members of the tribe the bot is currently in.
        """
        data = self.pack_data("hib", self.tribulle["OpenTribeInterface"], self.tfm_connection_data["tribulleIncrement"],
                              1)
        self.tfm_connection_data["tribulleIncrement"] += 1
        self.send(chr(0), chr(0), "Tribe member list request", data)

    def send_emote(self, emote, flag="tr", player_id=0):
        if emote == 10:
            data = self.pack_data("bis", emote, player_id, flag)
        else:
            data = self.pack_data("bi", emote, player_id)
        self.send(chr(0), chr(0), "Emote packet", data)

    def send_lua(self, script):
        try:
            url = "http://pastebin.com/raw.php?i=%s" % script.replace("http://", "").replace("https://", "").split("/")[
                1]
            udata = urllib2.urlopen(url, timeout=5)
        except urllib2.URLError:
            raise urllib2.URLError("Failed to connect pastebin / Incorrect ID / You're trying to kill the bot.")
        data = self.pack_data("bs", 0, udata.read())
        udata.close()
        self.send(chr(0), chr(0), "Load lua packet", data)

    def send_attach_balloon(self, pid):
        data = self.pack_data("b.bi", 1, str(pid), 1, pid)
        self.send(chr(0), chr(0), "Attach balloon packet", data, True)