export const setup = {
  errors: {
    bedCount: "Use 4 to 32 beds.",
    complete: "Unable to complete setup.",
    install: "Unable to complete the installation.",
    load: "Unable to load setup status.",
    passwordMismatch: "The two passwords do not match.",
    pull: "Unable to download the model.",
    save: "Unable to save setup settings.",
  },
  finish: {
    action: "Enter dashboard",
    callout: "The owner account, offline fallback, nest, and model choices have been saved. You can keep adjusting them from the dashboard.",
  },
  model: {
    actions: {
      pull: "Download and verify model",
      save: "Verify and save model",
      skip: "Configure later",
    },
    callout: "ElfieNest only saves models verified at the fixed Ollama endpoint; it will not pretend that missing models are available.",
    confirmPull: "I agree to download this model; size and timing depend on the model and network.",
    fields: {
      reference: "Model (provider_id/model_id)",
    },
    noRecommendation: "Local memory is below 4 GiB or could not be detected, so no local model is recommended by default.",
    recommended: "Detected about {{memory}} GiB memory. Start with {{model}}.",
    running: "Downloading and verifying model · {{progress}}%",
    runningHint: "A refresh will show the latest progress.",
  },
  nest: {
    action: "Save room settings",
    callout: "The nest keeps at least 4 beds and at most 32; it cannot be set to 1.",
    fields: {
      bedCount: "Bed count",
    },
  },
  ollama: {
    actions: {
      bind: "Bind existing Ollama",
      install: "Download official Ollama",
      skip: "Skip for now",
    },
    callout: "Ollama can keep basic local model ability available when the network or cloud is unavailable. If you already have a shared Ollama endpoint, bind it here; ElfieNest will not switch endpoints on its own later.",
    confirmInstall: "I agree to download and run the official Ollama installer for this computer.",
    fields: {
      endpoint: "Existing Ollama endpoint",
    },
    running: "Installing Ollama · {{progress}}%",
    runningHint: "Keep this page open; a refresh will show the latest progress.",
  },
  owner: {
    action: "Create owner account",
    fields: {
      confirmPassword: "Confirm password",
      displayName: "Display name",
      password: "Password",
      accountId: "Owner account",
    },
    submitting: "Creating…",
  },
  progress: {
    stepCount: "Step {{current}} of {{total}}",
  },
  rail: {
    brand: "Setup wizard",
    current: "In progress",
    description: "Prepare the nest in five clear steps. Progress is saved automatically.",
    footnote: "Ollama and local models are not bundled with the app; official install or download flows only run after you confirm them.",
    pending: "Waiting",
    productLabel: "FIRST HOME SETUP",
    saved: "Saved",
    stepsLabel: "Setup steps",
  },
  steps: {
    owner: {
      description: "Create the single owner account. Each later step can safely continue from there.",
      label: "Create owner account",
      title: "Set up the home first.",
    },
    ollama: {
      description: "Ollama is an optional local model service that keeps basic ability available when the network or cloud is unavailable.",
      label: "Offline fallback (optional)",
      title: "Keep a light on for offline moments.",
    },
    nest: {
      description: "The room layout is fixed; only confirm the initial bed count.",
      label: "Nest beds",
      title: "Arrange the nest.",
    },
    model: {
      description: "Only verified models are saved. You can skip this now even without Ollama.",
      label: "Model and food",
      title: "Choose a model and food.",
    },
    finish: {
      description: "Confirm the foundation and enter the ElfieNest dashboard.",
      label: "Finish setup",
      title: "Ready to finish.",
    },
  },
} as const
