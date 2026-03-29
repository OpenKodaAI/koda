export function createSSEStream(
  pollFn: () => Promise<Record<string, unknown>>,
  intervalMs: number = 2000
): ReadableStream {
  let timer: ReturnType<typeof setInterval> | null = null;
  let lastState: string = "";

  return new ReadableStream({
    start(controller) {
      const encoder = new TextEncoder();

      const send = (event: string, data: unknown) => {
        controller.enqueue(
          encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
        );
      };

      let heartbeatCounter = 0;

      timer = setInterval(async () => {
        try {
          heartbeatCounter++;

          // Heartbeat every 30s (15 intervals of 2s)
          if (heartbeatCounter % 15 === 0) {
            send("heartbeat", { ts: Date.now() });
          }

          const state = await pollFn();
          const stateStr = JSON.stringify(state);

          if (stateStr !== lastState) {
            lastState = stateStr;
            send("update", state);
          }
        } catch (error) {
          console.error("SSE poll error:", error);
        }
      }, intervalMs);
    },
    cancel() {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    },
  });
}
