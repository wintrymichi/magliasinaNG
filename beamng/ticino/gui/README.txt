Ticino Server

TicinoServer.exe is the Windows app of the Ticino map of MagliasinaNG. It needs no installation: run it from anywhere.

- Downloads: downloads the map from the GitHub release into the folder you choose (about 52 GB), only what changed,
  resumes interrupted downloads and checks every zip against its sha256. Updates are installed when the server and
  the game are closed.
- Graphics: view distance of trees, far terrain, buildings, roads and details (BeamNG's settings\ticino.json).
- Server: starts and stops ticino_server.exe (downloaded by the app itself), shows its log and its state.
- Play: starts the server and BeamNG straight into the map.

The app's own files are in %LOCALAPPDATA%\TicinoServer (settings.json, app.log, server\).
A draft release can only be downloaded with GitHub CLI logged in (gh auth login).
