# Desktop

The Electron Desktop is a host and supervision layer, not a product business
layer.

Desktop windows always open the Core's `/login` first. After login, `/chat` or
`/manage` is decided by the Core based on the session role and the Owner's
personal default page; Electron does not duplicate any login, chat or
management page.

## Responsible for

- Single-instance windows and lifecycle;
- Resource discovery and process supervision for the Python Core, Ollama and
  the Godot Web Runtime;
- Platform paths, packaged resources and shutdown convergence;
- The host bridge between the Desktop side and the Web Runtime.

## Not responsible for

- Elfie cognition, personality, memory and output routing;
- Accounts, adoption, chat and Nest rules;
- Duplicating Python or Godot domain facts.

After changing Desktop, use `desktop/`'s own lockfile and tests; never write
Desktop-generated artifacts back into source directories.

In development you can run:

```bash
cd desktop
pnpm install --frozen-lockfile
pnpm test
```
