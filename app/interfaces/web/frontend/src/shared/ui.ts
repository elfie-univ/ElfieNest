import "./styles.css"

export function element<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag)
  if (className !== undefined) node.className = className
  return node
}

export function clearAndMount(node: Node): void {
  const mount = document.querySelector<HTMLElement>("#app")
  if (mount === null) throw new Error("页面缺少 #app 挂载点")
  mount.replaceChildren(node)
}

export function notice(message: string, kind: "error" | "info" = "info"): HTMLParagraphElement {
  const node = element("p", `notice notice--${kind}`)
  node.textContent = message
  return node
}

export function avatar(name: string): HTMLSpanElement {
  const node = element("span", "avatar")
  node.textContent = name.slice(0, 1) || "精"
  return node
}
