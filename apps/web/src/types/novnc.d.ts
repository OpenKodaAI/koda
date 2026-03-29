declare module "@novnc/novnc/lib/rfb.js" {
  export default class RFB {
    constructor(target: Element, url: string);
    scaleViewport: boolean;
    resizeSession: boolean;
    background: string;
    addEventListener(name: string, handler: () => void): void;
    disconnect(): void;
  }
}
