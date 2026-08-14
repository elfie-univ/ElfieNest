# First-time configuration

The first time ElfieNest opens, it shows a four-step setup wizard. The wizard
saves your choices as a draft while you move through the steps. Nothing is
installed or created until you confirm the final page.

## Step 1: create the first administrator

Enter:

- a sign-in account;
- the name shown in the app;
- a password and its confirmation.

This first account is the Nest owner. Keep the password somewhere safe. The
owner can later create ordinary members and other administrators from
Management.

## Step 2: choose local offline support

**Use local Ollama** is optional:

- Turn it on if you want a local model available on this computer. ElfieNest
  checks the local service, downloads the selected model during installation,
  and prepares a first **Emergency food (保底粮)** as a last-resort backup.
- Leave it off if you plan to use a model subscription configured later by an
  administrator.

You do not need to understand model names to finish setup. If you are not the
Nest administrator, ask the person who manages your Nest which option to use.

## Step 3: set the number of beds

Choose how many places the Nest should have. The current setup accepts 4–32
beds. This is the room capacity; it does not create that many Elfies.

## Step 4: review and install

Check the summary and choose **Confirm configuration and start installation**.
The page then shows an overall progress bar and the current stage. While it is
working, wait for the page to finish; the setup page intentionally does not
offer a cancel or back action.

If a stage fails, choose **Retry from the failed stage**. Completed stages are
checked again, and you should not have to re-enter every choice.

## After setup

When installation completes, choose **Enter Management**. Installation creates
the Nest, but it is not necessarily ready for daily conversation yet:

- with local support on, the wizard prepares a last-resort Emergency food
  (保底粮); an administrator should still prepare and enable a daily Common
  food (常用粮);
- with local support off, no model connection or Food is prepared by the
  wizard, so an administrator must continue with [Core configuration](./ready).

Complete that configuration check before inviting members to adopt or chat. Ordinary
members can sign in with the account created for them and do not need to repeat
the owner setup.

## Model connections and Food later

Administrators can open **Management → Model subscriptions** to add a remote
model connection, authorize a supported ChatGPT subscription, or manage local
Ollama. They then open **Management → Food strategy** to configure a daily
Common food (常用粮) and a last-resort Emergency food (保底粮) for Elfies. See [Core configuration](./ready)
for the complete checklist. The app keeps connections in local protected
storage. Never paste an API key, password or one-time authorization code into a
public document or send it to another user.
