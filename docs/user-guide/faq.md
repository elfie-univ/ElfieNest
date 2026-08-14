# FAQ

## What is ElfieNest?

ElfieNest is the local home and desktop app where an Elfie can live, remember
experiences and interact with you. The app gives you Chat, profiles and a room
to observe.

## What is an Elfie? What is a Nest?

An **Elfie** is the individual companion. The **Nest** is the shared home and
room where Elfies live. You adopt an Elfie; you configure the Nest.

## What does “Food” mean?

**Food** is ElfieNest's friendly name for the capability an Elfie uses to think
and talk. It hides the technical details behind that ability. **Common food
(常用粮)** is the daily choice; **Emergency food (保底粮)** is the last backup. An administrator prepares
and enables Food from the available models. Ordinary users only choose a
healthy visible current food when the profile offers more than one.

## Do I need to understand code or AI models?

No. Install the desktop app, finish setup, and use the visible pages. Model
connections and Food are an administrator task; developers can read the
separate [Developer docs](/developer/).

## Is a local model required?

No. The administrator can choose either source:

| Source | What it means for you |
| --- | --- |
| Local Ollama | The model stays on the Nest computer and can work with less internet dependence, but it uses disk and memory and must be running. |
| Remote subscription | The Nest uses an online provider, so the computer needs internet access and the provider's rules or usage charges may apply. Conversation data is sent to that provider. |

Both can be kept available. See [Core configuration](./ready) for the
administrator's checklist.

## Why can I not chat?

Chat needs a running model service and at least one enabled, healthy Food with a
primary model. Ask an administrator to check **Management → Status monitor**,
**Model subscriptions** and **Food strategy** in that order. If the profile says
that no current food is available, the administrator must prepare one.

## Who configures Food?

The Nest owner or an administrator. They decide which model source to use,
validate models, prepare Common and Emergency food, and control which users can
see custom Food. An Elfie's owner may choose the current food from the
healthy options they are allowed to use.

## Can I use ElfieNest on my phone?

Yes, through the QR code in the desktop app. The phone and computer need to be
on the same local network, and the phone follows the same account permissions.
There is no separate mobile app to download.

## Why can I not see Management or Monitor?

Those areas are reserved for the Nest owner and administrators. A normal member
can still chat, browse Elfie profiles and use personal settings.

## Does closing the window stop ElfieNest?

No. Closing the window hides the app in the tray so local services can continue.
Choose **Quit ElfieNest** when you want to stop it completely.

## Where is my data, and does a provider see it?

The Nest, profiles and settings are kept on the computer that runs the app.
Local model use keeps model conversations on that computer, subject to any
optional online tools an administrator enables. A remote model provider receives
the conversation needed to answer and may charge according to its terms. Keep
the computer private, follow your provider's policy, and do not send the entire
Nest data folder to support.

## What if my question is not here?

Start with [Troubleshooting](./troubleshooting). If you still need help, send
the visible error text, version and steps that led to it, without passwords,
keys or one-time codes.
