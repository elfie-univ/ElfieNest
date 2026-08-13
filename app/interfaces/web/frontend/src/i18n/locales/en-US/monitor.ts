export const monitor = {
  session: {
    verifying: "Verifying your session…",
  },
  surface: {
    title: "3D room monitor",
    roomHint: "Drag to look around the room. Use the wheel or a two-finger gesture to zoom.",
    elfieHint: "Drag to orbit the Elfie. Use the wheel or a two-finger gesture to zoom.",
    enter: "Enter 3D",
    end: "End monitoring",
    idle: "3D loads the first time it opens without blocking chat or management.",
    loading: "Opening the local monitoring view…",
    retry: "Retry 3D",
    fallback: {
      insecureTitle: "Mobile browsers need a secure connection for 3D room monitoring.",
      insecureDetail: "Use localhost on this device, or serve the local-network address over HTTPS. Browsers block insecure HTTP addresses such as 192.168.*.",
      unsupportedTitle: "This device cannot run 3D room monitoring right now.",
      unavailableTitle: "3D monitoring is unavailable.",
      entityCount: "{{count}} Elfies are currently visible.",
      continue: "Chat, profiles, and room management remain available.",
    },
  },
  toolbar: {
    label: "Monitoring controls",
  },
  navigation: {
    controls: "Monitor navigation",
    exitImmersive: "Exit immersive monitoring",
    immersive: "Enter immersive monitoring",
    mobileAccess: "Open monitor on a phone",
    railLabel: "Monitor navigation rail",
  },
  controls: {
    resetAria: "Reset view",
    reset: "Reset",
    overview: "Overview",
    pause: "Pause monitoring",
    resume: "Resume monitoring",
    retry: "Retry 3D monitoring",
  },
  status: {
    offline: "Monitoring is unavailable.",
    idle: "Monitoring is not connected.",
    loading: "Connecting to {{endpoint}}…",
    fallback: "Monitoring is unavailable.",
    unknown: "Monitoring status is unavailable.",
  },
  empty: {
    cameras: "Waiting for the runtime to provide camera views.",
  },
  help: {
    controls: "Switch between overview and runtime camera views, reset the view, or pause and resume monitoring.",
    disabled: "3D monitoring is not enabled for this session. Other features remain available.",
    idle: "The 3D scene loads when monitoring opens without blocking chat or management.",
    insecureContext: "Mobile browsers require a secure HTTPS connection. You can use localhost on this device.",
    loading: "The local 3D scene is starting. This can take a moment.",
    offline: "No Observer is available in this session.",
    runtime: "The local 3D runtime stopped responding. You can retry without leaving this page.",
    unknown: "Monitoring returned an unknown status. Try again later.",
    unsupportedDevice: "This device cannot run 3D monitoring right now. Other features remain available.",
  },
  connection: {
    connectedTo: "Connected to {{endpoint}}",
  },
  errors: {
    connect: "Unable to connect to monitoring.",
    control: "Unable to complete the monitoring control.",
  },
} as const
