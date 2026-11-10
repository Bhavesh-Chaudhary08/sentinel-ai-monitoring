// Device identity, shared by the capture path and the activity sessionizer.

const DEVICE_ID_KEY = "device_id";

export async function getDeviceId(): Promise<string> {
  const stored = await chrome.storage.local.get(DEVICE_ID_KEY);
  const existing = stored[DEVICE_ID_KEY] as string | undefined;
  if (existing) return existing;
  const id = `ext-${crypto.randomUUID()}`;
  await chrome.storage.local.set({ [DEVICE_ID_KEY]: id });
  return id;
}
