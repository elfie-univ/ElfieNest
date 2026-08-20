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

Internal-preview macOS packages are currently unsigned and not notarized, so
Gatekeeper or verification warnings may appear. Windows previews may also show
a publisher warning. Confirm that the file came from the official Releases
page, and never disable security protections for an unknown file.

## What happens when you close the window?

On the desktop app, closing the window hides ElfieNest and keeps its local
services available in the background. Use **Quit ElfieNest** from the app menu
or the tray menu when you want to stop it completely. This makes it possible to
open a phone view without reopening the desktop window.

## Remove the app

Use your system's normal uninstall flow. The native installer also removes the
global `elfienest` launcher when the package manager supports removal. Before
removing the app, make sure you have decided whether the Nest data should be
backed up or kept. If you are not sure, ask the Nest administrator; do not
delete the data folder manually.

## Next step

After the app is installed, continue with [First-time configuration](./configuration).
