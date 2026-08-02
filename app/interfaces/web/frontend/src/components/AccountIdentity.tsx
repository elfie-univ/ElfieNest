import type { ClientUser } from "../api/client"
import { Avatar } from "./Avatar"

type AccountIdentity = Pick<ClientUser, "account_id" | "avatar_url" | "display_name">

export function accountDisplayName(user: Pick<AccountIdentity, "account_id" | "display_name">): string {
  return user.display_name?.trim() || user.account_id
}

export function AccountIdentityAvatar({ user }: { readonly user: AccountIdentity }) {
  return <Avatar imageUrl={user.avatar_url} name={accountDisplayName(user)} />
}
