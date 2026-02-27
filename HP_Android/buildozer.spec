[app]
# (str) Title of your application
# You can change this freely later.
title = Hanse: Atheria Edition

# (str) Package name
package.name = hansegame

# (str) Package domain (needed for Android package/ID)
# Change to your reverse domain.
package.domain = org.atheria

# (str) Application versioning (method 1)
version = 1.0.0

# (str) Source code where the main.py lives
source.dir = .

# (list) Source files to include (comma separated)
source.include_exts = py,png,webp,jpg,jpeg,ttf,otf,json,txt

# (str) Entry point of the application
entrypoint = main.py

# (list) Application requirements
# Keep target python and hostpython pinned to the same version to avoid
# longintrepr.h header mismatch when building pygame.
requirements = python3==3.10.11, hostpython3==3.10.11, pygame

# (str) Android app theme
# android.theme = @android:style/Theme.NoTitleBar

# (str) Supported orientation (landscape matches your UI layout)
orientation = landscape

# (int) Fullscreen mode
fullscreen = 1

# (str) Presplash (optional)
presplash.filename = %(source.dir)s/HP_Game/images/bg_setup.webp

# (str) Icon (optional)
icon.filename = %(source.dir)s/assets/icon_launcher.png

# (str) Supported Android API level
android.api = 33

# (str) Minimum Android API level
android.minapi = 21

# (str) Android NDK version
android.ndk = 25b

# (list) Android permissions
# android.permissions = INTERNET

# (list) Supported architectures
android.archs = arm64-v8a, armeabi-v7a

# (str) Build release artifact type (apk or aab)
android.release_artifact = apk

# Optional signing fields (set via env or fill directly for CI)
# android.release_keystore = /absolute/path/to/release.keystore
# android.release_keyalias = your_alias
# android.release_keystore_password = your_keystore_password
# android.release_keyalias_password = your_key_password

# (bool) Copy libraries instead of linking (saves time in some builds)
# android.copy_libs = 1

[buildozer]
# (str) Log level (debug/info)
log_level = 2

# (int) Buildozer spec version
# spec_version = 0.1
