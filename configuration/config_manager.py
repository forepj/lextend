# Lextend
# Copyright (c) 2014-2015 Egger Enertech <http://www.egger-enertech.ch>
# Released under the GNU Public License 3 (or higher, your choice)
# See the file COPYING for details.

import os
from xmlsettings import XMLSettings
from lxml import etree

import pyinotify

import logging

import time

class dummy: pass

class EventHandler(pyinotify.ProcessEvent):
  """ This class is used by inotify to handle filesystem changes events.
  """
  def __init__(self, configManagerInstance):
    super(EventHandler, self).__init__()
    self.configManagerInstance = configManagerInstance

  def process_IN_CLOSE_WRITE(self, event):
    """ This is a callback handler. Used to handle filesystem events.

      It will check for the config_filename CREATED and MODIFIED events,
      and reload the configuration in such cases.
    """
    if self.configManagerInstance.config_filename in event.pathname:
      self.configManagerInstance.loadfile()

class ConfigManager():
  """ This class is used to read, write, reset the global config,

    It is used by sonosdoorbell service and by webfrontend.

    Configuration is stored in an XML file.
    Configuration is autoloaded when a file change is detected.

    NOTE: When an exception occurs, the configuration is generally reset
          and is saved again to the XML file. A backup is also created.
  """

  def __init__(self, config_subdir, config_filename, lextend_ip, logger=None):
    """ ConfigManager initializer.

      This function will ensure that folder structure is created.
      It will load (and save to ensure consistency in case of errors) the XML.
      It will then start watching the config_file for changes.
    """
    self.lextend_ip = lextend_ip
    self.logger = logger or logging.getLogger(__name__)

    self.config_filename = None
    config_userconfig = os.path.join("/root",
                                     ".config", config_subdir, config_filename)

    # Make sure config_file exists in the config directory.
    try:
      if not os.path.exists(config_userconfig):
        try:
          conf_dir = os.path.dirname(config_userconfig)
          os.makedirs(conf_dir)
        except:
          self.logger.error("Cannot create %s." % conf_dir, exc_info=True)
      self.config_filename = config_userconfig
    except:
      self.logger.error("Could not ensure %s exists." % config_userconfig,
                        exc_info=True)

    # Try to load and save the config file : enforce consistency.
    self.loadfile()
    self.save()

    # Start watching the config file for changes.
    try:
      self.wm = pyinotify.WatchManager()
      mask = pyinotify.IN_CLOSE_WRITE
      self.notifier = pyinotify.ThreadedNotifier(self.wm, EventHandler(self))
      self.notifier.start()
      self.wdd = self.wm.add_watch(os.path.dirname(self.config_filename),
                                   mask,
                                   rec=True)
    except:
      self.logger.error("Could not start observe on %s" % self.config_filename,
                        exc_info=True)

  def loadfile(self):
    """ Load config from the XML file, and reset and save in case of error.
    """
    self.logger.info("Loading settings from %s." % self.config_filename)
    try:
      self.config = XMLSettings(self.config_filename)
    except:
      self.logger.error("Could not load Config from %s." % self.config_filename,
                        exc_info=True)
      self.reset()
      self.save()
    self.load()

  def load(self):
    """ Load settings from the config file.
    """

    def load_general():
      section = "General"

      # Prepare the structures
      self.general = dummy()
      self.general.lextend = dummy()
      self.general.miniserver = dummy()

      # read the settings
      lextend_ip = "192.168.0.231"
      if self.lextend_ip != "":
        lextend_ip = self.lextend_ip
      self.general.lextend.ip = self.config.get(section + "/Lextend/ip",
                                                lextend_ip)
      self.general.lextend.port = self.config.get(section + "/Lextend/port",
                                                  "5050")

      self.general.miniserver.ip = self.config.get(section + "/Miniserver/ip",
                                                   "192.168.0.230")
      self.general.miniserver.port = self.config.get(section + "/Miniserver/port",
                                                     "5050")

    def load_sonos_doorbell():
      section = "Services/Sonos_Doorbell"

      # Prepare the structures
      self.sonos_doorbell = dummy()

      tmp = self.config.get(section + "/enable", "True")
      self.sonos_doorbell.enable = True if "True" in tmp else False
      tmp = self.config.get(section + "/volume_override", "False")
      self.sonos_doorbell.volume_override = True if "True" in tmp else False
      self.sonos_doorbell.volume = self.config.get(section + "/volume", 50)
      self.sonos_doorbell.default_sound = self.config.get(section + "/default_sound", 1)

      self.sonos_doorbell.sounds_filelist = []
      for i in range(10):
        key = section + "/Sounds/sound_%s" % i
        self.sonos_doorbell.sounds_filelist.append(self.config.get(key, "default sound"))

      self.sonos_doorbell.protocol = self.config.get(section + "/Protocol",
                                                     "10!x1")

    load_general()
    load_sonos_doorbell()

  def save(self):
    """ Save settings to the config file.
    """
    self.logger.info("Saving Config to %s." % self.config_filename)

    def put_general():
      section = "General"
      self.config.put(section + "/version", "1")

      self.config.put(section + "/Lextend/ip", self.general.lextend.ip)
      self.config.put(section + "/Lextend/port", self.general.lextend.port)

      self.config.put(section + "/Miniserver/ip", self.general.miniserver.ip)
      self.config.put(section + "/Miniserver/port", self.general.miniserver.port)

    def put_sonos_doorbell():
      section = "Services/Sonos_Doorbell"
      self.config.put(section + "/enable", str(self.sonos_doorbell.enable))
      self.config.put(section + "/volume_override",
                      str(self.sonos_doorbell.volume_override))
      self.config.put(section + "/volume", self.sonos_doorbell.volume)
      self.config.put(section + "/default_sound", self.sonos_doorbell.default_sound)

      for i in range(10):
        self.config.put(section + "/Sounds/sound_%s" % i, self.sonos_doorbell.sounds_filelist[i])

      self.config.put(section + "/Protocol", self.sonos_doorbell.protocol)

    put_general()
    put_sonos_doorbell()

    try:
      self.config.save()
    except:
      self.logger.error("Could not save settings.", exc_info=True)

    # Lazy attempt to solve the bug with using config before it is loaded again;
    time.sleep(0.5)

  def remove_xml_element(self, element_name):
    try:
      f = open(self.config_filename, "rw")
      tree = etree.parse(f)
      f.close()

      for element in tree.xpath("//%s" % element_name):
        element.getparent().remove(element)

      fi = open(self.config_filename, "r+w")
      fi.write(etree.tostring(tree))
    except:
      self.logger.error("While removing %s in %s" % (element_name,
                                                     self.config_filename),
                        exc_info=True)


  def reset_service(self, service_name):
    self.remove_xml_element(service_name)
    self.load()
    self.save()

  def reset_general(self):
    self.reset_service("General")

  def reset_sonos_doorbell(self):
    self.reset_service("Sonos_Doorbell")

  def reset(self):
    """ Reset settings and save them to the XML config file.
    """
    self.logger.info("Resetting Config to %s" % self.config_filename)
    try:
      os.rename(self.config_filename, "%s.bak" % self.config_filename)
      self.logger.info("Config file backed up to %s.bak" % self.config_filename)
    except:
      self.logger.warn("reset", exc_info=True)
    try:
      self.config = XMLSettings(self.config_filename)
    except:
      self.config = XMLSettings("")
      self.logger.warn("reset", exc_info=True)
    self.load()
    self.save()
