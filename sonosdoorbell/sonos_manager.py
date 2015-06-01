# Lextend
# Copyright (c) 2014-2015 Egger Enertech <http://www.egger-enertech.ch>
# Released under the GNU Public License 3 (or higher, your choice)
# See the file COPYING for details.

import traceback

import time
import threading

from SoCo import soco

import logging

FADE_OUT_ENABLED          = False

class FuncThread(threading.Thread):
  """ Run a function in a thread.
  """
  def __init__(self, target, *args):
      self._target = target
      self._args = args
      threading.Thread.__init__(self)

  def run(self):
      self._target(*self._args)

class SonosPoolManager():
  """ Handles a pool of Sonos devices
  """
  def __init__(self, logger=None):
    self.logger = logger or logging.getLogger(__name__)

    self.devices_list = []

  def discover(self):
    self.devices_list = []
    discovered = soco.discover()
    if discovered != None:
      for sonos in list(discovered):
        self.logger.info("Discovered sonos : %s." % sonos.ip_address)
        self.devices_list.append(SonosDeviceManager(sonos.ip_address))

  def pause_play_bell_resume(self, uri, volume):
    """ Pause and save state, play uri at the specified volume and resume.
    Args:
      uri (str): uri of the sound to play. Generally the samba share link.
      volume (int): volume at which the sound will be played.
    """
    # pause all in parallel.
    threads = []
    for sonos in self.devices_list:
      t = sonos.pause()
      threads.append(t)
      t.start()
    # Wait for all to pause
    for t in threads:
      t.join()

    self.logger.info("Regrouping for bell.")
    # regroup
    master = self.devices_list[0]
    [zone.device.join(master.device) for zone in self.devices_list if zone is not master]
    # set bell volume everywhere
    for zone in self.devices_list:
      zone.device.volume = volume 

    # Bell
    master.play_bell(uri, volume)

    # Resume
    # Unjoin all
    [zone.device.unjoin() for zone in self.devices_list]
    # Join previous groups
    for device in self.devices_list:
      zone = device.device
      group_coordinator = device.state.group.coordinator
      if zone is not group_coordinator:
        zone.join(group_coordinator)
    # Resume all group coordinators
    threads = []
    for device in self.devices_list:
      zone = device.device
      t = device.resume()
      threads.append(t)
      t.start()
    # Wait for all to resume
    for t in threads:
      t.join()

class SonosDeviceManager():
  """ Handles one sonos device.
      This a wrapper around SoCo class that handles pause/play dell/resume,
      for a sonos device saving and restoring all the state of the device.
  """
  class State():
    """ Helper class to store the state of the device.
    """
    def __init__(self):
      self.playlist_position = 0
      self.uri               = ""
      self.position          = "00:00:00"
      # state is in ['STOPPED', 'PLAYING', 'PAUSED_PLAYBACK', 'TRANSITIONING']
      self.state             = "STOPPED"
      self.from_queue        = False
      self.volume            = 0
      self.group             = None

  def __init__(self, ip, logger=None):
    self.logger = logger or logging.getLogger(__name__)

    self.ip = ip
    self.device = soco.SoCo(self.ip)

  def pause_sync(self):
    """ Save the current state, and pause if the device is playing.
    """
    self.state = self.State()
    try:
      track_info     = self.device.get_current_track_info()
      transport_info = self.device.get_current_transport_info()
      queue          = self.device.get_queue()

      self.state.playlist_position = track_info["playlist_position"]
      self.state.uri               = track_info["uri"]
      self.state.position          = track_info["position"]
      self.state.state             = transport_info["current_transport_state"]
      self.state.volume            = self.device.volume
      self.logger.info("Saving volume : %s." % self.state.volume)

      for QueueItem in queue:
        if self.state.uri == QueueItem.uri:
          self.state.from_queue = True
          break

      self.state.group = self.device.group
    except:
      # Cannot retrieve current state, will return in a STOPPED state
      self.logger.error("Could not get current state.", exc_info=True)

    # Fade out
    if FADE_OUT_ENABLED:
      self.logger.info("Fading out.")
      while self.device.volume != 0:
        self.device.volume = max(self.device.volume - 5, 0)
        time.sleep(0.100)
      self.logger.info("Fading out complete.")

    if not self.device.is_coordinator:
      self.device.unjoin()
      self.logger.info("Unjoined.")

    # Stop
    if self.state.state not in ["PAUSED_PLAYBACK", "STOPPED"]:
      try:
        self.device.stop()
      except:
        self.logger.error("Could not stop.", exc_info=True)

  def resume_sync(self):
    """ Restore the previous state and resume playing if needed.
    """
    # Prepare for fade in
    self.device.volume = 0

    # Resume playing if coordiantor
    if self.device.is_coordinator:
      try:
        if self.state.from_queue:
          self.device.play_from_queue(int(self.state.playlist_position)-1)
          self.device.seek(self.state.position)
        else:
          self.device.play_uri(self.state.uri)
          self.device.seek(self.state.position)
      except:
        self.logger.error("A problem occurred while resuming", exc_info=True)

      if self.state.state == "PLAYING":
        pass
      elif self.state.state == "STOPPED":
        try:
          self.device.stop()
        except:
          self.logger.error("Could not restore STOPPED state.", exc_info=True)
      elif self.state.state == "PAUSED_PLAYBACK":
        try:
          self.device.pause()
        except:
          self.logger.error("Could not restore PAUSED_PLAYBACK state",
                            exc_info=True)

    # Fade in, all
    self.logger.info("Restoring volume to %s. Fading in." % self.state.volume)
    while self.device.volume != self.state.volume:
      self.device.volume = min(self.device.volume + 5, self.state.volume)
      time.sleep(0.100)
    self.logger.info("Fade in complete.")

  def play_bell(self, uri, volume):
    """ Play a sound from a given uri and volume.
        This function is blocking and will poll each second or so until
        the sound has finished playing.
    Args:
      uri (str): uri of the sound to play. Generally the samba share link.
      volume (int): volume at which the sound will be played.
    """
    try:
      self.logger.info("Bell : URI %s, Volume : %s." % (uri, volume))
      self.device.volume = volume
      self.device.play_uri(uri)
      time.sleep(1)  # sometimes it takes some time for the sonos to start.
      # Wait for completion : Polling each 1 second
      while True:
        time.sleep(1)

        try:
          track_info   = self.device.get_current_track_info()
          transport_info = self.device.get_current_transport_info()
        except:
          self.logger.error("Could not retrieve status while playing %s" % uri,
                            exc_info=True)
          break

        # Prevent a lock in case the device stopped playing.
        if uri not in track_info["uri"]:
          self.logger.info("URI %s is not playing." % uri)
          break
        if "PLAYING" not in transport_info["current_transport_state"]:
          self.logger.info("URI %s is not playing." % uri)
          break
    except:
      self.logger.error("An unexpected problem occurred while playing %s" % uri,
                        exc_info=True)

  def resume(self):
    """ Call resume_sync in a separate thread to make it async.
    """
    return FuncThread(self.resume_sync)
  def pause(self):
    """ Call pause_sync in a separate thread to make it async.
    """
    return FuncThread(self.pause_sync)
