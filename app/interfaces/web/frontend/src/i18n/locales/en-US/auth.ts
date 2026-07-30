export const auth = {
  errors: {
    login: "Sign-in failed. Try again.",
  },
  login: {
    action: "Enter ElfieNest",
    brand: "ELFIENEST · A HOME FOR ELFIES",
    description: "Sign in to enter your chat and management space.",
    fields: {
      account: "Account",
      password: "Password",
    },
    submitting: "Signing in…",
    title: "Welcome back. Your Elfie is waiting.",
  },
  session: {
    signedInAs: "Signed in as {{accountName}}",
  },
} as const
