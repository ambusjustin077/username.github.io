# Build iOS/Android packages with Buildozer (https://buildozer.readthedocs.io/).
# iOS builds require macOS with Xcode; they cannot be produced on Windows alone.

[app]

title = Gravity Bounce
package.name = gravitybounce
package.domain = org.cs325.ambus

source.dir = .
source.include_exts = py,json,png,jpg,jpeg,kv,atlas,ttf,otf,mp3,wav
source.exclude_dirs = tests, bin, .git, __pycache__, .buildozer, .idea

version = 0.1

requirements = python3,kivy

orientation = landscape
fullscreen = 0

osx.python_version = 3.11

[buildozer]
log_level = 2
warn_on_root = 1

[ios]
# codesign_identity = Apple Development: Your Name (TEAMID)
# Set team / signing in Xcode after `buildozer ios debug` generates the Xcode project,
# or configure ios.codesign.* per Buildozer docs for automated signing.
