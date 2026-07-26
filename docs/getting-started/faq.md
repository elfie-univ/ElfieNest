# FAQ

## What is ElfieNest?

It is a software station connecting Earth and Elfaria, and it is also an Elfie's
Nest on Earth. Technically it composes the creature individual, the in-nest
environment, the model runtime and the spatial presentation.

## What is the difference between an Elfie and a Nest?

An Elfie is a complete creature individual; a Nest is the activity space it
lives in. One answers "who is living", the other answers "where they live and
what happens there".

## Do I need to understand models and code first?

No. The normal usage path starts from install, configure and run; models,
module boundaries and tests belong to the [Developer docs](/developer/).

## Where is data stored?

Production data lives under `ELFIE_HOME`; the source tree only stores code and
the finalized documents that can be published.

## Can it run without an external model service?

You can use fallback mode to validate the basic runtime pipeline. For the full
model experience you need to configure an available model service per the
provider instructions.
