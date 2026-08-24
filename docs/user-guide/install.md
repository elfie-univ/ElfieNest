# Install and configure

## Before you begin

You need a computer that can run one of the official ElfieNest packages. Choose
the package that matches your system:

| Computer | Package to choose |
| --- | --- |
| Mac with Apple silicon | macOS arm64 |
| Intel Mac | macOS x64 |
| Windows PC | Windows x64 |
| Linux PC | Linux x64 DEB |

Download only from the [official Releases page](https://github.com/elfie-univ/ElfieNest/releases).
The preview packages are not automatically updated, so check the release notes
when you install a newer version.

> **No package listed yet?** The project is still in preview distribution. Do
> not download source files or extra tools just to run ElfieNest. Wait for an
> official package or ask your administrator for the approved file.

## Install the app

1. Download the file for your computer.
2. Open it and follow the normal installer steps for your system.
   - On macOS, open the PKG and complete the installer.
   - On Windows, run the installer and keep the default location unless your
     administrator tells you otherwise.
   - On Linux, install the DEB with your system package manager.
3. Start **ElfieNest** from Applications, the Start menu or your desktop.

The first launch may take a little longer while the app prepares its local
services. Do not open multiple copies of the app at the same time.

The macOS and Linux installers publish the management command at
`/usr/local/bin/elfienest`. If that path already contains a file or points to a
different program, installation stops and reports the conflict instead of
overwriting it. Check who owns the existing command before moving or removing
it, then run the installer again.

Preview macOS and Windows packages may show a warning that the package is not
signed or notarized. Confirm that the file came from the official Releases page;
do not disable your computer's security settings for an unknown file.

## What happens when you close the window?

On the desktop app, closing the window hides ElfieNest and keeps its local
services available in the background. Use **Quit ElfieNest** from the app menu
or the tray menu when you want to stop it completely. This makes it possible to
open a phone view without reopening the desktop window.

## Remove the app

Removing the application keeps `ELFIE_HOME` (normally `~/.elfienest`) and all
Nest data. If you also want to delete configuration or data, run
`elfienest uninstall` **before** removing the application and choose the
corresponding cleanup option. That command handles data only; it does not remove
the installed application.

- **Windows:** open **Settings > Apps > Installed apps**, select **ElfieNest**,
  and choose **Uninstall**. The uninstaller removes its own application files,
  command launcher and PATH entry.
- **Linux (DEB):** run `sudo apt remove elfienest-desktop`. The package removes
  only launchers that still point to the installed ElfieNest files.
- **macOS (PKG):** macOS has no standard PKG uninstall button. Use the commands
  below. The launcher is removed only when it still points to this ElfieNest
  application:

  ```bash
  if [ "$(readlink /usr/local/bin/elfienest 2>/dev/null || true)" = "/Applications/ElfieNest.app/Contents/Resources/management-cli/ElfieNestCli" ]; then
    sudo rm -f /usr/local/bin/elfienest
  fi
  sudo rm -rf /Applications/ElfieNest.app
  sudo pkgutil --forget com.elfienest.desktop
  ```

If the Nest belongs to several people or you are unsure whether its data should
be kept, back it up and ask the Nest administrator before choosing a data-cleanup
option.

## Next step

After the app is installed, continue with [First-time configuration](./configuration).
