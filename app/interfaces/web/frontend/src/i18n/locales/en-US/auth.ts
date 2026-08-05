export const auth = {
  errors: {
    login: "Sign-in failed. Try again.",
  },
  login: {
    action: "Log in",
    brand: "ELFIENEST",
    fields: {
      account: "Account",
      password: "Password",
    },
    submitting: "Signing in…",
    title: "Log in",
  },
  session: {
    signedInAs: "Signed in as {{accountName}}",
  },
} as const
