// Reads the last SMS the demo API "sent" (MCL_DEV_SMS_INBOX=true, demo back end only).
export async function readCode(phone: string): Promise<string> {
  const res = await fetch(`http://localhost:8000/api/dev/sms/${phone}`)
  const { text } = (await res.json()) as { text: string | null }
  const code = text?.match(/\b(\d{6})\b/)?.[1]
  if (!code) throw new Error(`No code SMS for ${phone}`)
  return code
}
