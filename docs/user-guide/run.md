# Daily use: chat, profiles and phone access

<script setup>
import { withBase } from "vitepress";
</script>

After setup and the administrator's [core configuration](./ready), most people
spend their time in **Chat** and **Elfies**. The desktop app opens the same
local Nest each time you sign in. If someone else manages the Nest, you do not
need to configure models or Food yourself.

## Chat with an Elfie

1. Open **Chat**.
2. Choose an Elfie from the conversation list, or open **Elfies** and choose
   **Enter chat** from a profile.
3. Write a message and choose **Send**.
4. Return later to see the conversation history.

<img :src="withBase('/assets/user-guide/chat.png')" alt="A desktop chat message in ElfieNest" />

If the Elfie does not reply after waiting a little while, check
[Troubleshooting](./troubleshooting). A sent message can still be kept in the
conversation while the service recovers.

## Read an Elfie's profile

In **Elfies**, select an Elfie to see:

- the basic introduction, species, age and owner;
- an interactive 3D appearance when the local 3D view is available;
- personality scores and highlighted traits;
- experiences, relationships, world understanding, knowledge and Food strategy
  sections as they become available.

<img :src="withBase('/assets/user-guide/profile.png')" alt="An Elfie profile with the 3D appearance area" />

Choose **Enter chat** from the profile whenever you want to talk. The **Food
strategy** section is where the owner can choose a currently available
**Current food**. Ordinary members do not need to manage the model recipe
behind it. If the profile says that no current food is available, ask the Nest
administrator to follow [Core configuration](./ready).

## Use ElfieNest on a phone

There is no separate mobile app. The desktop app can show a QR code for the
current view:

1. Make sure the phone and the computer running ElfieNest are on the same local
   network.
2. In the desktop rail, choose **Scan to open Chat**, **Management** or
   **Monitor on a phone**, depending on what you need.
3. Scan the QR code with the phone camera and open the displayed page.
4. On a phone, the bottom navigation switches between **Messages**, **Elfies**
   and **Me**.

<img :src="withBase('/assets/user-guide/mobile-chat.png')" alt="The ElfieNest chat view on a phone" />

Phone access follows the same account permissions as the desktop app. A normal
member can use chat and profiles; only an administrator can open Management or
Monitor. If the QR dialog says that the service is local-only, ask the Nest
administrator to enable access from the local network. Do not forward the QR
code to people who should not access the Nest.

## Personal settings

Choose your avatar at the bottom of the navigation to open **Me**. You can
change your display name, avatar, password, language and theme. Administrators
can also choose whether their default landing page is Chat or Management.
