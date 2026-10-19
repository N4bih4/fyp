import type { TaskOut } from './api';

export function spokenReply(task: TaskOut, language: string): string {
  const ur = language.startsWith('ur');
  const hi = language.startsWith('hi');
  const text = (english: string, urdu: string, hindi: string) => ur ? urdu : hi ? hindi : english;
  switch (task.status) {
    case 'completed': return text('Done.', 'ہو گیا۔', 'हो गया।');
    case 'awaiting_approval': return text('Please review and confirm on screen.', 'اجازت چاہیے۔ اسکرین پر دیکھیں۔', 'अनुमति चाहिए। स्क्रीन पर देखें।');
    case 'awaiting_input': return text('Please clarify the target. See the choices on screen.', 'کون سا؟ نام یا راستہ بتائیں۔', 'कौन सा? नाम या रास्ता बताएं।');
    case 'waiting_retry': return text('Service limit reached. Please wait.', 'سروس کی حد آ گئی۔ تھوڑا انتظار کریں۔', 'सर्विस की सीमा आ गई। थोड़ा इंतजार करें।');
    case 'failed': return text('Could not finish. See the reason on screen.', 'کام نہیں ہوا۔ وجہ اسکرین پر ہے۔', 'काम नहीं हुआ। वजह स्क्रीन पर है।');
    default: return text('Stopped.', 'روک دیا۔', 'रोक दिया।');
  }
}

const clean = (value: string) => value.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{M}\p{N}\s]/gu, '').replace(/\s+/g, ' ').trim();

export function isSpeechEcho(heard: string, spoken: string): boolean {
  const candidate = clean(heard);
  const source = clean(spoken);
  return Boolean(candidate && source && (source.includes(candidate) || candidate === source));
}

// Consume interruption acknowledgements, never turn "okay" into action approval.
// A following command is preserved: "achha theek hai volume down".
export function afterInterruption(heard: string): string {
  return heard.trim().replace(/^(?:(?:ach+h?a\s+)?(?:theek\s+hai|thik\s+hai)|(?:اچھا\s+)?ٹھیک\s+ہے|(?:अच्छा\s+)?ठीक\s+है|stop\s+(?:speaking|talking)|chup\s+ho\s+jao|خاموش\s+ہو\s+جاؤ|बोलना\s+बंद\s+करो|okay|ok|ach+h?a|اچھا|अच्छा|بس|رکو|ruko|bas|stop)(?=$|[\s،,.!۔])[\s،,.!۔]*/iu, '').trim();
}

export function finishOnce(callback: () => void): () => void {
  let finished = false;
  return () => { if (!finished) { finished = true; callback(); } };
}
