# Lextend
# Copyright (c) 2014-2015 Egger Enertech <http://www.egger-enertech.ch>
# Released under the GNU Public License 3 (or higher, your choice)
# See the file COPYING for details.

import os
from glob import glob
import shutil

from settings import *

import logging

class SoundsManager():
  """ This class handles the sounds that are used as a bell sound.

    Sound files are stored in two folders as follows:
      defaults : /root/.config/[CONFIG_SUBDIR]/sounds/defaults/
      uploads : /root/.config/[CONFIG_SUBDIR]/sounds/uploads/

    defaults contain 10 preinstalled sounds that must be there.
    uploads holds user uploaded sounds, they are 10 at most.

    User running this script should have read permission for defaults,
    and read/write permission for uploads.

    Sounds' filenames always start with "index-", in the form index-name.ext
  """
  def __init__(self, config_subdir, logger=None):
    self.logger = logger or logging.getLogger(__name__)

    self.sounds_folder = os.path.join("/root", ".config", config_subdir, 
                                      "sounds")
    self.sounds_defaults_folder = os.path.join(self.sounds_folder, "defaults")
    self.sounds_uploads_folder = os.path.join(self.sounds_folder, "uploads")

    # Create needed folders if they do not exist.
    folders = [self.sounds_folder,
               self.sounds_defaults_folder,
               self.sounds_uploads_folder]
    for folder in folders:
      try:
        if not os.path.exists(folder):
          os.makedirs(folder)
      except:
        self.logger.error("Could not guarantee that %s exists." % folder,
                          exc_info=True)

    try:
      # Copy default sounds to default folder
      package_folder = path = os.path.dirname(__file__)

      sounds_defaults = os.path.join(package_folder, "..", "sounds", "defaults")
      for filename in glob(os.path.join(sounds_defaults, '*-*')):
        shutil.copy(filename, self.sounds_defaults_folder)
    except:
      self.logger.error("Could not copy default sounds to user config folder.",
                        exc_info=True)

  def delete_file_by_index(self, index):
    """ Delete an uploaded sound from its index.
    Args:
      index (int): index of the uploaded sound to delete.
    """
    target = os.path.join(self.sounds_uploads_folder, str(index)) + "-*"
    for file_to_delete in glob(target):
      try:
        os.remove(file_to_delete)
      except:
        self.logger.error("While deleting %s." % file_to_delete, exc_info=True)

  def create_upload_path(self, index, filename):
    """ Return the full path of an uploading sound from it's name and index.
    Args:
      index (int): index of the uploaded sound.
      filename (str): filename of the uploaded sound.
    Returns:
      full_path (str) : full path of the upload sound.
    """
    full_filename = "%s-%s" % (str(index), filename)
    return os.path.join(self.sounds_uploads_folder, full_filename)

  def search_path_by_index(self, index, default_sound=False):
    """ Return the full path of a sound by index, uploads are searched first.
    Args:
      index (int): index of the sound.
    Returns:
      full_path (str) : full path of the sound. None if nothing is found.
    """
    if not default_sound:
      uploads = glob(os.path.join(self.sounds_uploads_folder, str(index)) + "-*")
      if uploads:
        return uploads[0]

    defaults = glob(os.path.join(self.sounds_defaults_folder, str(index)) + "-*")
    if defaults:
      return defaults[0]

    return None
