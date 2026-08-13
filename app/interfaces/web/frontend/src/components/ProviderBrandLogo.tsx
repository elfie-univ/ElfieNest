import { useState } from "react"

import type { ProviderProduct } from "../api/owner-providers"

type ProviderBrandLogoProps = {
  readonly brand: ProviderProduct["brand"]
}

export function ProviderBrandLogo({ brand }: ProviderBrandLogoProps) {
  const [imageFailed, setImageFailed] = useState(false)
  const assetPath = brand.logo_asset.trim().replace(/^\/+/, "")
  const initial = brand.name.trim().slice(0, 1).toUpperCase() || "?"

  return <span aria-hidden="true" className="provider-brand-mark">
    {assetPath && !imageFailed
      ? <img alt="" onError={() => setImageFailed(true)} src={`/${assetPath}`} />
      : <span>{initial}</span>}
  </span>
}
