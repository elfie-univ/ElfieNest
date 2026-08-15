# Management: users, Food and the Nest

<script setup>
import { withBase } from "vitepress";
</script>

Management is for the Nest owner and administrators. A normal member will not
see these entries and can continue using Chat and Elfies without them.

## The administrator's first job

After [First-time configuration](./configuration), complete [Core configuration](./ready):
choose a local or remote model source, validate at least one model, configure
Food for Elfies, and check **Status monitor**. That is the page to use when Chat
stops receiving replies.

<img :src="withBase('/assets/user-guide/manage.png')" alt="Status monitor example in ElfieNest" />

> This screenshot is a status-monitor example, not a success certificate. If
> **Model services** says `0 available models`, the Nest still needs a model
> connection and Food; follow [Core configuration](./ready).

## What each section does

Open **Management** from the desktop rail. The left navigation groups the
work into these areas:

| Section | What an administrator can do |
| --- | --- |
| **Status monitor** | Refresh system health, see users and Elfies, check model services and available models, and read recent events. |
| **Users** | Create local members or administrators, set each member's adoption limit, reset a password, and remove a member who no longer owns an Elfie. |
| **Elfies** | Filter by owner, species, Food or status; review a profile, bed assignment and current food; change an Elfie's current food when needed. |
| **Elfie Nest** | Set room capacity to 4–32 beds, assign or clear beds, review the floor plan, and open the room preview. |
| **Model subscriptions** | Add a remote connection or supported ChatGPT account, install/start local Ollama, download models, reload model lists, and validate connections. |
| **Food strategy** | Check, create, edit, enable, disable or archive Food; choose its model abilities; and control whether everyone or selected users can see it. |
| **System settings** | Review Elfie capacity and member limits, enable system capabilities, and adjust sign-in protection or low-frequency runtime settings. |

Save one area and wait for its success message before changing another. Never
paste an API key, password or one-time authorization code into Chat or send it
to a member.

The current local limits are 16 accounts in total and up to 5 administrators.

## Food is the user-friendly name

ElfieNest intentionally says **Food** instead of asking ordinary users to
learn about technical model details. Behind the friendly name, an
administrator is preparing which capabilities an Elfie can use:

- **Common food (常用粮)** is the normal daily choice. It must have a working **primary
  model** and be enabled.
- **Emergency food (保底粮)** is the system's last-resort backup. It is not directly
  selectable by an ordinary user. Keep it configured if the Nest should have a
  fallback when the daily choice is unavailable.
- A **custom Food** is useful when one group needs a different balance of
  speed, quality or abilities. It can be visible to everyone or only selected
  users.

Reasoning, vision, tool and fallback abilities are optional roles beside the
primary model. When a provider is down, a model is disabled, or a Food is
unconfigured, disabled or archived, that Food may be degraded or unavailable;
repair or validate the model connection before relying on it. An Elfie's
profile lets its owner choose a healthy visible **Current food**; members do not
need to edit the underlying model choices.

## Capacity, users and beds are different

Two limits are shown in Management:

- **Nest bed capacity** is how many places the room has. Change it in **Elfie
  Nest** and assign beds there.
- **Member adoption limit** is how many Elfies one member may adopt. Change the
  default or a member's limit in **Users** / **System settings**.

Increasing one does not automatically increase the other. A new adoption needs
both a member limit and a free Nest place.

## System settings in plain language

**System settings** has three kinds of controls:

- **Elfie quota** shows current Nest capacity, adopted Elfies and remaining
  room, and sets the default maximum per member.
- **System capabilities** controls optional abilities such as Web search and
  read-only Local files. Each capability has its own settings and a **Verify**
  action. Enable only what the Nest should provide.
- **Advanced settings** protects sign-in and changes low-frequency runtime
  parameters. Most people can leave these alone; a runtime change requires a
  restart before it takes effect.

## Status monitor and 3D Monitor are different

**Status monitor** is the dashboard inside Management. It answers “is the Nest
healthy?” and shows service details and recent events.

**Monitor** is the separate 3D observation page. It answers “what is happening
in the room?”:

- **Overview** shows the whole room when available;
- a location button changes the viewing position;
- **Reset** returns to the default view;
- **Pause observation** pauses only the picture, not the Nest or an Elfie's
  life;
- **Immersive view** hides surrounding navigation;
- **Retry 3D** tries the room again if the scene did not load.

The 3D room may take a moment to load. Chat, profiles and Management can still
be used while it is unavailable. Administrators can scan the Monitor QR code
for a phone view; the phone and computer must be on the same local network and
the phone still needs an administrator account.
