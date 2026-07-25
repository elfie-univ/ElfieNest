type AvatarProps = { readonly name: string }

export function Avatar({ name }: AvatarProps) {
  return <span className="avatar" aria-hidden="true">{name.slice(0, 1) || "精"}</span>
}
