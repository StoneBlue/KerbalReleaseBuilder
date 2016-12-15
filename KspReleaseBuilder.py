# Public domain license.
# Author: igor.zavoychinskiy@gmail.com
# Version: 0.1

# A very simple class to produce a .ZIP archive with a KSP mod distribution.

import collections
import glob
import json
import os.path
import re
import shutil
import subprocess


class Builder(object):
  VERSION = None

  # System path to binary that creates ZIP archive from a folder.
  SHELL_ZIP_BINARY = None
  
  # An executable which will be called to build the project's binaraies in release mode.
  SHELL_COMPILE_BINARY_SCRIPT = None

  # Folder name in game's GameData folder. It's also a release archive name.
  PACKAGE_NAME = None

  # Base path for all the repository files.
  SRC = None

  # Assembly info file to extract version number from. See ExtractVersion() method.
  SRC_VERSIONS_FILE = '/Source/Properties/AssemblyInfo.cs'

  # Path to the release's binary. If it doesn't exist then no release.
  SRC_COMPILED_BINARY = None

  # Version file to be updated during the build (see UpdateVersionInSources).
  SRC_REPOSITORY_VERSION_FILE = None

  # A path where release structure will be constructed.
  DEST = '../Release'

  # A path where resulted ZIP file wil be stored. It must exist.
  ARCHIVE_DEST = '..'

  # A format string which accepts VERSION as argument and return distribution
  # file name with no extension.
  DEST_RELEASE_NAME_FMT = None

  # A file name format for releases with build field other than zero.
  DEST_RELEASE_NAME_WITH_BUILD_FMT = None

  # Definition of the main release structure. Entities are handled in *order*, so keep type of this
  # field OrderedDict or similar.
  # Key is a path in DEST. The path *must* start from "/". The root in this case
  # is DEST. There is no way to setup absulte root on the drive.
  # Value is a path in SRC. It's either a string or a list of patterns:
  # - If value is a plain string then then it's path to a single file or
  #   directory.
  #   If path designates a folder then the entire tree will be copied.
  # - If value is a list then each item:
  #   - If does *not* end with "/*" then it's a path to a file.
  #   - If *does* end with "/*" then it's a folder name. Only files in the
  #     folder are copied, not the whole tree.
  #   - If starts from "-" then it's a request to *drop* files in DEST folder
  #     (the key). Value after "-" is a regular OS path pattern.
  STRUCTURE = collections.OrderedDict({})

  # File copy actions to do after the build.
  # First item of the tuple sets source, and the second item sets the target.
  # Both paths must be full OS paths (either absolute or relative).
  POST_BUILD_COPY = []

  def __init__(self, name, make_script_path, archiver_path):
    self.DEST_RELEASE_NAME_FMT = name + '_v%d.%d.%d'
    self.DEST_RELEASE_NAME_WITH_BUILD_FMT = name + '_v%d.%d.%d_build%d'
    self.SRC_COMPILED_BINARY = '/Source/bin/Release/' + name + '.dll'
    self.SRC_REPOSITORY_VERSION_FILE = '/' + name + '.version'
    self.PACKAGE_NAME = name
    self.SHELL_COMPILE_BINARY_SCRIPT = make_script_path
    self.SHELL_ZIP_BINARY = archiver_path
    

  # Makes the binary.
  def CompileBinary(self):
    binary_path = self.SRC + self.SRC_COMPILED_BINARY
    if os.path.exists(binary_path):
      os.unlink(binary_path)
    print 'Compiling sources in PROD mode...'
    code = subprocess.call([self.SHELL_COMPILE_BINARY_SCRIPT])
    if code != 0 or not os.path.exists(binary_path):
      print 'ERROR: Compilation failed. Cannot find target DLL:', binary_path
      exit(code)
  
  
  # Purges any existed files in the release folder.
  def CleanupReleaseFolder(self):
    print 'Cleanup release folder...'
    shutil.rmtree(self.DEST, True)
  
  
  # Creates whole release structure and copies the required files.
  def MakeFoldersStructure(self):
    # Make.
    print 'START: Building release structure:'
    for (dest_folder, src_patterns) in self.STRUCTURE.iteritems():
      if not dest_folder or dest_folder[0] != '/':
        dest_path = self.DEST + '/GameData/' + self.PACKAGE_NAME + dest_folder
      else:
        dest_path = self.DEST + dest_folder
      print 'Folder:', dest_path
      copy_sources = []
      drop_patterns = []
      for src_pattern in src_patterns:
        allow_no_matches = False
        is_drop_pattern = False
        pattern = self.SRC + src_pattern

        if src_pattern[0] == '?':
          allow_no_matches = True
          pattern = self.SRC + src_pattern[1:]
        elif src_pattern[0] == '-':
          is_drop_pattern = True
          _, file_name = os.path.split(src_pattern[1:])
          drop_patterns.append(file_name)
          continue

        entry_sources = glob.glob(pattern)
        if not entry_sources and not is_drop_pattern:
          if allow_no_matches:
            print '=> skip pattern "%s" since no matches found' % pattern
          else:
            print 'ERROR: Nothing is found for pattern:', pattern
            exit(-1)
        if not is_drop_pattern:
          copy_sources.extend(entry_sources)
        else:
          drop_patterns.extend(entry_sources)

      # Copy files.
      if copy_sources:
        self.MaybeCreateFolder(dest_path)
        for source in copy_sources:
          print '=> copy file:', source
          shutil.copy(source, dest_path)
      elif allow_no_matches:
        print '=> skip release folder due to it\'s EMPTY'
      else:
        print 'ERROR: Nothing found for release folder:', dest_folder
        print 'HINT: If this folder is allowed to be emoty then add "?" to the destination'
        exit(-1)

      # Drop files.
      if drop_patterns:
        drop_sources = []
        for pattern in drop_patterns:
          drop_sources.extend(glob.glob(os.path.join(dest_path, pattern)))
        for source in drop_sources:
          if os.path.isfile(source):
            print '=> drop file:', os.path.relpath(source, dest_path)
            os.unlink(source)
          else:
            print '=> drop folder:', source
            shutil.rmtree(source)


    print 'END: Building release structure'


  def MaybeCreateFolder(self, folder):
    if not os.path.isdir(folder):
      print 'Create folder:', folder
      os.makedirs(folder)
   
  
  # Extarcts version number of the release from the sources.
  def ExtractVersion(self):
    file_path = self.SRC + self.SRC_VERSIONS_FILE
    with open(file_path) as f:
      content = f.readlines()
    for line in content:
      if line.lstrip().startswith('//'):
        continue
      # Expect: [assembly: AssemblyVersion("X.Y.Z")]
      matches = re.match(r'\[assembly: AssemblyVersion.*\("(\d+)\.(\d+)\.(\d+)(.(\d+))?"\)\]', line)
      if matches:
        self.VERSION = (int(matches.group(1)),  # MAJOR
                        int(matches.group(2)),  # MINOR
                        int(matches.group(3)),  # PATCH
                        int(matches.group(5) or 0))  # BUILD, optional.
        break
        
    if self.VERSION is None:
      print 'ERROR: Cannot extract version from: %s' % file_path
      exit(-1)
    print 'Releasing version: v%d.%d.%d build %d' % self.VERSION
  
  
  # Updates the destination files with the version info.
  def PostBuildCopy(self):
    if self.POST_BUILD_COPY:
      print 'Post-build copy step:'
      for source, target in self.POST_BUILD_COPY:
        print '  ..."%s" into "%s"...' % (source, target)
        shutil.copy(source, target)
  
  
  # Updates the source files with the version info.
  def UpdateVersionInSources(self):
    version_file = self.SRC + self.SRC_REPOSITORY_VERSION_FILE
    print 'Update version file:', version_file
    with open(version_file) as fp:
      content = json.load(fp);
    if not 'VERSION' in content:
      print 'ERROR: Cannot find VERSION in:', version_file
      exit(-1)
    content['VERSION']['MAJOR'] = self.VERSION[0]
    content['VERSION']['MINOR'] = self.VERSION[1]
    content['VERSION']['PATCH'] = self.VERSION[2]
    content['VERSION']['BUILD'] = self.VERSION[3]
    with open(version_file, 'w') as fp:
      json.dump(content, fp, indent=4, sort_keys=True)
  
  
  def MakeReleaseFileName(self):
    if self.VERSION[3]:
      return self.DEST_RELEASE_NAME_WITH_BUILD_FMT % self.VERSION
    else:
      return self.DEST_RELEASE_NAME_FMT % self.VERSION[:3]
  
  
  # Creates a package for re-destribution.
  def MakePackage(self, overwrite_existing):
    release_name = self.MakeReleaseFileName();
    package_file_name = '%s/%s.zip' % (self.ARCHIVE_DEST, release_name)
    if os.path.exists(package_file_name): 
      if not overwrite_existing:
        print 'ERROR: Package for this version already exists: %s' % package_file_name
        exit(-1)
  
      print 'WARNING: Package already exists. Deleting.'
      os.remove(package_file_name)
  
    print 'Making %s package...' % self.PACKAGE_NAME
    code = subprocess.call([
        self.SHELL_ZIP_BINARY,
        'a',
        package_file_name,
        self.DEST + '/*'])
    if code != 0:
      print 'ERROR: Failed to make the package.'
      exit(code)


  def MakeRelease(self, make_archive, overwrite_existing=False):
    self.ExtractVersion()
    self.CleanupReleaseFolder()
    self.CompileBinary()
    if self.SRC_VERSIONS_FILE:
      self.UpdateVersionInSources()
    else:
      print 'No version file, skipping'
    self.MakeFoldersStructure()
    self.PostBuildCopy()
    if make_archive:    
      self.MakePackage(overwrite_existing)
    else:
      print 'No package requested, skipping.'
    print 'SUCCESS!'