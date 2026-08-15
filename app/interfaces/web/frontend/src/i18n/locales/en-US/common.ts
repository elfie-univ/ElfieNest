export const common = {
  actions: {
    cancel: "Cancel",
    close: "Close",
    confirm: "Confirm",
    processing: "Processing...",
  },
  aria: {
    closeDialog: "Close {{title}}",
    decrease: "Decrease {{label}}",
    increase: "Increase {{label}}",
    notifications: "Notifications",
  },
  language: {
    label: "Language",
  },
  mobileAccess: {
    brand: "MOBILE ACCESS",
    close: "Close mobile access QR code",
    loading: "Looking for this computer on the local network...",
    localAddress: "Local address",
    qrAlt: "QR code for {{url}}",
    qrError: "Unable to generate the QR code.",
    title: "Open ElfieNest on your phone",
    unavailable: "Phone access is not available right now, so please continue on this computer. Make sure your computer and phone are on the same local network, then try again.",
  },
  status: {
    unknown: "Unknown status",
  },
} as const
