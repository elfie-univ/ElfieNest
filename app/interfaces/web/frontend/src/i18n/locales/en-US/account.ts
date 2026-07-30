export const account = {
  feedback: {
    landingSaved: "The default landing page has been saved.",
    passwordSaved: "The password has been updated.",
    themeSaved: "The color theme has been saved.",
  },
  identity: {
    editDisplayName: "Edit display name",
    ownerRole: "Owner · system administration access",
    saveDisplayName: "Save display name",
    uploadAvatar: "Upload a local avatar",
    userRole: "User · chat and Elfie space",
  },
  language: {
    sectionLabel: "Language preference",
  },
  landing: {
    action: "Save default page",
    chat: "Chat page",
    field: "Default landing page",
    manage: "Dashboard",
    saving: "Saving…",
  },
  panel: {
    close: "Close profile settings",
    label: "Profile and appearance settings",
    title: "Profile settings",
  },
  password: {
    action: "Update password",
    current: "Current password",
    next: "New password",
    saving: "Updating…",
  },
  session: {
    currentAccount: "Current account: {{accountName}}",
  },
  sections: {
    landing: "Default landing page",
    password: "Change password",
    passwordSummary: "Update sign-in credentials",
    theme: "Color theme",
  },
  themes: {
    harborBlue: { description: "Refreshing", label: "Harbor Blue" },
    mossGreen: { description: "Natural", label: "Moss Green" },
    orchidArchive: { description: "Quiet", label: "Orchid Archive" },
    warmPaper: { description: "Default", label: "Warm Paper and Clay" },
  },
  trigger: {
    compact: "Open profile settings",
    owner: "Owner",
    tooltip: "Profile settings",
    user: "User settings",
  },
} as const
