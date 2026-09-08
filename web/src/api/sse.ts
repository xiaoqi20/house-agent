export interface SseEvent {
  name: string;
  data: Record<string, unknown>;
}

const FRAME_SEP = /\r?\n\r?\n/;

export async function ssePost(
  url: string,
  onEvent: (e: SseEvent) => void,
): Promise<void> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok || !res.body) {
    let message = `HTTP ${res.status}`;
    try {
      const payload = await res.json();
      message =
        typeof payload.detail === "string"
          ? payload.detail
          : JSON.stringify(payload.detail);
    } catch {
      /* keep status text */
    }
    throw new Error(message);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let m: RegExpExecArray | null;
    while ((m = FRAME_SEP.exec(buf)) !== null) {
      const frame = buf.slice(0, m.index);
      buf = buf.slice(m.index + m[0].length);
      let name = "message";
      let data = "";
      for (const line of frame.split(/\r?\n/)) {
        if (line.startsWith("event:")) name = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data)
        onEvent({ name, data: JSON.parse(data) as Record<string, unknown> });
    }
  }
}
