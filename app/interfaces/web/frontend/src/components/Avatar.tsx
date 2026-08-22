import { useEffect, useState } from "react"

type AvatarProps = { readonly imageUrl?: string | null | undefined; readonly name: string }

export function Avatar({ imageUrl, name }: AvatarProps) {
  const [imageFailed, setImageFailed] = useState(false)
  useEffect(() => setImageFailed(false), [imageUrl])
  const showImage = Boolean(imageUrl) && !imageFailed
  return <span className="avatar" aria-hidden="true">
    {showImage ? <img alt="" onError={() => setImageFailed(true)} src={imageUrl ?? undefined} /> : <span className="avatar__initial">{name.slice(0, 1) || "•"}</span>}
  </span>
}
