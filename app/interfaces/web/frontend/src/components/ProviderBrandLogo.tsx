import { useState } from "react"

import type { ProviderProduct } from "../api/owner-providers"

type ProviderBrandLogoProps = {
  readonly product: ProviderProduct
}

export function ProviderBrandLogo({ product }: ProviderBrandLogoProps) {
  const [imageFailed, setImageFailed] = useState(false)
  const assetPath = product.brand.logo_asset.trim().replace(/^\/+/, "")
  const initial = product.brand.name.trim().slice(0, 1).toUpperCase() || "?"

  return <span aria-hidden="true" className="provider-brand-mark">
    {assetPath && !imageFailed
      ? <img alt="" onError={() => setImageFailed(true)} src={`/${assetPath}`} />
      : <span>{initial}</span>}
  </span>
}
