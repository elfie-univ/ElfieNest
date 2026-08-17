export const auth = {
  errors: {
    login: "Sign-in failed. Try again.",
    register: "Registration failed. Try again.",
  },
  login: {
    action: "Log in",
    registerAction: "Register and continue",
    registerSubmitting: "Registering and signing in…",
    switchToLogin: "Already have an account? Log in",
    switchToRegister: "No account? Register",
    fields: {
      account: "Account",
      confirmPassword: "Confirm password",
      displayName: "Display name",
      password: "Password",
    },
    passwordMismatch: "The passwords do not match.",
    submitting: "Signing in…",
  },
} as const
