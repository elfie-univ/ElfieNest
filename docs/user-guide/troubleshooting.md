# Troubleshooting

Start with the symptom that matches what you see. Do not delete the Nest data
folder as a first step.

## The installer will not open

Confirm that the package matches your computer and came from the official
[Releases page](https://github.com/elfie-univ/ElfieNest/releases). Preview macOS
and Windows packages may show an unsigned-package warning. If the warning names
an unknown file or publisher, stop and ask the person who provided the package.

## The app stays on “Starting”

Wait a little longer on the first launch, then close and reopen the app once.
Check that another ElfieNest copy is not already open in the tray. If it still
does not start, save a screenshot of the error page and contact the Nest
administrator.

## The app says that the data folder is from an older version

The app will show a recovery page before starting Core or Godot. Choose
**Back up old data and create a new environment** to keep the complete old
folder in the displayed backup location and create a fresh environment at the
original path. The old account, Elfie and history data is not migrated
automatically. Do not delete the old backup unless you have confirmed that you
no longer need it.

If you prefer to inspect the result from a terminal, run:

```bash
elfienest data-home inspect --json
```

The recovery operation is also available as `elfienest data-home recover`; it
backs up the old folder before rebuilding the active folder and never performs
an in-place migration.

On current pre-LFC-010 builds, an existing fresh folder can still be selected
with `elfienest data-home activate --data-home PATH`. This is a temporary
compatibility command. The accepted lifecycle target removes it: installed
entrypoints select through `ELFIE_HOME`, while source lifecycle commands use
`--data-home` or context.

## First setup failed

Return to the locked setup page and choose **Retry from the failed stage**. The
wizard keeps completed choices. If the local model stage fails, leave local
support off and ask an administrator to complete [Core configuration](./ready)
with another model source.

## I cannot sign in

Check the account name and password exactly as they were created. An
administrator can reset a member password from **Management → Users**. Never
send a password in a screenshot or chat.

## My message was sent but there is no reply

This usually means no usable Food is currently available. If you are a member,
ask the administrator to do these checks in order:

1. Open **Management → Status monitor** and refresh. If it says **No model
   service** or shows `0 available models`, continue to Model subscriptions.
2. In **Model subscriptions**, make sure a remote connection is validated, or
   that local Ollama is running and has an installed model. For a remote service,
   check internet access, authorization and any provider account limit.
3. In **Food strategy**, make sure an enabled **Common food (常用粮)** has a healthy
   primary model. If the Food is unconfigured, disabled, degraded or
   unavailable, repair the connection, validate again, or choose another Food.
4. Open the Elfie's profile and check its **Current food**. An owner can pick
   another healthy Food that is visible to them. If the page says that no current
   food is available, the administrator must prepare or enable one.

Do not repeatedly send the same message while the service is recovering. A
sent message can remain in the conversation even when its reply is delayed.

## A model connection fails validation

Check the provider name, connection address and authorization details, then
save and choose **Validate** again. For a remote service, check the network and
provider account. For local Ollama, start or restart the service and confirm a
model is installed. A connection may stay saved while it is being repaired, but
it is not ready for Food until validation succeeds.

## Food is unavailable or degraded

Open **Food strategy** and read the Food status. A provider may be offline, a
model may have been disabled, or an optional role may no longer be available.
The administrator can repair the provider, choose a different available model,
or save another healthy Common food. Emergency food is only a last resort and
cannot help if it was never configured or has no working model.

## Local Ollama is stopped or missing

In **Management → Model subscriptions**, open the Ollama card. Choose
**Install**, **Start** or **Restart** as shown, then open **Models** and download
one of the recommended models. If installation or download fails, check disk
space and ask the administrator to use a remote model source instead.

## The 3D profile or room is unavailable

The 3D view loads separately from Chat. Choose **Retry 3D**, then continue using
the text profile or Chat if it is still unavailable. On a phone, some devices
cannot run the 3D view even though chat works.

## The phone QR code does not work

Keep the phone and computer on the same local network, scan a newly generated
code, and make sure the displayed address is reachable from the phone. If the
dialog says the service is local-only, ask the administrator to enable access
from the local network. Do not share the code outside the Nest.

## The app is still running after I close the window

That is expected for the desktop app: closing the window hides it in the tray.
Choose **Quit ElfieNest** from the app or tray menu to stop the local services.

## What to send when asking for help

Send the visible error text, the app version and the step where it happened.
Screenshots are useful. Do not include passwords, API keys, one-time codes or
your entire local data folder.
