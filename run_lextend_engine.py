#!/usr/bin/env python2

# Lextend
# Copyright (c) 2014-2015 Egger Enertech <http://www.egger-enertech.ch>
# Released under the GNU Public License 3 (or higher, your choice)
# See the file COPYING for details.


import socket
import traceback

from configuration import ConfigManager
from sonosdoorbell import SonosPoolManager
from sonosdoorbell import SonosDeviceManager

from utils.settings import *
from utils.sounds_utils import *
from utils.ip_utils import *

from threading import Thread
import rpyc
from rpyc.utils.server import ThreadedServer

from time import sleep

from Queue import Queue
import re

import logging
import logging.handlers

logger = logging.getLogger()
LOG_FILENAME = "/var/log/lextend.engine.log"
handler = logging.handlers.RotatingFileHandler(LOG_FILENAME, mode="a",
                                               maxBytes=1024*1024*1,
                                               backupCount=5)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
handler.setLevel(logging.INFO)
if logger.handlers:
    for handler in logger.handlers:
              logger.removeHandler(handler)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

class RPC_Server(Thread):
  """ Wrapper used to run RPC service in a separate thread.
  """
  def __init__(self, sonosManagerInstance):
    Thread.__init__(self)
    self.sonosManagerInstance = sonosManagerInstance
  def run(self):
    thread = ThreadedServer(RPC_Service(self.sonosManagerInstance),
                            port=RPC_PORT,
                            protocol_config={"allow_public_attrs":True})
    thread.start()

def RPC_Service(sonosManagerInstance):
  """ Closure used to pass arguments to RPC_Service_Class(rpyc.Service)
  """
  class RPC_Service_Class(rpyc.Service):
    """ RPC service class, used to expose interfaces and objects to webfrontend.
    """
    def on_connect(self):
      pass

    def on_disconnect(self):
      pass

    def exposed_get_sonosPoolManager(self):
      return sonosManagerInstance

  return RPC_Service_Class

def parseExtensionProtocol(data, cfg):
  """ Parse miniserver udp packet and return parsed data.

  Packet format: HEADER + PARAMETERS

  DoorBell Packet format: HEADER + SOUND + VOLUME
    HEADER : a string of any length
    SOUND  : 1 CHAR, ascii, 1..9
    VOLUME : 1 CHAR, ascii, 1..9

  Args:
      data (str): Input packet.
      cfg (str): configuration instance, it contains expected headers.

  Returns:
    {"type":"", "params":(parameters)} if successful, None otherwise.
    Examples:
      {"type":"sonos_doorbell", [sound, volume]}
  """
  if data.startswith(cfg.sonos_doorbell.protocol):
    header_len = len(cfg.sonos_doorbell.protocol)
    try:
      args_sound = int(data[header_len])
      if not (1 <= args_sound <= 9):
        return None
      args_volume = int(data[header_len+1])
      if not (1 <= args_volume <= 9):
        return None
    except:
      return None

    return {"type":"sonos_doorbell", "params":[args_sound, args_volume]}

  # unknown protocol
  else:
    return None

class LextendEngine(object):
  def __init__(self, logger=None):
    self.logger = logger or logging.getLogger(__name__)
    self.logger.info("Starting Lextend Engine.")

    # Load configuration from XML file
    try:
      local_ip = get_local_ip()
    except:
      local_ip = ""
    self.cfg = ConfigManager(CONFIGURATION_SUBDIRECTORY,
                             CONFIGURATION_FILENAME,
                             lextend_ip = local_ip)

    # Create a sonos manager
    self.sonosPoolManager = SonosPoolManager()
    try:
      self.sonosPoolManager.discover()
    except:
      self.logger.error("Could not start discovering Sonos.")

    # Create a sounds manager
    self.soundsManager = SoundsManager(CONFIGURATION_SUBDIRECTORY)

    # Expose some RPC interfaces for webfrontend
    self.rpc_server_thread = RPC_Server(self.sonosPoolManager)
    self.rpc_server_thread.start()

    # Get aria ip address
    while True:
      Lextend_ip_address = get_local_ip()
      if Lextend_ip_address == "":
        self.logger.error("FATAL: Cannot get my IP address. Retrying in 10s.")
        sleep(10)
      else:
        self.logger.info("Detected IP address : %s" % Lextend_ip_address)
        break
    self.CIFS_HEADER = "x-file-cifs://" + Lextend_ip_address + "/sonos_share/"

    # Start listening to miniserver.
    self.sock = None
    while self.sock == None:
      try:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", UDP_PORT))
      except Exception:
        # NOTE : the common error is : 98 : address already in use.
        self.logger.error("Failed to create socket, retrying in 10 seconds.", exc_info=True)
        sleep(10)

  def run(self):
    self.socket_receiver_thread = Thread(target=self.socket_receiver, args=())
    self.socket_receiver_thread.setDaemon(True)
    self.socket_receiver_thread.start()

    # Threads shouldn't stop
    self.socket_receiver_thread.join()

  def socket_receiver(self):
    self.logger.info("Started listening on UDP port %s" % UDP_PORT)
    while True:
      data, addr = self.sock.recvfrom(UDP_PORT)
      try:
        ret = parseExtensionProtocol(data, self.cfg)
        if ret:
          if ret["type"] in "sonos_doorbell":
            if self.cfg.sonos_doorbell.enable:
              sound = ret["params"][0]
              volume = ret["params"][1]
              # Calculate volume percentage from protocol input.
              volume = volume * 11            # [0,9] => [0-100]
              # Apply configured volume override.
              if self.cfg.sonos_doorbell.volume_override:
                volume = self.cfg.sonos_doorbell.volume
              # Search for the sound in uploads and fallback to defaults.
              if self.cfg.sonos_doorbell.default_sound != 0:
                sound = self.cfg.sonos_doorbell.default_sound

              default_sound=True
              if "default sound" != self.cfg.sonos_doorbell.sounds_filelist[sound-1]:
                default_sound=False
              sound_file = self.soundsManager.search_path_by_index(sound,
                                                                  default_sound)
              if sound_file:
                split = os.path.split(sound_file)
                sound_file = os.path.join(os.path.split(split[0])[1], split[1])
                smb_path = self.CIFS_HEADER + sound_file
                self.logger.info("Playing %s, %s, %s." % (sound_file, 
                                                         smb_path,
                                                         volume))
                self.sonosPoolManager.pause_play_bell_resume(smb_path, volume)
              else:
                self.logger.error("Couldn't locate a sound @ index : %s" % sound)
            else:
              self.logger.info("SonosDoorbell feature disabled !")
          else:
            self.logger.error("Packet type not known : %s" % ret["type"])
        else:
          self.logger.warn("Can't decode this packet : %s" % data)
      except:
        self.logger.error("In main loop : ", exc_info=True)

def main():
  Lextend_engine = LextendEngine()
  Lextend_engine.run()

if __name__ == "__main__":
  main()
