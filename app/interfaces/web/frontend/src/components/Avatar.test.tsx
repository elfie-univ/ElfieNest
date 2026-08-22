import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Avatar } from "./Avatar"

describe("Avatar", () => {
  it("marks the fallback initial so every avatar size can scale it consistently", () => {
    // Given: an identity without an uploaded image.
    render(<Avatar name="阿尔法" />)

    // When: the fallback avatar is rendered.
    const initial = screen.getByText("阿")

    // Then: the initial has a dedicated presentation hook instead of inheriting an arbitrary parent size.
    expect(initial).toHaveClass("avatar__initial")
  })

  it("falls back to the initial when an image URL cannot be loaded", () => {
    render(<Avatar imageUrl="/missing-avatar.png" name="阿尔法" />)

    const image = document.querySelector(".avatar img")
    if (!(image instanceof HTMLImageElement)) throw new TypeError("Expected avatar image")
    fireEvent.error(image)

    expect(screen.getByText("阿")).toHaveClass("avatar__initial")
    expect(screen.queryByRole("img")).not.toBeInTheDocument()
  })
})
