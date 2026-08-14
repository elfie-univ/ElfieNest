# Core configuration: models and Food

Finishing the first-time configuration creates the basic Nest settings, but an
administrator still needs to complete the core model and Food configuration
before inviting people to use it.

ElfieNest deliberately calls this **Food**. It is a friendly way to talk about
the capability an Elfie uses to think, talk and, when enabled, use tools. You
do not need to learn the technical details behind it: choose where the ability
comes from, prepare a Food, and keep it available.

## The simple story

- A **model service** is the source of the ability: it can run on this computer
  (local Ollama) or be provided online (a remote subscription).
- **Food** is the prepared everyday choice made from the available models. It
  tells ElfieNest which ability to use for normal conversation and optional
  tasks.
- **Common food (常用粮)** is the daily meal. It needs a working **primary** model.
- **Emergency food (保底粮)** is the last-resort meal. It is a system backup, not a
  choice that ordinary users select directly.

If there is no working model or no enabled Food with a primary model, an Elfie
has no energy for a normal reply. That is why this page comes before adoption
and daily chat.

## Who needs to do this?

Ordinary members can skip this page. The Nest owner or an administrator should
complete it once, and revisit it when a provider, model or Food becomes
unavailable.

## Administrator checklist

### 1. Choose where the ability comes from

| Choice | Good when | Keep in mind |
| --- | --- | --- |
| **Local Ollama** | You prefer local privacy or want less dependence on the internet | The computer needs enough disk space and memory; a model must be downloaded; the local service must be running |
| **Remote subscription** | You want to use an online provider without keeping a model on this computer | The computer needs internet access; provider rules, account limits or usage charges may apply; conversation data is sent to that provider |

You can keep both available and use one as a backup. The setup wizard's local
option is optional; it does not prevent an administrator from adding a remote
connection later.

### 2. Add and check a model service

Open **Management → Model subscriptions**.

- For a remote service, choose a supported provider, enter its connection or
  authorization details, and save it.
- For local use, open the **Ollama** card. Install or start it if needed, then
  download a recommended model from **Models**.
- Open **Models** for the connection and make sure at least one model is
  available. Choose **Validate** (or **Validate all**) after adding or
  changing a connection.

Only available, recently validated models can be used to prepare Food. A saved
connection that has not been validated is not ready for daily use.

### 3. Configure Food for Elfies

Open **Management → Food strategy**.

1. Check **Emergency food (保底粮)** first. It is the last backup. A local setup may
   prepare it automatically, but still check that it is configured and enabled.
2. Check **Common food (常用粮)** for everyday use. Give it a working **primary**
   model, then enable and save it. Reasoning, vision, tool and fallback
   abilities are optional and can be added when the Nest needs them.
3. Add a custom Food only when you need a different balance of speed, quality
   or abilities. You can make it visible to everyone or only selected users.
   Use **Generate preview** to review a suggestion before saving it.

The screen may show the technical model names while you are editing. That is
for the administrator; members only need the friendly Food name. A Food with
no primary model or a disabled Food cannot power an Elfie; a Food whose provider
is unavailable may be degraded or unavailable and should be repaired first.

### 4. Check the configuration

Return to **Management → Status monitor** and refresh it. A healthy starting
point is:

- **System health** is healthy;
- **Model services** shows a running/validated service and at least one
  available model;
- **Food strategy** shows an enabled Common food and a configured Emergency
  food.

After an Elfie exists, open its profile and check **Current food**. An owner can
choose one of the healthy Foods made visible to that user. If the profile says
that no current food is available, return to Food strategy or ask the
administrator to fix it.

## After core configuration

The owner can now [adopt an Elfie](./adoption), create member accounts, and
invite people to [use Chat](./run). If Chat later stops receiving replies,
start with [Troubleshooting](./troubleshooting): first check the model service,
then Food, then the Elfie's current food.
