# Releasing vcui

Releases are built by `.github/workflows/build.yml` on a Windows runner:

1. tests (web app and engine) on Linux;
2. the engine packaged with PyInstaller (`engine/vcui-engine.spec`) and started once as a smoke test;
3. the NSIS installer built by `tauri-apps/tauri-action`, with the engine as app resources
   (`src-tauri/tauri.release.conf.json`).

| Trigger | Result |
| --- | --- |
| Push to any branch, or a pull request | Installer kept as the workflow artifact `vcui-windows-installer`. |
| Push to `main` | Release `v<version>` published, marked latest. |
| Manual run (*Actions → Build → Run workflow*) with `draft` | Draft release `v<version>` with the installer attached. |

`<version>` comes from `src-tauri/tauri.conf.json`. Bump it, together with `package.json`,
`src-tauri/Cargo.toml` and `engine/pyproject.toml`, for every release: a push to `main` with an
unchanged version replaces the files of the existing release.

## Automatic updates

The app checks `https://github.com/sockulags/vcui/releases/latest/download/latest.json` at start.
When a newer signed version is there, the top bar offers it; installing stops the engine, runs the
installer in passive mode and restarts the app.

Update packages must be signed with the private key whose public half is in
`src-tauri/tauri.conf.json` (`plugins.updater.pubkey`). The workflow signs when these repository
secrets exist (*Settings → Secrets and variables → Actions*):

- `TAURI_SIGNING_PRIVATE_KEY`: the contents of the private key file;
- `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`: its password.

Without them, the installer is still built but has no update package, and the run shows a warning.
An installed app updates only to a release that has `latest.json`, so the first version with the
updater (0.2.0) has to be installed by hand.

To replace the key: `npx tauri signer generate -w vcui-updater.key`, put the `.pub` contents in
`plugins.updater.pubkey`, update both secrets, and release. Apps that have the old public key will
not accept updates signed with the new one: they need one manual install.

## Checklist

1. Bump the version in the four files above and add what changed to the release notes.
2. Merge to `main` (squash). The workflow publishes `v<version>`.
3. Check the release has `vcui_<version>_x64-setup.exe`, and, with the signing secrets,
   `vcui_<version>_x64-setup.exe.sig` and `latest.json`.
4. Install it on Windows, start it, and say a command.
