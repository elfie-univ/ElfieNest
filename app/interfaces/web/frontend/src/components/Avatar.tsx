type AvatarProps = { readonly imageUrl?: string | null | undefined; readonly name: string }

export function Avatar({ imageUrl, name }: AvatarProps) {
  return <span className="avatar" aria-hidden="true">{imageUrl ? <img alt="" src={imageUrl} /> : name.slice(0, 1) || "•"}</span>
}
