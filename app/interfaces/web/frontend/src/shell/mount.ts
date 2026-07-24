import { shellPages, type ShellPage } from "./content"

function createNavigation(page: ShellPage): HTMLElement {
  const navigation = document.createElement("nav")
  const pageNavigation = shellPages[page].navigation

  for (const item of pageNavigation) {
    const link = document.createElement("a")
    link.href = item.href
    link.textContent = item.label
    navigation.append(link)
  }

  return navigation
}

function createLoginForm(): HTMLFormElement {
  const form = document.createElement("form")
  form.action = "/api/auth/login"
  form.method = "post"

  for (const [labelText, fieldName, fieldType] of [
    ["账号", "username", "text"],
    ["密码", "password", "password"]
  ] as const) {
    const label = document.createElement("label")
    label.textContent = labelText
    const input = document.createElement("input")
    input.name = fieldName
    input.required = true
    input.type = fieldType
    label.append(input)
    form.append(label)
  }

  const submit = document.createElement("button")
  submit.textContent = "登录"
  submit.type = "submit"
  form.append(submit)
  return form
}

export function mountShell(page: ShellPage): void {
  const mountPoint = document.querySelector<HTMLElement>("#app")
  if (mountPoint === null) {
    throw new Error("Web shell requires a #app mount point.")
  }

  const content = shellPages[page]
  const heading = document.createElement("h1")
  heading.textContent = content.heading
  const description = document.createElement("p")
  description.textContent = content.description

  const shell = document.createElement("section")
  shell.append(heading, description, createNavigation(page))
  if (page === "login") {
    shell.append(createLoginForm())
  }
  mountPoint.replaceChildren(shell)
}
