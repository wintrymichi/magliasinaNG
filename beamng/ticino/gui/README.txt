Ticino Server

TicinoServer.exe is the Windows app of the Ticino map of MagliasinaNG. It needs no installation: run it from anywhere.

- Downloads: downloads the map from the GitHub release into the folder you choose (about 52 GB), only what changed,
  resumes interrupted downloads and checks every zip against its sha256. Updates are installed when the server and
  the game are closed.
- Graphics: view distance of trees, far terrain, buildings, roads and details (BeamNG's settings\ticino.json).
- Server: starts and stops ticino_server.exe (downloaded by the app itself), shows its log and its state.
- Play: starts the server and BeamNG straight into the map. In packs mode (every zip in BeamNG's mods, as the installer
  makes it with -Mode packs) it starts BeamNG and the streaming helper, as "Start Ticino" does; Move on the Home page
  takes the zones out of mods into a packs folder and switches to the server.

If you installed the map with "Install Ticino", the app uses the same folders: the zone packs in the installer's
data folder (<user folder>\ticino_data by default) and the server in <user folder>\ticino_tools. Its settings go into
ticino_tools\ticino_server.json, so "Start Ticino" runs the server the same way, and a server started by the shortcut
is shown as running (the app does not start a second one).

The app's own files are in %LOCALAPPDATA%\TicinoServer (settings.json, app.log, server\).
It downloads from the public pre-release ticino-v1. Another release can be set on the Downloads page; a draft release
can only be downloaded with GitHub CLI logged in (gh auth login).
