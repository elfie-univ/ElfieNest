import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"

import { SelectField } from "./SelectField"

describe("SelectField", () => {
  it("renders an accessible trigger for the selected option", () => {
    const html = renderToStaticMarkup(createElement(SelectField, {
      ariaLabel: "默认登录页",
      options: [
        { label: "管理页", value: "manage" },
        { label: "聊天页", value: "chat" },
      ],
      value: "manage",
      onValueChange: () => undefined,
    }))

    expect(html).toContain("默认登录页")
    expect(html).toContain("管理页")
    expect(html).toContain("select-field__trigger")
  })
})
