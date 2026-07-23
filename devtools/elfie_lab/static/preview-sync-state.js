export function createPreviewSyncState() {
  let ready = false;
  let claimedKey = "";

  return {
    setReady(value) {
      ready = Boolean(value);
      if (!ready) claimedKey = "";
    },
    claim(key) {
      if (!ready || !key || key === claimedKey) return false;
      claimedKey = key;
      return true;
    },
    release(key) {
      if (!key || key === claimedKey) claimedKey = "";
    },
  };
}
