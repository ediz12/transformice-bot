# coding=utf-8

import json
import logging
import random
import time
from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from transformice.factory import Factory, FactoryHandler
from transformice.bridge import BridgeProtocol
from transformice.tfm import TFMProtocol
from transformice.TFMData import TFMData
from cleverwrap import CleverWrap
import hashlib
# from utils.riddler import Riddler

log = logging.getLogger()
log.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(asctime)s][%(levelname)s] %(message)s', datefmt="%d-%m-%Y|%H:%M:%S")

file_handler = logging.FileHandler("TFMlogs/%s" % time.strftime("%Y-%m-%d %H-%M-%S"))
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
log.addHandler(file_handler)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(formatter)
log.addHandler(stream_handler)


# noinspection PyMethodMayBeStatic
class TFMBot(TFMProtocol):
    """
    TFMBot application itself
    """

    def __init__(self, *args, **kwargs):
        TFMProtocol.__init__(self, *args, **kwargs)
        self.factorylist = kwargs["factorylist"]
        self.username = "username"
        self.password = "password"
        self.player_bot = True
        self.room = "*dizzy bootcamp"
        self.requests = {"tribe_otfm": False, "stafflist": False}
        self.loops = {}
        self.staff_list = {"mods": {}, "mapcrew": {}}
        self.chat_list = {}
        self.td = self.get_tfm_info()
        self.cb = CleverWrap("clever_key")

    def get_tfm_info(self):
        with open("transformice/tfminfo.json") as f:
            return json.load(f)

    def save_tfm_info(self):
        with open("transformice/tfminfo.json", "w") as f:
            json.dump(self.td, f, sort_keys=True, indent=2)

    def save_staff_api(self):
        try:
            with open("/home/edizzy12/www/riddlematic.com/html/staff.json", "w") as f:
                json.dump(self.staff_list, f, sort_keys=True, indent=2)
        except:
            pass

    def get_chat_list(self):
        return self.chat_list

    def get_protocol(self, which):
        self.factorylist.get_factory_protocol(which)

    def on_connection_made(self, name):
        def api_checker():
            self.send_command("mod")
            reactor.callLater(1, self.send_command, "mapcrew")

        self.loops["api checker"] = LoopingCall(api_checker)
        self.loops["api checker"].start(60)
        reactor.callLater(2.5, self.join_chat, "#help")
        reactor.callLater(3.5, self.join_chat, "#dm-help")

    def on_connection_lost(self, name):
        if name == "transformice":
            for name, loop in self.loops.iteritems():
                loop.stop()

    def on_login(self, player_id, bot_name, time_played, community, temp_player_id, mod_level, public_staff, levels):
        log.info("I am online!")
        reactor.callLater(5, self.join_tribehouse)
        self.send_command("chat ediztest")

    def got_room_address(self, ip, key):
        if "bulle" in self.factorylist.factories:
            self.factorylist.factories["bulle"].stop_connection()
            self.factorylist.factories["bulle"].connector.disconnect()
        self.factorylist.add_factory("bulle", Factory(TFMBot, ip, 44444, key, data=self.factorylist.tfm_data,
                                                      factorylist=self.factorylist))
        self.factorylist.start_factory("bulle")

    def on_join_chatroom(self, chat_id, chat_name):
        if chat_name.lower() == "~too cute to be real":
            chat_name = "tribe"

        self.chat_list[chat_name] = chat_id

    def on_tribe_message(self, name, message):
        message = message.replace("&lt;", "<").replace("&amp;", "&")
        name, id = name.split("#")

        log.info("[TRIBE][%s] %s" % (name, message))
        self.bridge_chat_message(name, message, "tribe")
        if message.startswith("!"):
            args = message[1:].split()
            request = args[0].lower()

            if request in ["odiscord", "od"]:
                self.get_online_discord()

            elif request in ["otfm", "ot"]:
                self.request_tribe_members_list()
                self.requests["tribe_otfm"] = True

            elif request == "8ball":
                self.send_tribe_message(self.eightball(args[1:]))

            elif request == "omsg":
                self.send_tribe_message(self.add_offline_message(name, message))

            elif request == "tw" and name.lower() in self.td["leaders"]:
                self.send_tribe_message(self.change_tribe_welcome(message))

        else:
            if message.lower().startswith("dizzy,"):
                self.send_tribe_message(self.cb.say(message.replace("dizzy,", "")).encode("utf8"))

    def on_tribe_connect(self, name):
        name, id = name.split("#")
        message = "%s has connected." % (name.capitalize())
        log.info(message)
        self.bridge_chat_message("Server", str(message), "tribe")

        try:
            greet = random.choice(self.td["greets"][name.lower()])
        except KeyError:
            greet = random.choice(self.td["greets"]["tribe"])

        self.send_tribe_message(("%s ❤".decode("utf8") % greet).encode("utf8"))

        if name.lower() in self.td["offline-messages"]:
            text = "You have following messages from tribe:\n"
            for msg in self.td["offline-messages"][name.lower()]:
                text += msg + "\n"
            self.remove_offline_message(name.lower())
            self.send_private_message(name, str(text))

    def on_tribe_disconnect(self, name):
        message = "%s has disconnected." % (name.capitalize())  # self.td["gameIDs"][str(game_id)]
        log.info(message)
        self.bridge_chat_message("Server", str(message), "tribe")

    def on_tribe_join(self, name):
        message = "%s has joined the tribe." % name.capitalize()
        log.info(message)
        self.bridge_chat_message("Server", message, "tribe")

    def on_tribe_quit(self, name):
        message = "%s has left the tribe." % name.capitalize()
        log.info(message)
        self.bridge_chat_message("Server", message, "tribe")

    def on_tribe_kick(self, kicked_person, who_kicked):
        message = "%s has excluded %s from the tribe." % (who_kicked.capitalize(), kicked_person.capitalize())
        log.info(message)
        self.bridge_chat_message("Server", message, "tribe")

    def on_tribe_greeting_change(self, name, text):
        message = "%s has changed the greeting message:\n %s" % (name.capitalize(), text)
        log.info(message)
        self.bridge_chat_message("Server", message, "tribe")

    def on_tribe_list(self, tribe, members, ranks):
        if self.requests["tribe_otfm"]:
            online = []
            for name, member in members.iteritems():
                # print "%s: %s" % (name, time.strftime("%Z - %Y/%m/%d, %H:%M:%S", time.localtime(member["last connection"] * 60)))
                if member["game"] > 1:
                    online.append(name)
            random.shuffle(online)
            g = random.choice(["Online TFM peeople", "Online TFM peeps", "Online TFM dudes"])
            online = ", ".join(online)
            self.send_tribe_message("%s: %s" % (g, online))
            self.requests["tribe_otfm"] = False

    def on_chat_message(self, name, community, channel, message):
        message = message.replace("&lt;", "<").replace("&amp;", "&")
        name = name.replace("#0000", "") # UNIQUE ID
        community = str(self.td["communityIDs"][str(community - 1)].upper())
        log.info("[%s][%s][%s] %s" % (channel, community, name, message))

        if channel == "help" or channel == "dm-help":
            self.bridge_chat_message(name, "[%s][%s] %s" % (community, name, message), "chat|%s" % channel, "helpers_discord")

        if name.lower() != self.username.lower():
            pass

    def on_room_message(self, user_id, name, message):
        self.bridge_chat_message(name, message, "room")
        log.info("[%s] %s" % (name, message))
        if name.lower() != self.username.lower():
            if message.startswith("!"):
                args = message[1:].split()
                request = args[0].lower()

                if request == "emote" and len(args) > 1:
                    emote = args[1].lower()
                    try:
                        if emote == "flag" and len(args) == 3:
                            self.send_emote(self.td["emoteIDs"][emote], args[2])
                        elif emote == "help":
                            allowed_emotes = ", ".join(self.td["emoteIDs"].keys())
                            self.send_room_message("Allowed emotes: %s" % str(allowed_emotes))
                        else:
                            self.send_emote(self.td["emoteIDs"][emote])
                    except KeyError:
                        self.send_room_message("Unknown emote \"%s\". Type !emote help for a list of emotes." % emote)

                elif request == "testlua":
                    self.send_lua("http://pastebin.com/RtT5jitf")
            else:
                if message.lower().startswith("dizzy,"):
                    self.send_room_message(self.cb.say(message.replace("dizzy,", "")).encode("utf8"))

    def on_private_message(self, sender, receiver, community, message):
        message = message.lower()
        if message == "!mchash":
            priv_key = ": 0k=[yR>4kk9:DUztPb"
            hsh = hashlib.sha1(sender + priv_key).hexdigest()
            msg = "Your key: {0}".format(hsh)
            self.send_private_message(sender, msg)

    def on_server_message(self, what, text):
        if what == "mods" or "mapcrew":
            if self.requests["stafflist"]:
                self.send_stafflist("%s: %s" % (what, text))
            log.debug("Online %s: %s" % (what, text))
            self.staff_list[what] = {}
            if "\n" in text:
                lst = text.split("\n")
                for names in lst[1:]:
                    community, names = names[1:3], names[5:].split(", ")
                    self.staff_list[what][community] = names
            self.save_staff_api()

    def on_server_restart(self, ms):
        text = "[SERVER] The server will restart in %s seconds." % (ms / 1000)
        log.warning(text)
        if (ms / 1000) == 120:
            self.bridge_chat_message("server", text, "server")
            self.bridge_chat_message("server", text, "server", "bot_discord")

    def on_admin_message(self, name, message):
        text = "[ADMIN MESSAGE][%s] %s" % (name.capitalize(), message)
        log.info(text)
        self.bridge_chat_message("server", text, "server")
        self.bridge_chat_message("server", text, "server", "bot_discord")

    def on_lua_print(self, text):
        text = text.split(":")
        name = text[0]
        for i in self.players:
            if name.lower() == self.players[i]["name"].lower():
                self.send_attach_balloon(i)

    def on_room_player_list(self, players):
        self.players = players

    def bridge_chat_message(self, user, message, chat, to="tribe_discord"):
        try:
            bridge = self.factorylist.get_factory_protocol("bridge")
            bridge.send_message(to, user, message, chat)
        except Exception as e:
            log.error("Bridge chat message: %s" % e)

    def get_online_discord(self):
        try:
            bridge = self.factorylist.get_factory_protocol("bridge")
            bridge.send_get_online_tribe("tribe_discord", "get")
        except Exception as e:
            self.send_tribe_message("Main server is not up, sorry :(")
            log.error("Odiscord: %s" % e)

    def send_stafflist(self, text):
        try:
            self.requests["stafflist"] = False
            bridge = self.factorylist.get_factory_protocol("bridge")
            bridge.send_stafflist_request(text)
        except Exception as e:
            log.error("Stafflist: %s" % e)

    def eightball(self, args):
        yes = ['It is certain', 'It is decidedly so', 'Without a doubt', 'Yes, definitely', 'You may rely on it',
               'As I see it, yes', 'Most likely', 'Outlook good', 'Yes', 'Signs point to yes']
        maybe = ['Reply hazy try again', 'Ask again later', 'Better not tell you now', 'Cannot predict now',
                 'Concentrate and ask again']
        no = ["Don't count on it", 'My reply is no', 'My sources say no', 'Outlook not so good', 'Very doubtful']

        l = len(args)
        if l % 3 == 0:
            return random.choice(yes)
        elif l % 3 == 1:
            return random.choice(maybe)
        else:
            return random.choice(no)

    def add_offline_message(self, frm, text):
        try:
            to, text = text.split()[1].lower(), " ".join(text.split()[2:])
        except (ValueError, IndexError):
            return "Usage: !omsg <name> <text>"

        if text == "":
            return "Please specify a message you want to send to the user."

        try:
            self.td["offline-messages"][to]
        except KeyError:
            self.td["offline-messages"][to] = []
        finally:
            if len(self.td["offline-messages"]) < 5:
                self.td["offline-messages"][to].append("%s: %s" % (frm.capitalize(), text))
            else:
                return "Maximum amount of offline messages (5) exceed. :("

        self.save_tfm_info()
        return "Added offline message for %s! :)" % to

    def remove_offline_message(self, name):
        self.td["offline-messages"].pop(name.lower())
        self.save_tfm_info()

    def change_tribe_welcome(self, text):
        try:
            text = text.split()
            action, name, text = text[1], text[2], " ".join(text[3:])
        except (ValueError, IndexError):
            return "Usage: !tw <action> <name> <text>"

        if text == "":
            return "Please specify a message you want to send to the user."

        if action == "add":
            name = name.lower()
            try:
                self.td["greets"][name]
            except KeyError:
                self.td["greets"][name] = []
            finally:
                if len(self.td["greets"][name]) < 25:
                    self.td["greets"][name].append(text)
                else:
                    return "Maximum amount of welcome messages (25) exceed. :("

        else:
            return "Unknown action %s." % action

        self.save_tfm_info()
        return "Successfully added a new welcome message for %s! :)" % name


class Bridge(BridgeProtocol):
    """
    Bridge application itself
    """

    def __init__(self, *args, **kwargs):
        BridgeProtocol.__init__(self, *args, **kwargs)

    def on_bridge_chat_message(self, name, message, chat):
        message = "[D][%s] %s" % (name, message)
        try:
            if chat == "tribe":
                tfm = self.factorylist.get_factory_protocol("transformice")
                tfm.send_tribe_message(message)
            elif chat == "room":
                bulle = self.factorylist.get_factory_protocol("bulle")
                bulle.send_room_message(message)

            elif chat == "chat|help":
                tfm = self.factorylist.get_factory_protocol("transformice")
                tfm.send_chat_message("help", message)

            elif chat == "chat|dm-help":
                tfm = self.factorylist.get_factory_protocol("transformice")
                tfm.send_chat_message("dm-help", message)

        except (KeyError, AttributeError):
            self.send_chat_message_failed("tribe_discord", chat)

    def on_bridge_chat_failed(self, err, chat):
        if err == "0":
            err = "Error: Discord bot is not online."
        elif err == "1":
            err = "Discord bot is online, but no connection was established with Discord servers."

        log.error(err)

    def on_tribe_online_request(self, res):
        if res == "get":
            try:
                tfm = self.factorylist.get_factory_protocol("transformice")
                tfm.requests["tribe_otfm"] = True
                tfm.request_tribe_members_list()
            except KeyError:
                self.send_get_online_tribe("tribe_discord", "1")
        else:
            tfm = self.factorylist.get_factory_protocol("transformice")
            if res == "0":
                tfm.send_tribe_message("Discordbot not online :(")
            elif res == "1":
                tfm.send_tribe_message("Discordbot online, but no connection was found. :(")
            else:
                res = res.split(", ")
                random.shuffle(res)
                res = ", ".join(res)
                # Randomized due to repeated text being considered as spam
                omsg = random.choice(["Online people", "Online peeps", "Discord peeps", "Online discord dudes"])
                tfm.send_tribe_message("%s: %s" % (omsg, res))

    def on_stafflist_request(self, res):
        try:
            tfm = self.factorylist.get_factory_protocol("transformice")
            if res == "mods":
                tfm.requests["stafflist"] = True
                tfm.send_command("mod")
            elif res == "mapcrew":
                tfm.requests["stafflist"] = True
                tfm.send_command("mapcrew")
        except KeyError:
            self.send_stafflist_request("%s:1" % res)


class FactoryList(FactoryHandler):
    def __init__(self):
        super(FactoryList, self).__init__()
        self.dUrl2 = "http://api... Removed for security"
        self.dUrl = "http://api... Removed for security"
        self.tfm_data = TFMData(self.dUrl, self.dUrl2)
        self.add_factory("transformice",
                         Factory(TFMBot, "164.132.202.12", 44444, data=self.tfm_data,
                                 factorylist=self))  # use self.tfm_data.data["ip"] after fixing
        self.add_factory("bridge", Factory(Bridge, "localhost", 12122, factorylist=self))

    def start(self):
        self.start_factories()
        reactor.run()


FactoryList().start()
